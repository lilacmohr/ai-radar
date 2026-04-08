"""Hacker News source connector for ai-radar.

Stage: source fetch (step 1 of pipeline)
Input:  HackerNewsConfig
Output: list[RawItem] (content_type="web")

Fetches recent HN stories via the Algolia search API, filters by min_score
and keywords, and maps each story to a RawItem. Lookback window: 24 hours.

Spec reference: SPEC.md §3.1 (Hacker News connector), §6.3 (60s timeout).
"""

# Standard library imports
# Third-party imports
import structlog

# Internal imports
from radar.config import HackerNewsConfig
from radar.models import RawItem
from radar.sources.base import Source

logger = structlog.get_logger(__name__)


class HNSource(Source):
    """Hacker News source connector via Algolia search API."""

    def __init__(self, config: HackerNewsConfig) -> None:
        self._config = config

    def fetch(self) -> list[RawItem]:
        """Fetch and return recent HN stories matching config filters."""
        raise NotImplementedError
