"""Excerpt fetcher stage: fetches and extracts ~200-word excerpts from RawItems.

Stage: step 4 of preprocessing
Input:  list[RawItem]     (after Phase 1 dedup)
Output: list[ExcerptItem] (input to Phase 2 dedup and PreFilter)

For each RawItem:
- ArXiv items (content_type="arxiv"): use raw_content as excerpt directly,
  no HTTP fetch required.
- All other items: fetch item.url with httpx, extract clean text with
  trafilatura, truncate to ~200 words.

Items where extraction yields < 50 words are treated as paywall/extraction
failures, logged at INFO, and excluded from output.

Computes url_hash (reusing url_to_hash from deduplicator) and content_hash
(SHA-256 of excerpt text) for each output item.

Spec reference: SPEC.md §3.2 step 4, §3.7 (paywall threshold), §6.3 (60s timeout)."""

# 1. Standard library imports
import hashlib
import time

# 2. Third-party imports
import httpx
import structlog
import trafilatura

# 3. Internal imports — retry config
_MAX_RETRIES = 3
_RETRY_BACKOFF_BASE = 2  # seconds; doubles each attempt

# 3. Internal imports
from radar.cache import url_to_hash
from radar.models import ExcerptItem, RawItem

# 4. Module-level logger
logger = structlog.get_logger(__name__)

# 5. Constants
_FETCH_TIMEOUT_SECONDS = 60
_MIN_WORDS = 50
_MAX_EXCERPT_WORDS = 200


def excerpt_fetcher(items: list[RawItem]) -> list[ExcerptItem]:
    """Fetch and extract excerpts for each RawItem, returning ExcerptItems."""
    start = time.monotonic()
    result: list[ExcerptItem] = []
    skipped_paywall = 0

    for item in items:
        excerpt = _get_excerpt(item)
        if excerpt is None:
            skipped_paywall += 1
            continue
        result.append(
            ExcerptItem(
                url=item.url,
                title=item.title,
                source=item.source,
                published_at=item.published_at,
                excerpt=excerpt,
                url_hash=url_to_hash(item.url),
                content_hash=hashlib.sha256(excerpt.encode()).hexdigest(),
            )
        )

    elapsed_ms = int((time.monotonic() - start) * 1000)
    logger.info(
        "excerpt_fetch_complete",
        input=len(items),
        fetched=len(result),
        skipped_paywall=skipped_paywall,
        elapsed_ms=elapsed_ms,
    )
    return result


def _get_excerpt(item: RawItem) -> str | None:
    """Return a truncated excerpt string, or None if extraction failed/paywalled."""
    if item.content_type == "arxiv":
        text: str = item.raw_content
    else:
        fetched = _fetch_and_extract(item.url)
        if fetched is None:
            return None
        text = fetched

    if not text or len(text.split()) < _MIN_WORDS:
        logger.info("excerpt_skipped_paywall", url=item.url)
        return None

    return _truncate(text)


def _fetch_and_extract(url: str) -> str | None:
    """Fetch URL and extract clean text with trafilatura. Returns None on failure."""
    for attempt in range(_MAX_RETRIES + 1):
        try:
            response = httpx.get(url, timeout=_FETCH_TIMEOUT_SECONDS, follow_redirects=True)
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code == 429 and attempt < _MAX_RETRIES:
                wait = int(exc.response.headers.get("Retry-After", _RETRY_BACKOFF_BASE ** (attempt + 1)))
                logger.info("excerpt_fetch_rate_limited", url=url, attempt=attempt + 1, wait_s=wait)
                time.sleep(wait)
                continue
            logger.warning("excerpt_fetch_http_error", url=url, error=str(exc))
            return None
        except httpx.TimeoutException as exc:
            logger.warning("excerpt_fetch_timeout", url=url, error=str(exc))
            return None
        except httpx.ConnectError as exc:
            logger.warning("excerpt_fetch_connect_error", url=url, error=str(exc))
            return None
        else:
            break
    else:
        logger.warning("excerpt_fetch_rate_limited_giving_up", url=url)
        return None

    extracted: str | None = trafilatura.extract(response.text)
    return extracted


def _truncate(text: str) -> str:
    """Truncate text to at most _MAX_EXCERPT_WORDS words."""
    words = text.split()
    if len(words) <= _MAX_EXCERPT_WORDS:
        return text
    return " ".join(words[:_MAX_EXCERPT_WORDS])
