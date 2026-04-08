"""Hacker News source connector for ai-radar.

Stage: source fetch (step 1 of pipeline)
Input:  HackerNewsConfig
Output: list[RawItem] (content_type="web")

Fetches recent HN stories via the Algolia search API, filters by min_score
and keywords, and maps each story to a RawItem. Lookback window: 24 hours
(fixed per SPEC.md decision #2 — matches daily pipeline cadence).

Spec reference: SPEC.md §3.1 (Hacker News connector), §6.3 (60s timeout).
"""

# Standard library imports
import time
from datetime import UTC, datetime

# Third-party imports
import httpx
import structlog

# Internal imports
from radar.config import HackerNewsConfig
from radar.models import RawItem
from radar.sources.base import Source

logger = structlog.get_logger(__name__)

_ALGOLIA_URL = "https://hn.algolia.com/api/v1/search_by_date"
_FETCH_TIMEOUT_SECONDS = 60
_LOOKBACK_SECONDS = 24 * 60 * 60


class HNSource(Source):
    """Hacker News source connector via Algolia search API.

    Returns stories from the last 24 hours filtered by min_score and keywords.
    Single fetch failures are caught, logged, and return [].
    """

    def __init__(self, config: HackerNewsConfig) -> None:
        self._config = config

    def fetch(self) -> list[RawItem]:
        """Fetch and return recent HN stories matching config filters.

        Returns an empty list if the connector is disabled or the fetch fails.
        Never raises — HTTP errors and timeouts are caught, logged, and skipped.
        """
        if not self._config.enabled:
            return []

        start = time.monotonic()
        url = _build_url(self._config)

        try:
            response = httpx.get(url, timeout=_FETCH_TIMEOUT_SECONDS)
            response.raise_for_status()
        except httpx.TimeoutException as exc:
            logger.warning("hn_fetch_failed", error=str(exc))
            return []
        except httpx.ConnectError as exc:
            logger.warning("hn_fetch_failed", error=str(exc))
            return []
        except httpx.HTTPStatusError as exc:
            logger.warning("hn_fetch_failed", status_code=exc.response.status_code, error=str(exc))
            return []

        hits: list[dict[str, object]] = response.json().get("hits", [])
        items: list[RawItem] = []
        for hit in hits:
            item = _hit_to_raw_item(hit)
            if item is not None:
                items.append(item)

        elapsed_ms = int((time.monotonic() - start) * 1000)
        logger.info(
            "source_fetch_complete",
            source="hackernews",
            item_count=len(items),
            elapsed_ms=elapsed_ms,
        )
        return items


def _build_url(config: HackerNewsConfig) -> str:
    """Construct the Algolia search URL with filters."""
    since = int(datetime.now(tz=UTC).timestamp()) - _LOOKBACK_SECONDS
    numeric_filters = f"points>={config.min_score},created_at_i>={since}"
    params = f"tags=story&numericFilters={numeric_filters}"
    if config.keywords:
        query = " ".join(config.keywords)
        params += f"&query={query}"
    return f"{_ALGOLIA_URL}?{params}"


def _hit_to_raw_item(hit: dict[str, object]) -> RawItem | None:
    """Map an Algolia hit dict to a RawItem, or return None to skip."""
    url = str(hit.get("url", ""))
    if not url:
        logger.debug("hn_hit_missing_url", object_id=hit.get("objectID", ""))
        return None

    title = str(hit.get("title", ""))
    if not title:
        logger.warning("hn_hit_missing_title", url=url, object_id=hit.get("objectID", ""))
        return None

    published_at = datetime.fromtimestamp(float(str(hit["created_at_i"])), tz=UTC)
    raw_content = str(hit.get("story_text") or "")

    return RawItem(
        url=url,
        title=title,
        source="hackernews",
        published_at=published_at,
        raw_content=raw_content,
        content_type="web",
    )
