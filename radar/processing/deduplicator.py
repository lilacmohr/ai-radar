"""Deduplication stage: two-phase URL and content hash filtering.

Phase 1 — dedup_by_url: filters list[RawItem] against url_hash cache entries.
  Computes a url_hash from each item's URL (after stripping utm_* tracking params).
Phase 2 — dedup_by_content: filters list[ExcerptItem] against content_hash cache entries.
  ExcerptItem already carries content_hash; no hashing needed here.

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


def url_to_hash(url: str) -> str:
    """Return a hex hash of the normalized URL (utm_* params stripped)."""
    normalized = _normalize_url(url)
    return hashlib.sha256(normalized.encode()).hexdigest()


def dedup_by_url(items: list[RawItem], cache: Cache) -> list[RawItem]:
    """Filter RawItems to those whose url_hash has not been seen."""
    raise NotImplementedError


def dedup_by_content(items: list[ExcerptItem], cache: Cache) -> list[ExcerptItem]:
    """Filter ExcerptItems to those whose content_hash has not been seen."""
    raise NotImplementedError


def _normalize_url(url: str) -> str:
    """Strip utm_* query parameters and return the cleaned URL."""
    parsed = urlparse(url)
    params = parse_qs(parsed.query, keep_blank_values=True)
    filtered = {k: v for k, v in params.items() if not k.startswith("utm_")}
    clean_query = urlencode(filtered, doseq=True)
    return urlunparse(parsed._replace(query=clean_query))
