"""SQLite-backed URL/content deduplication cache.

Implements two-phase dedup per SPEC.md §4.4:
  Phase 1 — url_hash check (before content fetch)
  Phase 2 — content_hash check (after excerpt fetch, before LLM)

Schema: seen_items(url_hash TEXT, content_hash TEXT, seen_at TEXT)
  - PRIMARY KEY (url_hash, content_hash) — enables INSERT OR IGNORE idempotency
  - seen_at stored as ISO 8601 UTC string
  - raw_content is NOT stored (SPEC.md §4.4 explicit constraint)

Cache safety rule (SPEC.md §4.4): mark_seen is called by pipeline.py ONLY after
successful digest generation. cache.py does not enforce this ordering.

Spec reference: SPEC.md §4.4 (caching & deduplication).
"""

# Standard library imports
import hashlib
import sqlite3
from datetime import UTC, datetime, timedelta
from pathlib import Path
from urllib.parse import parse_qs, urlencode, urlparse, urlunparse

# Third-party imports
import structlog

logger = structlog.get_logger(__name__)

__all__ = ["Cache", "url_to_hash"]

_TRACKING_PARAMS = frozenset({"fbclid", "gclid", "ref", "source"})


def _normalize_url(url: str) -> str:
    """Strip tracking query parameters and normalize scheme/host to lowercase."""
    parsed = urlparse(url)
    params = parse_qs(parsed.query, keep_blank_values=True)
    filtered = {
        k: v for k, v in params.items() if not k.startswith("utm_") and k not in _TRACKING_PARAMS
    }
    clean_query = urlencode(filtered, doseq=True)
    normalized = parsed._replace(
        scheme=parsed.scheme.lower(),
        netloc=parsed.netloc.lower(),
        query=clean_query,
    )
    return urlunparse(normalized)


def url_to_hash(url: str) -> str:
    """Return a hex SHA-256 of the normalized URL (tracking params stripped).

    This is the canonical hash scheme used by both the deduplicator and the cache.
    Use this function everywhere a URL needs to be stored or looked up in the cache.
    """
    return hashlib.sha256(_normalize_url(url).encode()).hexdigest()


_CREATE_TABLE_SQL = """
    CREATE TABLE IF NOT EXISTS seen_items (
        url_hash    TEXT NOT NULL,
        content_hash TEXT NOT NULL,
        seen_at     TEXT NOT NULL,
        PRIMARY KEY (url_hash, content_hash)
    )
"""

_INSERT_SQL = """
    INSERT OR IGNORE INTO seen_items (url_hash, content_hash, seen_at)
    VALUES (?, ?, ?)
"""


class Cache:
    """SQLite-backed deduplication cache.

    is_seen uses OR semantics: an item is seen if EITHER url_hash OR
    content_hash matches an entry in the cache.

    Connection management: each method opens and closes its own connection.
    sqlite3's context manager (`with connect(...) as conn`) handles transaction
    commit/rollback but does NOT close the connection — connections are released
    when the local variable goes out of scope. This is intentional: the pipeline
    is a short-lived daily batch process, so connection pooling is unnecessary.
    """

    def __init__(self, db_path: Path) -> None:
        """Open (or create) the SQLite database at db_path.

        Raises:
            FileNotFoundError: if the parent directory does not exist.
                The caller is responsible for creating the cache directory.
        """
        if not db_path.parent.exists():
            msg = f"Cache directory does not exist: {db_path.parent}"
            raise FileNotFoundError(msg)
        self._db_path = db_path
        self._init_db()

    def _init_db(self) -> None:
        """Create the seen_items table if it does not already exist."""
        with sqlite3.connect(self._db_path) as conn:
            conn.execute(_CREATE_TABLE_SQL)
            conn.commit()

    def is_seen(
        self,
        url_hash: str | None = None,
        content_hash: str | None = None,
    ) -> bool:
        """Return True if EITHER hash matches an entry in the cache (OR semantics).

        Phase 1 dedup: call with url_hash only.
        Phase 2 dedup: call with content_hash only.
        Both phases combined: call with both — returns True if either matches.
        """
        if url_hash is not None and content_hash is not None:
            sql = "SELECT 1 FROM seen_items WHERE url_hash = ? OR content_hash = ? LIMIT 1"
            row_params: tuple[str, ...] = (url_hash, content_hash)
        elif url_hash is not None:
            sql = "SELECT 1 FROM seen_items WHERE url_hash = ? LIMIT 1"
            row_params = (url_hash,)
        elif content_hash is not None:
            sql = "SELECT 1 FROM seen_items WHERE content_hash = ? LIMIT 1"
            row_params = (content_hash,)
        else:
            return False
        with sqlite3.connect(self._db_path) as conn:
            row = conn.execute(sql, row_params).fetchone()
        return row is not None

    def mark_seen(self, url_hash: str, content_hash: str) -> None:
        """Record a (url_hash, content_hash) pair as seen.

        Idempotent: calling twice with the same hashes does not raise or duplicate.
        Cache safety: pipeline.py is responsible for calling this only after
        successful digest generation (SPEC.md §4.4).
        """
        seen_at = datetime.now(tz=UTC).isoformat()
        with sqlite3.connect(self._db_path) as conn:
            conn.execute(_INSERT_SQL, (url_hash, content_hash, seen_at))
            conn.commit()

    def clear_all(self) -> None:
        """Delete all entries from the cache."""
        with sqlite3.connect(self._db_path) as conn:
            conn.execute("DELETE FROM seen_items")
            conn.commit()
        logger.info("cache_cleared")

    def stats(self) -> dict[str, object]:
        """Return cache statistics: entry_count, oldest, newest seen_at strings."""
        with sqlite3.connect(self._db_path) as conn:
            row = conn.execute(
                "SELECT COUNT(*), MIN(seen_at), MAX(seen_at) FROM seen_items"
            ).fetchone()
        count, oldest, newest = row or (0, None, None)
        return {"entry_count": count, "oldest": oldest, "newest": newest}

    def remove_url(self, url: str) -> bool:
        """Remove all cache entries for the given URL. Returns True if any were removed."""
        url_hash = url_to_hash(url)
        with sqlite3.connect(self._db_path) as conn:
            cursor = conn.execute("DELETE FROM seen_items WHERE url_hash = ?", (url_hash,))
            conn.commit()
        removed: bool = cursor.rowcount > 0
        logger.info("cache_remove_url", url=url, removed=removed)
        return removed

    def purge_expired(self, ttl_days: int) -> int:
        """Remove entries older than ttl_days. Returns the number of rows deleted.

        Boundary: entries seen exactly ttl_days ago are NOT purged (strictly older).
        Comparison is at date granularity to avoid floating-point boundary races.
        """
        cutoff = datetime.now(tz=UTC) - timedelta(days=ttl_days)
        cutoff_date = cutoff.strftime("%Y-%m-%d")
        with sqlite3.connect(self._db_path) as conn:
            cursor = conn.execute(
                "DELETE FROM seen_items WHERE substr(seen_at, 1, 10) < ?",
                (cutoff_date,),
            )
            conn.commit()
            deleted: int = cursor.rowcount
        logger.info("cache_purged", rows_deleted=deleted, ttl_days=ttl_days)
        return deleted
