"""Truncator stage: caps article text length before LLM Pass 2.

Stage: between FullFetcher and Synthesizer
Input:  list[FullItem]
Output: list[FullItem] (full_text and word_count updated; all other fields unchanged)

Two responsibilities:
1. Truncate each article's full_text to at most config.max_words_full words.
2. If article count exceeds config.max_articles_in_digest, drop lowest-scored articles
   first (log WARNING with articles_dropped count). Input order is preserved among
   surviving articles.

Pure Python — no I/O, no LLM calls.

Spec reference: SPEC.md §3.3 (Pass 2 input preparation), §3.7 (context window overflow).
"""

# 1. Standard library imports
from dataclasses import replace

# 2. Third-party imports
import structlog

# 3. Internal imports
from radar.config import PipelineConfig
from radar.models import FullItem

# 4. Module-level logger
logger = structlog.get_logger(__name__)


class Truncator:
    """Caps article text length and drops overflow articles before Pass 2."""

    def __init__(self, config: PipelineConfig) -> None:
        self._config = config

    def truncate(self, items: list[FullItem]) -> list[FullItem]:
        """Truncate and drop articles to fit the Pass 2 context budget."""
        if not items:
            return []

        # Drop lowest-scored articles if count exceeds the digest cap.
        # Stable sort by score descending preserves relative input order for
        # tied scores; we then slice to the cap and restore original order.
        cap = self._config.max_articles_in_digest
        if len(items) > cap:
            articles_dropped = len(items) - cap
            logger.warning("articles_dropped", articles_dropped=articles_dropped)
            # Sort by score descending (stable), keep top-cap, restore input order
            scored = sorted(enumerate(items), key=lambda x: x[1].score, reverse=True)
            kept_indices = {idx for idx, _ in scored[:cap]}
            items = [item for idx, item in enumerate(items) if idx in kept_indices]

        return [_truncate_item(item, self._config.max_words_full) for item in items]


def _truncate_item(item: FullItem, max_words: int) -> FullItem:
    """Return item with full_text truncated to max_words words."""
    words = item.full_text.split()
    if len(words) <= max_words:
        return item
    truncated = " ".join(words[:max_words])
    return replace(item, full_text=truncated, word_count=max_words)
