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

from radar.config import ArxivConfig
from radar.models import RawItem
from radar.sources.base import Source


class ArxivSource(Source):
    """ArXiv source connector."""

    def __init__(self, config: ArxivConfig) -> None:
        self._config = config

    def fetch(self) -> list[RawItem]:
        """Fetch recent ArXiv papers for configured categories."""
        raise NotImplementedError
