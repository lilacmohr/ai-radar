"""LLM Pass 2 — digest synthesis from full article text.

Stage: final LLM stage
Input:  list[FullItem]
Output: Digest

Makes a single LLM call (gpt-4o via LLMClient) with all full article texts
and parses the structured markdown response into a Digest. Each FullItem is
converted back to a ScoredItem for Digest.articles — full_text and word_count
are consumed by the LLM and discarded.

Section parsing: the LLM response is split on ## headings. Each heading is
matched by prefix to one of the four expected sections; missing sections are
silently set to "". Sections may appear in any order.

If items is empty, returns a Digest with articles=[], all text fields "", and
no LLM call.

Spec reference: SPEC.md §3.3 (Pass 2: Synthesis & Insight), §3.4 (Digest
output format), §3.7 (Pass 2 unreachable).
"""

# 1. Standard library imports
import datetime
import re
import time

# 2. Third-party imports
import structlog

# 3. Internal imports
from radar.config import ObservabilityConfig, PipelineConfig, ProfileConfig
from radar.llm.client import LLMClient
from radar.llm.prompts import PASS_2_SYSTEM_TEMPLATE, PASS_2_USER_TEMPLATE
from radar.models import Digest, FullItem, ScoredItem

# 4. Module-level logger
logger = structlog.get_logger(__name__)

# 5. Constants
_SECTION_EXECUTIVE_SUMMARY = "📡 Executive Summary"
_SECTION_CONTRARIAN_INSIGHTS = "🔍 Contrarian & Non-Obvious Insights"
_SECTION_FOLLOW_UP_QUESTIONS = "❓ Follow-Up Questions & Rabbit Holes"
_SECTION_TRENDING_THEMES = "📈 Trending Themes"


class Synthesizer:
    """Runs LLM Pass 2: synthesizes a Digest from full article text."""

    def __init__(
        self,
        client: LLMClient,
        config: PipelineConfig,
        profile: ProfileConfig,
        observability_config: ObservabilityConfig | None = None,
    ) -> None:
        self._client = client
        self._config = config
        self._profile = profile
        self._observability = observability_config

    def synthesize(
        self,
        items: list[FullItem],
        run_date: datetime.date | None = None,
    ) -> Digest:
        """Synthesize a Digest from full article text via a single LLM call."""
        today = run_date or datetime.datetime.now(tz=datetime.UTC).date()

        if not items:
            return Digest(
                date=today,
                articles=[],
                executive_summary="",
                contrarian_insights="",
                follow_up_questions="",
                trending_themes="",
                source_stats={"synthesis_model": "quality"},
            )

        articles = [_to_scored_item(item) for item in items]

        t_start = time.monotonic()

        system = PASS_2_SYSTEM_TEMPLATE.format(
            role=self._profile.role or "",
            interests_list=_format_interests(self._profile.interests),
        )
        user = PASS_2_USER_TEMPLATE.format(
            articles_formatted=_format_articles(items),
            date=today.strftime("%Y-%m-%d"),
        )

        project = self._observability.project if self._observability else None
        prompt_version = self._config.prompt_versions.get("pass2")
        raw = self._client.complete(
            system=system,
            user=user,
            model="quality",
            pipeline_stage="pass2",
            prompt_version=prompt_version,
            project=project,
        )

        sections = _parse_sections(raw)
        elapsed_ms = int((time.monotonic() - t_start) * 1000)

        logger.info(
            "synthesizer_complete",
            articles_in_digest=len(articles),
            tokens_used=0,
            elapsed_ms=elapsed_ms,
        )

        return Digest(
            date=today,
            articles=articles,
            executive_summary=sections.get(_SECTION_EXECUTIVE_SUMMARY, ""),
            contrarian_insights=sections.get(_SECTION_CONTRARIAN_INSIGHTS, ""),
            follow_up_questions=sections.get(_SECTION_FOLLOW_UP_QUESTIONS, ""),
            trending_themes=sections.get(_SECTION_TRENDING_THEMES, ""),
            source_stats={"synthesis_model": "quality"},
        )


def _to_scored_item(item: FullItem) -> ScoredItem:
    """Convert a FullItem back to ScoredItem, dropping full_text and word_count."""
    return ScoredItem(
        url=item.url,
        title=item.title,
        source=item.source,
        published_at=item.published_at,
        excerpt="",  # excerpt is a Phase 1 concept; not carried through FullItem — see #92
        score=item.score,
        summary=item.summary,
    )


def _format_articles(items: list[FullItem]) -> str:
    """Format FullItems into the Pass 2 user prompt block."""
    blocks = [
        f"---\nURL: {item.url}\nTitle: {item.title}\n"
        f"Pass 1 score: {item.score}/10\nFull text: {item.full_text}\n"
        for item in items
    ]
    return "\n".join(blocks)


def _format_interests(interests: list[str]) -> str:
    """Format interest list as a bulleted list string."""
    return "\n".join(f"- {i}" for i in interests)


def _parse_sections(response: str) -> dict[str, str]:
    """Parse ## sections from the LLM markdown response.

    Splits on ## headings; matches each heading prefix to a known section key.
    Returns a dict mapping section name → stripped body text.
    Missing sections are absent from the returned dict.
    """
    sections: dict[str, str] = {}
    # Split on lines starting with '##' (but not '###')
    parts = re.split(r"(?m)^(?=## )", response)
    for part in parts:
        if not part.startswith("## "):
            continue
        first_line, _, body = part.partition("\n")
        heading = first_line[3:].strip()  # strip '## '
        sections[heading] = body.strip()
    return sections
