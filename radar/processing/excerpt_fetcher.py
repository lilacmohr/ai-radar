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

Spec reference: SPEC.md §3.2 step 4, §3.7 (paywall threshold), §6.3 (60s timeout).
"""

# 1. Standard library imports
# 2. Third-party imports
import structlog

# 3. Internal imports
from radar.models import ExcerptItem, RawItem

# 4. Module-level logger
logger = structlog.get_logger(__name__)


def excerpt_fetcher(items: list[RawItem]) -> list[ExcerptItem]:
    """Fetch and extract excerpts for each RawItem, returning ExcerptItems."""
    raise NotImplementedError
