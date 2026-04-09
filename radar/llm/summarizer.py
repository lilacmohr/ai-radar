"""LLM Pass 1 — relevance scoring and summarization.

Sends batches of ExcerptItem excerpts to the LLM and returns ScoredItem
objects for all items that score at or above the configured relevance
threshold. Items below threshold are silently dropped (expected behavior,
not an error).

Stub — implementation tracked in [IMPL] #74.
"""

import json  # noqa: F401
import time  # noqa: F401

import structlog

from radar.config import PipelineConfig, ProfileConfig
from radar.llm.client import LLMClient
from radar.models import ExcerptItem, ScoredItem

logger = structlog.get_logger(__name__)


class Summarizer:
    """Runs LLM Pass 1: scores and summarizes excerpt batches."""

    def __init__(self, client: LLMClient, config: PipelineConfig, profile: ProfileConfig) -> None:
        raise NotImplementedError

    def summarize(self, items: list[ExcerptItem]) -> list[ScoredItem]:
        """Score and summarize items; drop those below relevance threshold."""
        raise NotImplementedError
