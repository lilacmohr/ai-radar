"""LLM Pass 2 — digest synthesis from full article text.

Stage: final LLM stage
Input:  list[FullItem]
Output: Digest

Sends full article text to gpt-4o via LLMClient and parses the structured
markdown response into a Digest object. A single LLM call covers all articles
(unlike Pass 1 which batches). Each FullItem is converted back to a ScoredItem
for Digest.articles — full_text is consumed by the LLM and discarded.

Spec reference: SPEC.md §3.3 (Pass 2: Synthesis & Insight), §3.4 (Digest output
format), §3.7 (Pass 2 unreachable).
"""

# 1. Standard library imports

# 2. Third-party imports

# 3. Internal imports
from radar.config import PipelineConfig, ProfileConfig
from radar.llm.client import LLMClient
from radar.models import Digest, FullItem


class Synthesizer:
    """Runs LLM Pass 2: synthesizes a Digest from full article text."""

    def __init__(self, client: LLMClient, config: PipelineConfig, profile: ProfileConfig) -> None:
        raise NotImplementedError

    def synthesize(self, items: list[FullItem]) -> Digest:
        """Synthesize a Digest from full article text via a single LLM call."""
        raise NotImplementedError
