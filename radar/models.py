"""Shared data models for the ai-radar pipeline.

Stub — no fields defined yet. See [IMPL] issue #17.
"""

from dataclasses import dataclass
from datetime import date, datetime


@dataclass
class RawItem:
    """Raw content as fetched from a source connector."""


@dataclass
class NormalizedItem:
    """Boilerplate-stripped intermediate used by fetchers (not passed between stages)."""


@dataclass
class ExcerptItem:
    """Title + ~200-word excerpt; input to PreFilter and Pass 1."""


@dataclass
class ScoredItem:
    """Pass 1 output: excerpt + relevance score + summary."""


@dataclass
class FullItem:
    """Full article text after fetch + truncation; input to Pass 2."""


@dataclass
class Digest:
    """Pass 2 output: full structured digest."""


__all__ = [
    "Digest",
    "ExcerptItem",
    "FullItem",
    "NormalizedItem",
    "RawItem",
    "ScoredItem",
]

# Suppress unused-import warnings from stub — these will be used after implementation.
_ = date, datetime
