"""LLM Pass 1 — relevance scoring and summarization.

Sends batches of ExcerptItem excerpts to the LLM (gpt-4o-mini via LLMClient)
and returns ScoredItem objects for all items that score at or above the
configured relevance threshold. Items below threshold are silently dropped
(expected filtering behavior, not an error).

Retry policy on parse failure (SPEC.md §3.7):
  - First failure: retry once with explicit JSON instruction appended to user prompt
  - Second failure: skip the batch, log WARNING, continue with remaining batches
"""

import json
import time

import structlog

from radar.config import PipelineConfig, ProfileConfig
from radar.llm.client import LLMClient
from radar.llm.prompts import PASS_1_SYSTEM_TEMPLATE, PASS_1_USER_TEMPLATE
from radar.models import ExcerptItem, ScoredItem

logger = structlog.get_logger(__name__)

_JSON_RETRY_SUFFIX = "\n\nReturn only a JSON array. No other text."
_JSON_RESPONSE_FORMAT: dict[str, str] = {"type": "json_object"}
_SCORE_MIN = 1
_SCORE_MAX = 10


class Summarizer:
    """Runs LLM Pass 1: scores and summarizes excerpt batches."""

    def __init__(self, client: LLMClient, config: PipelineConfig, profile: ProfileConfig) -> None:
        self._client = client
        self._config = config
        self._profile = profile

    def summarize(self, items: list[ExcerptItem]) -> list[ScoredItem]:
        """Score and summarize items; drop those below relevance threshold.

        Splits items into batches of config.batch_size, calls the LLM once per
        batch, and collects results across all batches.
        """
        if not items:
            return []

        t_start = time.monotonic()
        results: list[ScoredItem] = []
        skipped_parse_error = 0

        system = PASS_1_SYSTEM_TEMPLATE.format(
            role=self._profile.role or "",
            interests_list=_format_interests(self._profile.interests),
        )

        batches = _chunk(items, self._config.batch_size)
        for batch in batches:
            batch_results, parse_errors = self._process_batch(batch, system)
            results.extend(batch_results)
            skipped_parse_error += parse_errors

        elapsed_ms = int((time.monotonic() - t_start) * 1000)
        logger.info(
            "summarizer_complete",
            input=len(items),
            scored=len(results),
            skipped_parse_error=skipped_parse_error,
            elapsed_ms=elapsed_ms,
        )
        return results

    def _process_batch(self, batch: list[ExcerptItem], system: str) -> tuple[list[ScoredItem], int]:
        """Process one batch; return (scored_items, parse_error_count)."""
        url_to_item = {item.url: item for item in batch}
        user = _format_user_prompt(batch)

        model = self._config.summarization_model
        raw = self._client.complete(
            system=system, user=user, model=model, response_format=_JSON_RESPONSE_FORMAT
        )
        parsed = _try_parse(raw)

        if parsed is None:
            # First failure: retry with explicit JSON instruction
            retry_user = user + _JSON_RETRY_SUFFIX
            raw = self._client.complete(
                system=system,
                user=retry_user,
                model=model,
                response_format=_JSON_RESPONSE_FORMAT,
            )
            parsed = _try_parse(raw)

        if parsed is None:
            logger.warning("summarizer_batch_skipped", batch_size=len(batch))
            return [], 1

        scored = _build_scored_items(parsed, url_to_item, self._profile.relevance_threshold)
        return scored, 0


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------


def _chunk(items: list[ExcerptItem], size: int) -> list[list[ExcerptItem]]:
    return [items[i : i + size] for i in range(0, len(items), size)]


def _format_interests(interests: list[str]) -> str:
    return "\n".join(f"- {interest}" for interest in interests)


def _format_user_prompt(batch: list[ExcerptItem]) -> str:
    articles_formatted = "\n".join(
        f"---\nURL: {item.url}\nTitle: {item.title}\nExcerpt: {item.excerpt}\n" for item in batch
    )
    return PASS_1_USER_TEMPLATE.format(articles_formatted=articles_formatted)


def _try_parse(raw: str) -> list[dict[str, object]] | None:
    """Return parsed JSON list, or None on any parse/type error.

    Strips markdown code fences (e.g. ```json ... ```) before parsing —
    some models emit fences even when instructed not to.
    """
    stripped = raw.strip()
    if stripped.startswith("```"):
        stripped = stripped.split("\n", 1)[-1].rsplit("```", 1)[0].strip()
    try:
        result = json.loads(stripped)
        if isinstance(result, list):
            return result
    except (json.JSONDecodeError, ValueError):
        pass
    return None


def _build_scored_items(
    parsed: list[dict[str, object]],
    url_to_item: dict[str, ExcerptItem],
    threshold: int,
) -> list[ScoredItem]:
    """Convert raw LLM dicts to ScoredItem, applying validation and threshold filter."""
    results: list[ScoredItem] = []

    for entry in parsed:
        url = str(entry.get("url", ""))
        if url not in url_to_item:
            logger.warning("summarizer_unknown_url", url=url)
            continue

        try:
            score = int(entry.get("score", 0))  # type: ignore[call-overload]
        except (TypeError, ValueError):
            logger.warning("summarizer_invalid_score", url=url, score=entry.get("score"))
            continue

        if not _SCORE_MIN <= score <= _SCORE_MAX:
            logger.warning("summarizer_invalid_score", url=url, score=score)
            continue

        if score < threshold:
            continue  # below threshold — silent drop

        source_item = url_to_item[url]
        results.append(
            ScoredItem(
                url=url,
                title=source_item.title,
                source=source_item.source,
                published_at=source_item.published_at,
                excerpt=source_item.excerpt,
                score=score,
                summary=str(entry.get("summary") or ""),
            )
        )

    # Log any input URLs that were missing from the response
    response_urls = {str(e.get("url", "")) for e in parsed}
    for url in url_to_item:
        if url not in response_urls:
            logger.warning("summarizer_missing_url", url=url)

    return results
