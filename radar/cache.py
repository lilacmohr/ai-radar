"""URL/content deduplication cache backed by SQLite.

Stub — no implementation yet. See [IMPL] issue #19.
"""

from pathlib import Path


class Cache:
    """SQLite-backed dedup cache. Stub — methods are no-ops."""

    def __init__(self, db_path: Path) -> None:
        self._db_path = db_path

    def is_seen(
        self,
        url_hash: str | None = None,  # noqa: ARG002
        content_hash: str | None = None,  # noqa: ARG002
    ) -> bool:
        """Return True if the hash is in the cache. Stub — always returns False."""
        return False

    def mark_seen(self, url_hash: str, content_hash: str) -> None:
        """Mark an item as seen. Stub — no-op."""

    def purge_expired(self, ttl_days: int) -> int:  # noqa: ARG002
        """Remove entries older than ttl_days. Stub — returns 0."""
        return 0
