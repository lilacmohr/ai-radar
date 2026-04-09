"""ArXiv source connector for ai-radar.

Stage: source fetch (step 1 of pipeline)
Input:  ArxivConfig
Output: list[RawItem] (content_type="arxiv")

Queries the ArXiv API for recent paper submissions in configured categories.
Maps each paper to a RawItem with content_type="arxiv" and the abstract as
raw_content. The Excerpt Fetcher (P3.7) will bypass HTTP fetch for these items
and use raw_content directly as the excerpt.

Spec reference: SPEC.md §3.1 (ArXiv connector), §6.3 (60s timeout).
"""

# 1. Standard library imports
import calendar
import socket
import time
import urllib.error
from datetime import UTC, datetime

# 2. Third-party imports
import feedparser
import structlog

# 3. Internal imports
from radar.config import ArxivConfig
from radar.models import RawItem
from radar.sources.base import Source

# 4. Module-level logger
logger = structlog.get_logger(__name__)

# 5. Constants
_FETCH_TIMEOUT_SECONDS = 60
_ARXIV_API_URL = "http://export.arxiv.org/api/query"


class ArxivSource(Source):
    """ArXiv source connector.

    Queries the ArXiv API for recent papers in configured categories and maps
    each entry to a RawItem with content_type="arxiv". The abstract is stored
    as raw_content; excerpt_fetcher will use it directly without an HTTP fetch.
    """

    def __init__(self, config: ArxivConfig) -> None:
        self._config = config

    def fetch(self) -> list[RawItem]:
        """Fetch recent ArXiv papers for configured categories.

        Returns an empty list if the connector is disabled, no categories are
        configured, or the API call fails. Never raises.
        """
        if not self._config.enabled:
            return []
        if not self._config.categories:
            return []

        start = time.monotonic()
        url = _build_url(self._config.categories)

        try:
            socket.setdefaulttimeout(_FETCH_TIMEOUT_SECONDS)
            result = feedparser.parse(url)
        except (urllib.error.URLError, TimeoutError) as exc:
            logger.warning("arxiv_fetch_failed", error=str(exc))
            return []
        finally:
            socket.setdefaulttimeout(None)

        items: list[RawItem] = []
        for entry in result.get("entries", []):
            item = _entry_to_raw_item(entry)
            if item is not None:
                items.append(item)

        elapsed_ms = int((time.monotonic() - start) * 1000)
        logger.info(
            "source_fetch_complete",
            source="arxiv",
            item_count=len(items),
            elapsed_ms=elapsed_ms,
        )
        return items


def _build_url(categories: list[str]) -> str:
    """Build the ArXiv API query URL for the given categories."""
    search_query = "+OR+".join(f"cat:{cat}" for cat in categories)
    return (
        f"{_ARXIV_API_URL}"
        f"?search_query={search_query}"
        f"&max_results=25"
        f"&sortBy=submittedDate"
        f"&sortOrder=descending"
    )


def _entry_to_raw_item(entry: dict[str, object]) -> RawItem | None:
    """Map a feedparser entry dict to a RawItem, or return None to skip.

    Skips entries missing a link or title. Missing summary produces raw_content="".
    """
    link = entry.get("link")
    if not link:
        logger.warning("arxiv_entry_missing_link")
        return None

    title_val = entry.get("title", "")
    title = str(title_val).strip()
    if not title:
        logger.warning("arxiv_entry_missing_title", url=str(link))
        return None

    raw_content = str(entry.get("summary", ""))
    published_parsed = entry.get("published_parsed")
    published_at = _parse_published_at(
        published_parsed if isinstance(published_parsed, time.struct_time) else None
    )

    return RawItem(
        url=str(link),
        title=title,
        source="arxiv",
        published_at=published_at,
        raw_content=raw_content,
        content_type="arxiv",
    )


def _parse_published_at(published_parsed: time.struct_time | None) -> datetime:
    """Convert a feedparser UTC struct_time to a timezone-aware datetime.

    Falls back to now(UTC) if published_parsed is absent.
    """
    if published_parsed is None:
        return datetime.now(tz=UTC)
    return datetime.fromtimestamp(calendar.timegm(published_parsed), tz=UTC)
