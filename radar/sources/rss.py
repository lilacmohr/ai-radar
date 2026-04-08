"""RSS/Atom source connector for ai-radar.

Stage: source fetch (step 1 of pipeline)
Input:  RssFeedsConfig
Output: list[RawItem] (content_type="web")

Fetches entries from one or more configured RSS/Atom feeds via feedparser,
maps each entry to a RawItem, and returns a single flat list. Full article
content is NOT fetched here — that is excerpt_fetcher.py (P3.7).

Spec reference: SPEC.md §3.1 (RSS/Atom connector), §3.2 step 1, §6.3 (60s timeout).
"""

# Standard library imports
import calendar
import socket
import time
import urllib.error
from datetime import UTC, datetime

# Third-party imports
import feedparser
import structlog

# Internal imports
from radar.config import RssFeedsConfig
from radar.models import RawItem
from radar.sources.base import Source

logger = structlog.get_logger(__name__)

_FETCH_TIMEOUT_SECONDS = 60


class RSSSource(Source):
    """RSS/Atom source connector.

    Iterates configured feeds, parses each with feedparser, and maps entries
    to RawItem. Single feed failures are logged and skipped; the pipeline
    continues with remaining feeds.
    """

    def __init__(self, config: RssFeedsConfig) -> None:
        self._config = config

    def fetch(self) -> list[RawItem]:
        """Fetch and return all items from configured RSS/Atom feeds.

        Returns an empty list if the connector is disabled or all feeds fail.
        Never raises — single-feed errors are caught, logged, and skipped.
        """
        if not self._config.enabled:
            return []

        start = time.monotonic()
        items: list[RawItem] = []
        failed = 0

        for feed in self._config.feeds:
            try:
                socket.setdefaulttimeout(_FETCH_TIMEOUT_SECONDS)
                result = feedparser.parse(feed.url)
            except (urllib.error.URLError, TimeoutError) as exc:
                logger.warning(
                    "rss_feed_fetch_failed",
                    feed=feed.name,
                    url=feed.url,
                    error=str(exc),
                )
                failed += 1
                continue
            finally:
                socket.setdefaulttimeout(None)

            for entry in result.get("entries", []):
                item = _entry_to_raw_item(entry, feed.name)
                if item is not None:
                    items.append(item)

        if self._config.feeds and failed == len(self._config.feeds):
            logger.error("rss_all_feeds_failed", feed_count=len(self._config.feeds))

        elapsed_ms = int((time.monotonic() - start) * 1000)
        logger.info(
            "source_fetch_complete", source="rss", item_count=len(items), elapsed_ms=elapsed_ms
        )

        return items


def _entry_to_raw_item(entry: dict[str, object], feed_name: str) -> RawItem | None:
    """Map a feedparser entry dict to a RawItem, or return None to skip.

    Skips entries missing a title — title is required for Pass 1 excerpt
    construction and cannot be substituted with an empty string.
    """
    title_val = entry.get("title", "")
    title = str(title_val).strip()
    if not title:
        logger.warning(
            "rss_entry_missing_title",
            feed=feed_name,
            url=entry.get("link", ""),
        )
        return None

    url = str(entry.get("link", ""))
    raw_content = str(entry.get("summary", ""))
    published_parsed = entry.get("published_parsed")
    published_at = _parse_published_at(
        published_parsed if isinstance(published_parsed, time.struct_time) else None
    )

    return RawItem(
        url=url,
        title=title,
        source=feed_name,
        published_at=published_at,
        raw_content=raw_content,
        content_type="web",
    )


def _parse_published_at(published_parsed: time.struct_time | None) -> datetime:
    """Convert a feedparser UTC struct_time to a timezone-aware datetime.

    Falls back to now(UTC) if published_parsed is absent.
    """
    if published_parsed is None:
        return datetime.now(tz=UTC)
    return datetime.fromtimestamp(calendar.timegm(published_parsed), tz=UTC)
