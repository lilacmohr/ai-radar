"""Shared data models for the ai-radar pipeline.

Typed dataclasses that flow between pipeline stages:
  Sources → RawItem
  → NormalizedItem (internal to fetchers, not passed between stages)
  → ExcerptItem → ScoredItem → FullItem → Digest

Spec reference: SPEC.md §3.1 (data models), §4.2 (data flow).
"""

# Standard library imports
from dataclasses import dataclass
from datetime import date, datetime
from typing import Any, Literal

_SCORE_MIN = 1
_SCORE_MAX = 10


@dataclass
class RawItem:
    """Raw content as fetched from a source connector.

    Stage: output of Sources, input to Deduplicator (Phase 1).
    """

    url: str
    title: str
    source: str
    published_at: datetime
    raw_content: str
    content_type: Literal["email", "web", "arxiv"]


@dataclass
class NormalizedItem:
    """Boilerplate-stripped intermediate used internally by fetchers.

    Not passed between pipeline stages directly — used within the
    Excerpt Fetcher and Full Article Fetcher for internal processing.
    """

    url: str
    title: str
    source: str
    published_at: datetime
    clean_text: str
    word_count: int
    url_hash: str
    content_hash: str

    def __post_init__(self) -> None:
        if self.word_count < 0:
            msg = f"word_count must be >= 0, got {self.word_count}"
            raise ValueError(msg)


@dataclass
class ExcerptItem:
    """Title + ~200-word excerpt; input to PreFilter and LLM Pass 1.

    Stage: output of Excerpt Fetcher + Phase 2 Deduplicator, input to PreFilter.
    """

    url: str
    title: str
    source: str
    published_at: datetime
    excerpt: str
    url_hash: str
    content_hash: str


@dataclass
class ScoredItem:
    """Pass 1 output: excerpt + relevance score + summary.

    Stage: output of LLM Pass 1 (Summarizer), input to Relevance Filter and Digest.
    score is 1-10; validated at construction time per SPEC.md §3.1.
    """

    url: str
    title: str
    source: str
    published_at: datetime
    excerpt: str
    score: int
    summary: str

    def __post_init__(self) -> None:
        if not _SCORE_MIN <= self.score <= _SCORE_MAX:
            msg = f"score must be in range {_SCORE_MIN}-{_SCORE_MAX}, got {self.score}"
            raise ValueError(msg)


@dataclass
class FullItem:
    """Full article text after fetch + truncation; input to LLM Pass 2.

    Stage: output of Full Article Fetcher + Truncator, input to Synthesizer.
    score is carried over from Pass 1 (1-10); word_count must be >= 0.
    """

    url: str
    title: str
    source: str
    published_at: datetime
    full_text: str
    word_count: int
    score: int
    summary: str

    def __post_init__(self) -> None:
        if self.word_count < 0:
            msg = f"word_count must be >= 0, got {self.word_count}"
            raise ValueError(msg)
        if not _SCORE_MIN <= self.score <= _SCORE_MAX:
            msg = f"score must be in range {_SCORE_MIN}-{_SCORE_MAX}, got {self.score}"
            raise ValueError(msg)


@dataclass
class Digest:
    """Pass 2 output: full structured digest.

    Stage: output of Synthesizer (LLM Pass 2), input to MarkdownRenderer.
    articles is list[ScoredItem] — zero-length is valid (SPEC.md §3.7, exit code 0).

    articles holds ScoredItem (Pass 1 output), not FullItem. The full_text fetched
    for Pass 2 input is consumed by the Synthesizer and discarded — it is not part
    of the digest data model. pipeline.py reconstructs the ScoredItem list from Pass 1
    output when building the Digest.
    """

    date: date
    articles: list[ScoredItem]
    executive_summary: str
    contrarian_insights: str
    follow_up_questions: str
    trending_themes: str
    source_stats: dict[str, Any]


__all__ = [
    "Digest",
    "ExcerptItem",
    "FullItem",
    "NormalizedItem",
    "RawItem",
    "ScoredItem",
]
