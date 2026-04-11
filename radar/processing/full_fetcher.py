"""Full article fetcher stage: fetches complete article text for Pass 1 survivors.

Stage: step 7 of the pipeline (Full Article Fetcher)
Input:  list[ScoredItem]  (output of Summarizer / Pass 1 relevance filter)
Output: list[FullItem]    (input to Truncator)

For each ScoredItem, fetches the full article body via httpx and extracts
clean text with trafilatura. Carries score and summary unchanged from the
ScoredItem. Articles where extraction yields < 50 words or returns None
are treated as paywall/extraction failures and excluded from output.

Spec reference: SPEC.md §3.2 step 7, §3.7 (paywall threshold).
"""

# 1. Standard library imports

# 2. Third-party imports

# 3. Internal imports
from radar.config import PipelineConfig
from radar.models import FullItem, ScoredItem


class FullFetcher:
    """Fetches full article text for each ScoredItem."""

    def __init__(self, config: PipelineConfig) -> None:
        raise NotImplementedError

    def fetch(self, items: list[ScoredItem]) -> list[FullItem]:
        """Fetch full text for each item, returning FullItems."""
        raise NotImplementedError
