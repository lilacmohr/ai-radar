"""Pre-filter stage: coarse keyword filter on ExcerptItems.

Receives a list[ExcerptItem] and a list of interest keywords.
Returns the subset of items whose title or excerpt contains at least
one keyword (case-insensitive substring match).

Stage: step 6 of preprocessing — after Phase 2 dedup, before Pass 1 LLM.
Pure logic — no I/O, no network, no LLM.
"""

# 1. Standard library imports
# 2. Third-party imports
import structlog

# 3. Internal imports
from radar.models import ExcerptItem

# 4. Module-level logger
logger = structlog.get_logger(__name__)


def pre_filter(items: list[ExcerptItem], interests: list[str]) -> list[ExcerptItem]:
    """Filter items to those matching at least one interest keyword."""
    raise NotImplementedError
