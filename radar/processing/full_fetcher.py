"""Full article fetcher stage: fetches complete article text for Pass 1 survivors.

Stage: step 7 of the pipeline (Full Article Fetcher)
Input:  list[ScoredItem]  (output of Summarizer / Pass 1 relevance filter)
Output: list[FullItem]    (input to Truncator)

For each ScoredItem, fetches the full article body via httpx and extracts
clean text with trafilatura. Carries score and summary unchanged from the
ScoredItem. Articles where extraction yields < 50 words or returns None
are treated as paywall/extraction failures and excluded from output.
HTTPStatusError, TimeoutException, and ConnectError are caught per-item;
the pipeline continues with remaining items.

Spec reference: SPEC.md §3.2 step 7, §3.7 (paywall threshold).
"""

# 1. Standard library imports
import time

# 2. Third-party imports
import httpx
import structlog
import trafilatura

_MAX_RETRIES = 3
_RETRY_BACKOFF_BASE = 2  # seconds; doubles each attempt

# 3. Internal imports
from radar.config import PipelineConfig
from radar.models import FullItem, ScoredItem

# 4. Module-level logger
logger = structlog.get_logger(__name__)

# 5. Constants
_FETCH_TIMEOUT_SECONDS = 30
_MIN_WORDS = 50


class FullFetcher:
    """Fetches full article text for each ScoredItem."""

    def __init__(self, config: PipelineConfig) -> None:
        self._config = config

    def fetch(self, items: list[ScoredItem]) -> list[FullItem]:
        """Fetch full text for each item, returning FullItems."""
        if not items:
            return []

        start = time.monotonic()
        result: list[FullItem] = []
        skipped_paywall = 0

        for item in items:
            full_text = _fetch_and_extract(item.url, self._config.user_agent)
            if full_text is None:
                skipped_paywall += 1
                logger.info("full_fetch_skipped_paywall", url=item.url)
                continue

            word_count = len(full_text.split())
            if word_count < _MIN_WORDS:
                skipped_paywall += 1
                logger.info("full_fetch_skipped_short", url=item.url, word_count=word_count)
                continue

            result.append(
                FullItem(
                    url=item.url,
                    title=item.title,
                    source=item.source,
                    published_at=item.published_at,
                    full_text=full_text,
                    word_count=word_count,
                    score=item.score,
                    summary=item.summary,
                )
            )

        elapsed_ms = int((time.monotonic() - start) * 1000)
        logger.info(
            "full_fetch_complete",
            input=len(items),
            fetched=len(result),
            skipped_paywall=skipped_paywall,
            elapsed_ms=elapsed_ms,
        )
        return result


def _fetch_and_extract(url: str, user_agent: str) -> str | None:
    """Fetch URL and extract clean text with trafilatura. Returns None on failure."""
    for attempt in range(_MAX_RETRIES + 1):
        try:
            response = httpx.get(
                url,
                timeout=_FETCH_TIMEOUT_SECONDS,
                headers={"User-Agent": user_agent},
                follow_redirects=True,
            )
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code == 429 and attempt < _MAX_RETRIES:
                wait = int(exc.response.headers.get("Retry-After", _RETRY_BACKOFF_BASE ** (attempt + 1)))
                logger.info("full_fetch_rate_limited", url=url, attempt=attempt + 1, wait_s=wait)
                time.sleep(wait)
                continue
            logger.warning("full_fetch_http_error", url=url, error=str(exc))
            return None
        except httpx.TimeoutException as exc:
            logger.warning("full_fetch_timeout", url=url, error=str(exc))
            return None
        except httpx.ConnectError as exc:
            logger.warning("full_fetch_connection_error", url=url, error=str(exc))
            return None
        else:
            break
    else:
        logger.warning("full_fetch_rate_limited_giving_up", url=url)
        return None

    try:
        extracted: str | None = trafilatura.extract(response.text)
    except Exception as exc:  # noqa: BLE001
        logger.warning("full_fetch_extract_error", url=url, error=str(exc))
        return None
    return extracted
