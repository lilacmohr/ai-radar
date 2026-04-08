"""Tests for radar/cache.py — SQLite-backed URL/content deduplication cache.

All tests in this file are expected to FAIL (red) until radar/cache.py
is implemented. See paired [IMPL] issue #19.

Spec reference: SPEC.md §4.4 (caching & deduplication — schema, TTL,
two-phase dedup, cache safety rule).

Cache safety rule (SPEC.md §4.4): items are marked seen ONLY after a
successful digest generation — never at fetch time. This makes every run
safely re-runnable after any failure. cache.py does NOT enforce ordering;
pipeline.py is responsible for calling mark_seen at the right time.
"""

import sqlite3
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from radar.cache import Cache

# ---------------------------------------------------------------------------
# Shared test constants
# ---------------------------------------------------------------------------

URL_HASH_A = "url_hash_abc123"
CONTENT_HASH_A = "content_hash_def456"
URL_HASH_B = "url_hash_xyz789"
CONTENT_HASH_B = "content_hash_uvw012"
TTL_DAYS = 30


# ---------------------------------------------------------------------------
# Initialization
# ---------------------------------------------------------------------------


def test_cache_init_creates_db_file(temp_cache_dir: Path) -> None:
    db_path = temp_cache_dir / "radar.db"
    Cache(db_path)
    assert db_path.exists()


def test_cache_init_creates_seen_items_table(temp_cache_dir: Path) -> None:
    db_path = temp_cache_dir / "radar.db"
    Cache(db_path)
    conn = sqlite3.connect(db_path)
    tables = conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
    conn.close()
    table_names = [row[0] for row in tables]
    assert "seen_items" in table_names


def test_cache_init_connects_to_existing_db_without_recreating(
    temp_cache_dir: Path,
) -> None:
    """Opening Cache twice on the same path must not lose existing data."""
    db_path = temp_cache_dir / "radar.db"
    # First open: creates DB and marks an item
    cache = Cache(db_path)
    cache.mark_seen(url_hash=URL_HASH_A, content_hash=CONTENT_HASH_A)
    # Second open: must see the previously marked item
    cache2 = Cache(db_path)
    assert cache2.is_seen(url_hash=URL_HASH_A)


def test_cache_seen_items_table_has_exactly_three_columns(
    temp_cache_dir: Path,
) -> None:
    """Schema must have url_hash, content_hash, seen_at — no extra columns.

    SPEC.md §4.4 does not include raw_content in the cache schema.
    """
    db_path = temp_cache_dir / "radar.db"
    Cache(db_path)
    conn = sqlite3.connect(db_path)
    columns = conn.execute("PRAGMA table_info(seen_items)").fetchall()
    conn.close()
    column_names = [col[1] for col in columns]
    expected_columns = {"url_hash", "content_hash", "seen_at"}
    assert set(column_names) == expected_columns
    assert len(column_names) == len(expected_columns)


def test_cache_seen_items_has_no_raw_content_column(temp_cache_dir: Path) -> None:
    """raw_content must NOT be stored in the cache per SPEC.md §4.4."""
    db_path = temp_cache_dir / "radar.db"
    Cache(db_path)
    conn = sqlite3.connect(db_path)
    columns = conn.execute("PRAGMA table_info(seen_items)").fetchall()
    conn.close()
    column_names = [col[1] for col in columns]
    assert "raw_content" not in column_names


def test_cache_init_raises_when_db_directory_does_not_exist(
    temp_cache_dir: Path,
) -> None:
    """Caller is responsible for creating the cache/ directory.

    Cache must not silently create parent directories — it must raise
    a clear error so the caller knows the directory is missing.
    """
    missing_dir = temp_cache_dir / "nonexistent_subdir"
    db_path = missing_dir / "radar.db"
    with pytest.raises(Exception, match=r"."):  # directory does not exist
        Cache(db_path)


# ---------------------------------------------------------------------------
# is_seen
# ---------------------------------------------------------------------------


def test_is_seen_returns_false_for_unknown_url_hash(temp_cache_dir: Path) -> None:
    db_path = temp_cache_dir / "radar.db"
    cache = Cache(db_path)
    assert cache.is_seen(url_hash=URL_HASH_A) is False


def test_is_seen_returns_false_for_unknown_content_hash(temp_cache_dir: Path) -> None:
    db_path = temp_cache_dir / "radar.db"
    cache = Cache(db_path)
    assert cache.is_seen(content_hash=CONTENT_HASH_A) is False


def test_is_seen_returns_false_on_freshly_initialized_empty_cache(
    temp_cache_dir: Path,
) -> None:
    """Any hash on an empty cache must return False — never True."""
    db_path = temp_cache_dir / "radar.db"
    cache = Cache(db_path)
    assert cache.is_seen(url_hash="any_hash") is False
    assert cache.is_seen(content_hash="any_hash") is False


# ---------------------------------------------------------------------------
# mark_seen + is_seen (the core dedup contract)
# ---------------------------------------------------------------------------


def test_mark_seen_makes_url_hash_visible(temp_cache_dir: Path) -> None:
    db_path = temp_cache_dir / "radar.db"
    cache = Cache(db_path)
    cache.mark_seen(url_hash=URL_HASH_A, content_hash=CONTENT_HASH_A)
    assert cache.is_seen(url_hash=URL_HASH_A) is True


def test_mark_seen_makes_content_hash_visible(temp_cache_dir: Path) -> None:
    db_path = temp_cache_dir / "radar.db"
    cache = Cache(db_path)
    cache.mark_seen(url_hash=URL_HASH_A, content_hash=CONTENT_HASH_A)
    assert cache.is_seen(content_hash=CONTENT_HASH_A) is True


def test_is_seen_matches_on_url_hash_alone(temp_cache_dir: Path) -> None:
    """An item is seen if its URL hash matches — content hash need not match.

    Phase 1 dedup (URL hash) is independent of Phase 2 dedup (content hash).
    """
    db_path = temp_cache_dir / "radar.db"
    cache = Cache(db_path)
    cache.mark_seen(url_hash=URL_HASH_A, content_hash=CONTENT_HASH_A)
    # Different content hash — but same URL hash: should be seen
    assert cache.is_seen(url_hash=URL_HASH_A) is True


def test_is_seen_matches_on_content_hash_alone(temp_cache_dir: Path) -> None:
    """An item is seen if its content hash matches — URL hash need not match.

    Catches the same article published at different URLs (Phase 2 dedup).
    """
    db_path = temp_cache_dir / "radar.db"
    cache = Cache(db_path)
    cache.mark_seen(url_hash=URL_HASH_A, content_hash=CONTENT_HASH_A)
    # Different URL hash, same content hash: should still be seen
    assert cache.is_seen(content_hash=CONTENT_HASH_A) is True


def test_is_seen_or_semantics_when_both_hashes_provided(
    temp_cache_dir: Path,
) -> None:
    """is_seen uses OR logic: seen if EITHER hash matches, not both required.

    Concrete case: url_hash matches (in cache), content_hash does not (not in cache).
    Result must be True — the url_hash match alone is sufficient.
    This mirrors Phase 1 dedup: a URL already seen blocks re-fetch regardless of
    whether its content hash was also stored.
    """
    db_path = temp_cache_dir / "radar.db"
    cache = Cache(db_path)
    cache.mark_seen(url_hash=URL_HASH_A, content_hash=CONTENT_HASH_A)
    # url_hash_A is in cache; content_hash_B is NOT in cache
    assert cache.is_seen(url_hash=URL_HASH_A, content_hash=CONTENT_HASH_B) is True


def test_is_seen_returns_false_when_neither_hash_matches(
    temp_cache_dir: Path,
) -> None:
    """is_seen returns False when both hashes are provided and neither is in cache."""
    db_path = temp_cache_dir / "radar.db"
    cache = Cache(db_path)
    cache.mark_seen(url_hash=URL_HASH_A, content_hash=CONTENT_HASH_A)
    assert cache.is_seen(url_hash=URL_HASH_B, content_hash=CONTENT_HASH_B) is False


def test_is_seen_returns_false_for_different_url_hash(temp_cache_dir: Path) -> None:
    db_path = temp_cache_dir / "radar.db"
    cache = Cache(db_path)
    cache.mark_seen(url_hash=URL_HASH_A, content_hash=CONTENT_HASH_A)
    assert cache.is_seen(url_hash=URL_HASH_B) is False


def test_is_seen_returns_false_for_different_content_hash(
    temp_cache_dir: Path,
) -> None:
    db_path = temp_cache_dir / "radar.db"
    cache = Cache(db_path)
    cache.mark_seen(url_hash=URL_HASH_A, content_hash=CONTENT_HASH_A)
    assert cache.is_seen(content_hash=CONTENT_HASH_B) is False


def test_mark_seen_is_idempotent(temp_cache_dir: Path) -> None:
    """Calling mark_seen twice with the same hashes must not raise.

    Uses INSERT OR IGNORE — duplicates are silently discarded.
    """
    db_path = temp_cache_dir / "radar.db"
    cache = Cache(db_path)
    cache.mark_seen(url_hash=URL_HASH_A, content_hash=CONTENT_HASH_A)
    # Second call: must not raise
    cache.mark_seen(url_hash=URL_HASH_A, content_hash=CONTENT_HASH_A)
    # Still seen — only one row, not two
    assert cache.is_seen(url_hash=URL_HASH_A) is True


def test_mark_seen_does_not_raise_in_isolation() -> None:
    """Cache safety rule: mark_seen is valid to call at any time.

    pipeline.py controls WHEN mark_seen is called (after successful digest).
    cache.py must not enforce ordering — it just stores what it's told.
    """
    # This test verifies mark_seen is callable without context.
    # It uses an in-memory SQLite path via a real temp dir, checked separately.
    # The key assertion: no exception is raised.
    import tempfile  # noqa: PLC0415

    with tempfile.TemporaryDirectory() as tmp:
        db = Path(tmp) / "radar.db"
        cache = Cache(db)
        cache.mark_seen(url_hash="any_url_hash", content_hash="any_content_hash")


# ---------------------------------------------------------------------------
# purge_expired
# ---------------------------------------------------------------------------


def test_purge_expired_removes_entries_older_than_ttl(temp_cache_dir: Path) -> None:
    db_path = temp_cache_dir / "radar.db"
    cache = Cache(db_path)
    # Insert an entry directly with an old seen_at timestamp
    old_seen_at = (datetime.now(tz=UTC) - timedelta(days=TTL_DAYS + 1)).isoformat()
    conn = sqlite3.connect(db_path)
    conn.execute(
        "INSERT INTO seen_items (url_hash, content_hash, seen_at) VALUES (?, ?, ?)",
        (URL_HASH_A, CONTENT_HASH_A, old_seen_at),
    )
    conn.commit()
    conn.close()
    purged = cache.purge_expired(ttl_days=TTL_DAYS)
    assert purged >= 1
    assert cache.is_seen(url_hash=URL_HASH_A) is False


def test_purge_expired_does_not_remove_fresh_entries(temp_cache_dir: Path) -> None:
    db_path = temp_cache_dir / "radar.db"
    cache = Cache(db_path)
    cache.mark_seen(url_hash=URL_HASH_A, content_hash=CONTENT_HASH_A)
    purged = cache.purge_expired(ttl_days=TTL_DAYS)
    assert purged == 0
    assert cache.is_seen(url_hash=URL_HASH_A) is True


def test_purge_expired_on_empty_table_completes_without_error(
    temp_cache_dir: Path,
) -> None:
    db_path = temp_cache_dir / "radar.db"
    cache = Cache(db_path)
    purged = cache.purge_expired(ttl_days=TTL_DAYS)
    assert purged == 0


def test_purge_expired_does_not_remove_entry_at_exact_ttl_boundary(
    temp_cache_dir: Path,
) -> None:
    """Entry seen exactly TTL_DAYS ago must NOT be purged.

    Guards against an off-by-one bug where >= TTL_DAYS is used instead of
    > TTL_DAYS, which would resurface already-seen articles from exactly 30 days ago.
    """
    db_path = temp_cache_dir / "radar.db"
    cache = Cache(db_path)
    boundary_seen_at = (datetime.now(tz=UTC) - timedelta(days=TTL_DAYS)).isoformat()
    conn = sqlite3.connect(db_path)
    conn.execute(
        "INSERT INTO seen_items (url_hash, content_hash, seen_at) VALUES (?, ?, ?)",
        (URL_HASH_A, CONTENT_HASH_A, boundary_seen_at),
    )
    conn.commit()
    conn.close()
    purged = cache.purge_expired(ttl_days=TTL_DAYS)
    assert purged == 0
    assert cache.is_seen(url_hash=URL_HASH_A) is True


def test_purge_expired_returns_count_of_purged_rows(temp_cache_dir: Path) -> None:
    """purge_expired must return the number of rows deleted."""
    db_path = temp_cache_dir / "radar.db"
    cache = Cache(db_path)
    old_seen_at = (datetime.now(tz=UTC) - timedelta(days=TTL_DAYS + 1)).isoformat()
    conn = sqlite3.connect(db_path)
    conn.executemany(
        "INSERT INTO seen_items (url_hash, content_hash, seen_at) VALUES (?, ?, ?)",
        [
            (URL_HASH_A, CONTENT_HASH_A, old_seen_at),
            (URL_HASH_B, CONTENT_HASH_B, old_seen_at),
        ],
    )
    conn.commit()
    conn.close()
    purged = cache.purge_expired(ttl_days=TTL_DAYS)
    assert purged == 2  # noqa: PLR2004


# ---------------------------------------------------------------------------
# Resilience
# ---------------------------------------------------------------------------


def test_cache_starts_clean_after_db_file_deleted_and_recreated(
    temp_cache_dir: Path,
) -> None:
    """Deleting the DB file and reopening Cache must start fresh — no error."""
    db_path = temp_cache_dir / "radar.db"
    cache = Cache(db_path)
    cache.mark_seen(url_hash=URL_HASH_A, content_hash=CONTENT_HASH_A)
    # Delete the file
    db_path.unlink()
    # Recreate — must create a new file and start clean
    cache2 = Cache(db_path)
    assert db_path.exists()
    assert cache2.is_seen(url_hash=URL_HASH_A) is False
