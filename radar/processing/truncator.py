"""Truncator stage: caps article text length before LLM Pass 2.

Stage: between FullFetcher and Synthesizer
Input:  list[FullItem]
Output: list[FullItem] (full_text and word_count updated; all other fields unchanged)

Two responsibilities:
1. Truncate each article's full_text to at most config.max_words_full words.
2. If total word count across all articles exceeds the context budget
   (max_articles_in_digest * max_words_full), drop lowest-scored articles
   first (log WARNING with articles_dropped count).

Pure Python — no I/O, no LLM calls.

Spec reference: SPEC.md §3.3 (Pass 2 input preparation), §3.7 (context window overflow).
"""

# 1. Standard library imports

# 2. Third-party imports

# 3. Internal imports
from radar.config import PipelineConfig
from radar.models import FullItem


class Truncator:
    """Caps article text length and drops overflow articles before Pass 2."""

    def __init__(self, config: PipelineConfig) -> None:
        raise NotImplementedError

    def truncate(self, items: list[FullItem]) -> list[FullItem]:
        """Truncate and drop articles to fit the Pass 2 context budget."""
        raise NotImplementedError
