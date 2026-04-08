"""Deduplication stage: two-phase URL and content hash filtering.

Phase 1 — dedup_by_url: filters list[RawItem] against url_hash cache entries.
  Normalizes each item's URL (strips utm_* and other tracking params), computes
  SHA-256, and skips items whose hash exists in the cache OR appeared earlier
  in the same batch (within-batch dedup).

Phase 2 — dedup_by_content: filters list[ExcerptItem] against content_hash entries.
  ExcerptItem already carries content_hash (computed by excerpt_fetcher). Skips
  items whose hash exists in the cache OR appeared earlier in the same batch.

Items are checked against the cache but NOT marked as seen here.
cache.mark_seen() is called by pipeline.py only after successful digest generation
(SPEC.md §4.4, CLAUDE.md §5 cache safety rule).

Stage: Phase 1 after source fetch; Phase 2 after excerpt fetch, before PreFilter.
Spec reference: SPEC.md §3.2 steps 2 and 5, §4.4.
"""

# 1. Standard library imports
import hashlib
from urllib.parse import parse_qs, urlencode, urlparse, urlunparse

# 2. Third-party imports
import structlog

# 3. Internal imports
from radar.cache import Cache
from radar.models import ExcerptItem, RawItem

# 4. Module-level logger
logger = structlog.get_logger(__name__)

# 5. Constants
_TRACKING_PARAMS = frozenset({"fbclid", "gclid", "ref", "source"})


def url_to_hash(url: str) -> str:
    """Return a hex hash of the normalized URL (tracking params stripped)."""
    normalized = _normalize_url(url)
    return hashlib.sha256(normalized.encode()).hexdigest()


def dedup_by_url(items: list[RawItem], cache: Cache) -> list[RawItem]:
    """Filter RawItems to those whose url_hash has not been seen.

    Checks both the persistent cache and hashes seen earlier in this batch,
    so within-batch duplicates (e.g. same article via utm-tagged and clean URL)
    are also filtered.
    """
    if not items:
        return []

    seen_in_batch: set[str] = set()
    result: list[RawItem] = []

    for item in items:
        h = url_to_hash(item.url)
        if h in seen_in_batch or cache.is_seen(url_hash=h):
            continue
        seen_in_batch.add(h)
        result.append(item)

    logger.info(
        "dedup_complete",
        phase=1,
        input=len(items),
        output=len(result),
        duplicates_removed=len(items) - len(result),
    )
    return result


def dedup_by_content(items: list[ExcerptItem], cache: Cache) -> list[ExcerptItem]:
    """Filter ExcerptItems to those whose content_hash has not been seen.

    Checks both the persistent cache and hashes seen earlier in this batch,
    so within-batch duplicates (same article at two different URLs) are filtered.
    """
    if not items:
        return []

    seen_in_batch: set[str] = set()
    result: list[ExcerptItem] = []

    for item in items:
        h = item.content_hash
        if h in seen_in_batch or cache.is_seen(content_hash=h):
            continue
        seen_in_batch.add(h)
        result.append(item)

    logger.info(
        "dedup_complete",
        phase=2,
        input=len(items),
        output=len(result),
        duplicates_removed=len(items) - len(result),
    )
    return result


def _normalize_url(url: str) -> str:
    """Strip tracking query parameters and normalize scheme/host to lowercase."""
    parsed = urlparse(url)
    params = parse_qs(parsed.query, keep_blank_values=True)
    filtered = {
        k: v
        for k, v in params.items()
        if not k.startswith("utm_") and k not in _TRACKING_PARAMS
    }
    clean_query = urlencode(filtered, doseq=True)
    normalized = parsed._replace(
        scheme=parsed.scheme.lower(),
        netloc=parsed.netloc.lower(),
        query=clean_query,
    )
    return urlunparse(normalized)
