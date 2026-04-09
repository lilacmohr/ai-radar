"""Tests for radar/llm/summarizer.py.

Verifies the Summarizer stage (LLM Pass 1):
- Returns list[ScoredItem] with fields from LLM response + carried-over ExcerptItem fields
- Items below relevance_threshold are dropped; items at threshold are included
- Input is split into batches; one LLM call per batch
- Malformed JSON response: retries once with explicit JSON instruction
- Second parse failure: batch skipped, pipeline continues with remaining batches
- URL missing from LLM response: treated as score 0 (dropped)
- Extra URLs in LLM response (not in input): ignored
- Out-of-range score in response: item skipped
- Contract: return type, constructor signature, works with TestLLMClient
"""

import inspect
import json
from datetime import UTC, datetime

from radar.config import PipelineConfig, ProfileConfig
from radar.llm.summarizer import Summarizer
from radar.models import ExcerptItem, ScoredItem
from tests.conftest import TestLLMClient

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_DEFAULT_URL = "https://example.com/article"
_DEFAULT_TITLE = "Test Article"
_DEFAULT_SOURCE = "rss"
_DEFAULT_EXCERPT = "This is a test excerpt about LLM inference and serving."
_DEFAULT_SCORE = 7
_DEFAULT_SUMMARY = "A solid article about LLM inference."
_THRESHOLD = 6

# ---------------------------------------------------------------------------
# Factories
# ---------------------------------------------------------------------------


def _make_excerpt_item(
    url: str = _DEFAULT_URL,
    title: str = _DEFAULT_TITLE,
    source: str = _DEFAULT_SOURCE,
    excerpt: str = _DEFAULT_EXCERPT,
) -> ExcerptItem:
    return ExcerptItem(
        url=url,
        title=title,
        source=source,
        published_at=datetime(2026, 4, 9, 9, 0, 0, tzinfo=UTC),
        excerpt=excerpt,
        url_hash="abc123",
        content_hash="def456",
    )


def _make_profile(
    threshold: int = _THRESHOLD,
    role: str = "AI engineer",
    interests: list[str] | None = None,
) -> ProfileConfig:
    return ProfileConfig(
        role=role,
        interests=interests or ["LLM inference"],
        relevance_threshold=threshold,
    )


def _make_config(batch_size: int = 10, model: str = "gpt-4o-mini") -> PipelineConfig:
    return PipelineConfig(batch_size=batch_size, summarization_model=model)


def _llm_response(
    url: str = _DEFAULT_URL,
    score: int = _DEFAULT_SCORE,
    summary: str = _DEFAULT_SUMMARY,
) -> str:
    return json.dumps([{"url": url, "score": score, "summary": summary}])


def _llm_response_multi(items: list[tuple[str, int, str]]) -> str:
    """Build a JSON response for multiple items: [(url, score, summary), ...]."""
    return json.dumps([{"url": u, "score": s, "summary": sm} for u, s, sm in items])


# ---------------------------------------------------------------------------
# Happy path: return values and field mapping
# ---------------------------------------------------------------------------


def test_summarize_returns_list_of_scored_items() -> None:
    client = TestLLMClient(responses=[_llm_response()])
    result = Summarizer(client, _make_config(), _make_profile()).summarize([_make_excerpt_item()])
    assert isinstance(result, list)
    assert all(isinstance(item, ScoredItem) for item in result)


def test_scored_item_score_from_llm_response() -> None:
    client = TestLLMClient(responses=[_llm_response(score=8)])
    result = Summarizer(client, _make_config(), _make_profile()).summarize([_make_excerpt_item()])
    assert result[0].score == 8  # noqa: PLR2004


def test_scored_item_summary_from_llm_response() -> None:
    client = TestLLMClient(responses=[_llm_response(summary="Great insight.")])
    result = Summarizer(client, _make_config(), _make_profile()).summarize([_make_excerpt_item()])
    assert result[0].summary == "Great insight."


def test_scored_item_url_from_llm_response() -> None:
    url = "https://example.com/specific"
    client = TestLLMClient(responses=[_llm_response(url=url)])
    result = Summarizer(client, _make_config(), _make_profile()).summarize(
        [_make_excerpt_item(url=url)]
    )
    assert result[0].url == url


def test_title_carried_over_from_excerpt_item() -> None:
    item = _make_excerpt_item(title="My Custom Title")
    client = TestLLMClient(responses=[_llm_response(url=item.url)])
    result = Summarizer(client, _make_config(), _make_profile()).summarize([item])
    assert result[0].title == "My Custom Title"


def test_source_carried_over_from_excerpt_item() -> None:
    item = _make_excerpt_item(source="hackernews")
    client = TestLLMClient(responses=[_llm_response(url=item.url)])
    result = Summarizer(client, _make_config(), _make_profile()).summarize([item])
    assert result[0].source == "hackernews"


def test_published_at_carried_over_from_excerpt_item() -> None:
    item = _make_excerpt_item()
    client = TestLLMClient(responses=[_llm_response(url=item.url)])
    result = Summarizer(client, _make_config(), _make_profile()).summarize([item])
    assert result[0].published_at == item.published_at


def test_excerpt_carried_over_from_excerpt_item() -> None:
    item = _make_excerpt_item(excerpt="Unique excerpt text here.")
    client = TestLLMClient(responses=[_llm_response(url=item.url)])
    result = Summarizer(client, _make_config(), _make_profile()).summarize([item])
    assert result[0].excerpt == "Unique excerpt text here."


def test_multiple_items_all_returned_when_all_above_threshold() -> None:
    items = [_make_excerpt_item(url=f"https://example.com/{i}") for i in range(3)]
    responses = _llm_response_multi([(item.url, _THRESHOLD + 1, "Good.") for item in items])
    client = TestLLMClient(responses=[responses])
    result = Summarizer(client, _make_config(), _make_profile()).summarize(items)
    assert len(result) == len(items)


# ---------------------------------------------------------------------------
# Happy path: empty input
# ---------------------------------------------------------------------------


def test_empty_input_returns_empty_list() -> None:
    client = TestLLMClient(responses=["irrelevant"])
    result = Summarizer(client, _make_config(), _make_profile()).summarize([])
    assert result == []


def test_empty_input_does_not_call_llm() -> None:
    client = TestLLMClient()
    Summarizer(client, _make_config(), _make_profile()).summarize([])
    assert client.call_count == 0


# ---------------------------------------------------------------------------
# Relevance threshold filtering
# ---------------------------------------------------------------------------


def test_items_above_threshold_included() -> None:
    item = _make_excerpt_item()
    client = TestLLMClient(responses=[_llm_response(score=_THRESHOLD + 1)])
    result = Summarizer(client, _make_config(), _make_profile(threshold=_THRESHOLD)).summarize(
        [item]
    )
    assert len(result) == 1


def test_items_equal_to_threshold_included() -> None:
    item = _make_excerpt_item()
    client = TestLLMClient(responses=[_llm_response(score=_THRESHOLD)])
    result = Summarizer(client, _make_config(), _make_profile(threshold=_THRESHOLD)).summarize(
        [item]
    )
    assert len(result) == 1


def test_items_below_threshold_dropped() -> None:
    item = _make_excerpt_item()
    client = TestLLMClient(responses=[_llm_response(score=_THRESHOLD - 1)])
    result = Summarizer(client, _make_config(), _make_profile(threshold=_THRESHOLD)).summarize(
        [item]
    )
    assert result == []


def test_all_items_below_threshold_returns_empty() -> None:
    items = [_make_excerpt_item(url=f"https://example.com/{i}") for i in range(3)]
    responses = _llm_response_multi([(item.url, 2, "Low relevance.") for item in items])
    client = TestLLMClient(responses=[responses])
    result = Summarizer(client, _make_config(), _make_profile(threshold=_THRESHOLD)).summarize(
        items
    )
    assert result == []


def test_mixed_threshold_only_passing_items_returned() -> None:
    low = _make_excerpt_item(url="https://example.com/low")
    high = _make_excerpt_item(url="https://example.com/high")
    response = _llm_response_multi(
        [(low.url, _THRESHOLD - 1, "Low."), (high.url, _THRESHOLD + 1, "High.")]
    )
    client = TestLLMClient(responses=[response])
    result = Summarizer(client, _make_config(), _make_profile(threshold=_THRESHOLD)).summarize(
        [low, high]
    )
    assert len(result) == 1
    assert result[0].url == "https://example.com/high"


# ---------------------------------------------------------------------------
# Batching
# ---------------------------------------------------------------------------


def test_single_batch_makes_one_llm_call() -> None:
    items = [_make_excerpt_item(url=f"https://example.com/{i}") for i in range(3)]
    responses = _llm_response_multi([(item.url, 7, "Good.") for item in items])
    client = TestLLMClient(responses=[responses])
    Summarizer(client, _make_config(batch_size=10), _make_profile()).summarize(items)
    assert client.call_count == 1


def test_items_split_into_batches_makes_multiple_calls() -> None:
    items = [_make_excerpt_item(url=f"https://example.com/{i}") for i in range(4)]
    batch1 = _llm_response_multi([(item.url, 7, "Good.") for item in items[:2]])
    batch2 = _llm_response_multi([(item.url, 7, "Good.") for item in items[2:]])
    client = TestLLMClient(responses=[batch1, batch2])
    Summarizer(client, _make_config(batch_size=2), _make_profile()).summarize(items)
    assert client.call_count == 2  # noqa: PLR2004


def test_batch_count_matches_ceil_of_items_over_batch_size() -> None:
    """6 items with batch_size=2 → 3 calls."""
    items = [_make_excerpt_item(url=f"https://example.com/{i}") for i in range(6)]
    per_batch = _llm_response_multi([(item.url, 7, "Good.") for item in items[:2]])
    client = TestLLMClient(responses=[per_batch])
    Summarizer(client, _make_config(batch_size=2), _make_profile()).summarize(items)
    assert client.call_count == 3  # noqa: PLR2004


def test_items_from_all_batches_returned() -> None:
    items = [_make_excerpt_item(url=f"https://example.com/{i}") for i in range(4)]
    batch1 = _llm_response_multi([(item.url, 7, "Good.") for item in items[:2]])
    batch2 = _llm_response_multi([(item.url, 7, "Good.") for item in items[2:]])
    client = TestLLMClient(responses=[batch1, batch2])
    result = Summarizer(client, _make_config(batch_size=2), _make_profile()).summarize(items)
    assert len(result) == len(items)


def test_uses_configured_summarization_model() -> None:
    item = _make_excerpt_item()
    client = TestLLMClient(responses=[_llm_response(url=item.url)])
    Summarizer(client, _make_config(model="gpt-4o-mini"), _make_profile()).summarize([item])
    assert client.calls[0]["model"] == "gpt-4o-mini"


def test_system_prompt_includes_role() -> None:
    item = _make_excerpt_item()
    profile = _make_profile(role="senior AI researcher")
    client = TestLLMClient(responses=[_llm_response(url=item.url)])
    Summarizer(client, _make_config(), profile).summarize([item])
    assert "senior AI researcher" in client.calls[0]["system"]


def test_system_prompt_includes_interests() -> None:
    item = _make_excerpt_item()
    profile = _make_profile(interests=["agentic systems", "model serving"])
    client = TestLLMClient(responses=[_llm_response(url=item.url)])
    Summarizer(client, _make_config(), profile).summarize([item])
    assert "agentic systems" in client.calls[0]["system"]


def test_user_prompt_includes_article_url() -> None:
    item = _make_excerpt_item(url="https://example.com/unique-url")
    client = TestLLMClient(responses=[_llm_response(url=item.url)])
    Summarizer(client, _make_config(), _make_profile()).summarize([item])
    assert "https://example.com/unique-url" in client.calls[0]["user"]


# ---------------------------------------------------------------------------
# Parse failure: retry on malformed JSON
# ---------------------------------------------------------------------------


def test_malformed_json_retries_once() -> None:
    """First response is invalid; retry should succeed on second call."""
    item = _make_excerpt_item()
    client = TestLLMClient(responses=["not valid json", _llm_response(url=item.url)])
    result = Summarizer(client, _make_config(), _make_profile()).summarize([item])
    assert client.call_count == 2  # noqa: PLR2004
    assert len(result) == 1


def test_retry_user_prompt_contains_json_instruction() -> None:
    """Retry must include an explicit JSON instruction in the user prompt."""
    item = _make_excerpt_item()
    client = TestLLMClient(responses=["not valid json", _llm_response(url=item.url)])
    Summarizer(client, _make_config(), _make_profile()).summarize([item])
    retry_user = client.calls[1]["user"]
    assert "JSON" in retry_user


def test_malformed_json_second_failure_skips_batch() -> None:
    """Both attempts fail → batch is skipped, returns empty list."""
    item = _make_excerpt_item()
    client = TestLLMClient(responses=["not valid json", "also not json"])
    result = Summarizer(client, _make_config(), _make_profile()).summarize([item])
    assert result == []


def test_malformed_json_second_failure_makes_exactly_two_calls() -> None:
    item = _make_excerpt_item()
    client = TestLLMClient(responses=["not valid json", "also not json"])
    Summarizer(client, _make_config(), _make_profile()).summarize([item])
    assert client.call_count == 2  # noqa: PLR2004


def test_parse_failure_in_first_batch_does_not_affect_second_batch() -> None:
    """Batch 1 fails both attempts; batch 2 succeeds and its items are returned."""
    items = [_make_excerpt_item(url=f"https://example.com/{i}") for i in range(4)]
    batch2_response = _llm_response_multi([(item.url, 7, "Good.") for item in items[2:]])
    client = TestLLMClient(responses=["not valid json", "also not json", batch2_response])
    result = Summarizer(client, _make_config(batch_size=2), _make_profile()).summarize(items)
    assert len(result) == len(items[2:])
    assert {r.url for r in result} == {items[2].url, items[3].url}


# ---------------------------------------------------------------------------
# Missing and extra URLs in LLM response
# ---------------------------------------------------------------------------


def test_url_missing_from_response_item_dropped() -> None:
    """URL present in input but absent from LLM response → not in output."""
    item = _make_excerpt_item(url="https://example.com/missing")
    client = TestLLMClient(responses=["[]"])  # empty array — URL not mentioned
    result = Summarizer(client, _make_config(), _make_profile()).summarize([item])
    assert result == []


def test_extra_url_in_response_not_in_input_ignored() -> None:
    """URL in LLM response that was not in the input batch → ignored."""
    item = _make_excerpt_item(url="https://example.com/real")
    extra_url = "https://example.com/hallucinated"
    response = _llm_response_multi([(item.url, 7, "Good."), (extra_url, 9, "Extra.")])
    client = TestLLMClient(responses=[response])
    result = Summarizer(client, _make_config(), _make_profile()).summarize([item])
    result_urls = {r.url for r in result}
    assert extra_url not in result_urls


# ---------------------------------------------------------------------------
# Out-of-range score
# ---------------------------------------------------------------------------


def test_score_above_10_skips_item() -> None:
    item = _make_excerpt_item()
    client = TestLLMClient(
        responses=[json.dumps([{"url": item.url, "score": 11, "summary": "Too high."}])]
    )
    result = Summarizer(client, _make_config(), _make_profile(threshold=1)).summarize([item])
    assert result == []


def test_score_below_1_skips_item() -> None:
    item = _make_excerpt_item()
    client = TestLLMClient(
        responses=[json.dumps([{"url": item.url, "score": 0, "summary": "Too low."}])]
    )
    result = Summarizer(client, _make_config(), _make_profile(threshold=1)).summarize([item])
    assert result == []


def test_valid_item_not_affected_by_sibling_with_invalid_score() -> None:
    """Invalid-score item is skipped; valid sibling in same batch still returned."""
    bad = _make_excerpt_item(url="https://example.com/bad")
    good = _make_excerpt_item(url="https://example.com/good")
    response = _llm_response_multi([(bad.url, 11, "Invalid score."), (good.url, 8, "Valid.")])
    client = TestLLMClient(responses=[response])
    result = Summarizer(client, _make_config(), _make_profile(threshold=1)).summarize([bad, good])
    assert len(result) == 1
    assert result[0].url == "https://example.com/good"


# ---------------------------------------------------------------------------
# Contract
# ---------------------------------------------------------------------------


def test_return_type_is_list() -> None:
    client = TestLLMClient(responses=["[]"])
    result = Summarizer(client, _make_config(), _make_profile()).summarize([_make_excerpt_item()])
    assert isinstance(result, list)


def test_return_items_are_scored_item_instances() -> None:
    item = _make_excerpt_item()
    client = TestLLMClient(responses=[_llm_response(url=item.url)])
    result = Summarizer(client, _make_config(), _make_profile()).summarize([item])
    assert all(isinstance(r, ScoredItem) for r in result)


def test_constructor_has_expected_parameters() -> None:
    """Summarizer.__init__ must accept client, config, profile."""
    params = list(inspect.signature(Summarizer.__init__).parameters.keys())
    assert "client" in params
    assert "config" in params
    assert "profile" in params
