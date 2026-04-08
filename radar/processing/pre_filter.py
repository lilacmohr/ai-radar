"""Pre-filter stage: coarse keyword filter on ExcerptItems.

Receives a list[ExcerptItem] and a list of interest keywords.
Returns the subset of items whose title or excerpt contains at least
one keyword (case-insensitive substring match).

Stage: step 6 of preprocessing — after Phase 2 dedup, before Pass 1 LLM.
Pure logic — no I/O, no network, no LLM.
"""

# 1. Standard library imports
# 2. Third-party imports
# 3. Internal imports
from radar.models import ExcerptItem


def pre_filter(items: list[ExcerptItem], interests: list[str]) -> list[ExcerptItem]:
    """Return items whose title or excerpt contains at least one interest keyword.

    Matching is case-insensitive substring search. An item passes if ANY keyword
    matches in title OR excerpt (OR semantics). Empty interests returns [].
    """
    if not interests:
        return []
    lower_keywords = [kw.lower() for kw in interests]
    return [
        item
        for item in items
        if any(
            kw in item.title.lower() or kw in item.excerpt.lower()
            for kw in lower_keywords
        )
    ]
