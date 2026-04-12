"""Pre-filter stage: coarse keyword filter on ExcerptItems.

Receives a list[ExcerptItem] and a list of interest phrases.
Returns the subset of items whose title or excerpt contains at least
one keyword token extracted from any interest phrase.

Interest phrases are expanded into individual tokens (case-insensitive
substring match) so that a phrase like "agent frameworks and multi-agent
systems" yields tokens ["agent", "frameworks", "multi-agent", "systems"]
and matches any article containing any of those words.

Stage: step 6 of preprocessing — after Phase 2 dedup, before Pass 1 LLM.
Pure logic — no I/O, no network, no LLM.
"""

# 1. Standard library imports
import re

# 2. Third-party imports
import structlog

# 3. Internal imports
from radar.models import ExcerptItem

logger = structlog.get_logger(__name__)

_STOP_WORDS = frozenset({
    "and", "or", "the", "for", "of", "in", "with", "from", "to", "a", "an",
    "at", "is", "are", "as", "by", "on", "its", "that", "this", "their",
})


def _expand_interests(interests: list[str]) -> list[str]:
    """Expand interest phrases into individual keyword tokens for matching."""
    tokens: set[str] = set()
    for phrase in interests:
        lower = phrase.lower()
        # keep the full phrase in case it matches verbatim
        tokens.add(lower)
        # also extract individual hyphenated words, skipping stop words
        for token in re.findall(r"[a-z0-9]+(?:-[a-z0-9]+)*", lower):
            if token not in _STOP_WORDS and len(token) >= 2:
                tokens.add(token)
    return list(tokens)


def pre_filter(items: list[ExcerptItem], interests: list[str]) -> list[ExcerptItem]:
    """Return items whose title or excerpt contains at least one interest keyword.

    Interest phrases are tokenized so individual words are matched, not just
    full phrases. Matching is case-insensitive substring search. An item passes
    if ANY token matches in title OR excerpt (OR semantics).
    Empty interests returns [].
    """
    if not interests:
        return []
    keywords = _expand_interests(interests)
    result = [
        item
        for item in items
        if any(kw in item.title.lower() or kw in item.excerpt.lower() for kw in keywords)
    ]
    logger.info("pre_filter_complete", input=len(items), passed=len(result), keywords=len(keywords))
    return result
