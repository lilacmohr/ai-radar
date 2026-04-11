"""Tests for radar/llm/synthesizer.py.

Verifies the Synthesizer stage (LLM Pass 2):
- Happy path: list[FullItem] → Digest with all four sections populated
- Section parsing: each markdown heading maps to the correct Digest field
- articles: list[ScoredItem] constructed from FullItem inputs; full_text discarded
- date: today's date
- Single LLM call for all articles
- Empty input: Digest with empty text fields and articles=[]
- Failure modes: missing section → "", out-of-order sections, empty response
- Exception propagation: LLMClient errors propagate out of synthesize()
- Contract: return type Digest, constructor signature, articles type, date type
"""

# 1. Standard library imports
import datetime

# 2. Third-party imports
import pytest

# 3. Internal imports
from radar.config import PipelineConfig, ProfileConfig
from radar.llm.synthesizer import Synthesizer
from radar.models import Digest, FullItem, ScoredItem
from tests.conftest import TestLLMClient

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_CANNED_RESPONSE = """\
## 📡 Executive Summary
- Point one
- Point two

## 🔍 Contrarian & Non-Obvious Insights
Observation one.

## ❓ Follow-Up Questions & Rabbit Holes
Question one?

## 📈 Trending Themes
Theme one.
"""

_DEFAULT_PUBLISHED_AT = datetime.datetime(2026, 4, 11, 9, 0, 0, tzinfo=datetime.UTC)

# ---------------------------------------------------------------------------
# Factories
# ---------------------------------------------------------------------------


def _make_full_item(**kwargs: object) -> FullItem:
    defaults: dict[str, object] = {
        "url": "https://example.com/article",
        "title": "Test Article",
        "source": "test-source",
        "published_at": _DEFAULT_PUBLISHED_AT,
        "full_text": "This is the full text of the article with enough words.",
        "word_count": 10,
        "score": 7,
        "summary": "A summary.",
    }
    defaults.update(kwargs)
    return FullItem(**defaults)  # type: ignore[arg-type]


def _make_synthesizer(responses: list[str] | None = None) -> tuple[Synthesizer, TestLLMClient]:
    client = TestLLMClient(responses=responses or [_CANNED_RESPONSE])
    config = PipelineConfig()
    profile = ProfileConfig(role="Engineering Lead", interests=["AI", "architecture"])
    return Synthesizer(client, config, profile), client


# ---------------------------------------------------------------------------
# Happy path: Digest fields populated
# ---------------------------------------------------------------------------


def test_returns_digest() -> None:
    synthesizer, _ = _make_synthesizer()
    result = synthesizer.synthesize([_make_full_item()])
    assert isinstance(result, Digest)


def test_executive_summary_populated() -> None:
    synthesizer, _ = _make_synthesizer()
    result = synthesizer.synthesize([_make_full_item()])
    assert "Point one" in result.executive_summary


def test_contrarian_insights_populated() -> None:
    synthesizer, _ = _make_synthesizer()
    result = synthesizer.synthesize([_make_full_item()])
    assert "Observation one" in result.contrarian_insights


def test_follow_up_questions_populated() -> None:
    synthesizer, _ = _make_synthesizer()
    result = synthesizer.synthesize([_make_full_item()])
    assert "Question one" in result.follow_up_questions


def test_trending_themes_populated() -> None:
    synthesizer, _ = _make_synthesizer()
    result = synthesizer.synthesize([_make_full_item()])
    assert "Theme one" in result.trending_themes


# ---------------------------------------------------------------------------
# Happy path: articles converted to ScoredItem
# ---------------------------------------------------------------------------


def test_articles_is_list_of_scored_items() -> None:
    item = _make_full_item()
    synthesizer, _ = _make_synthesizer()
    result = synthesizer.synthesize([item])
    assert all(isinstance(a, ScoredItem) for a in result.articles)


def test_articles_length_matches_input() -> None:
    item_count = 3
    items = [_make_full_item(url=f"https://example.com/{i}") for i in range(item_count)]
    synthesizer, _ = _make_synthesizer()
    result = synthesizer.synthesize(items)
    assert len(result.articles) == item_count


def test_articles_url_preserved() -> None:
    item = _make_full_item(url="https://example.com/specific")
    synthesizer, _ = _make_synthesizer()
    result = synthesizer.synthesize([item])
    assert result.articles[0].url == "https://example.com/specific"


def test_articles_title_preserved() -> None:
    item = _make_full_item(title="My Title")
    synthesizer, _ = _make_synthesizer()
    result = synthesizer.synthesize([item])
    assert result.articles[0].title == "My Title"


def test_articles_source_preserved() -> None:
    item = _make_full_item(source="hackernews")
    synthesizer, _ = _make_synthesizer()
    result = synthesizer.synthesize([item])
    assert result.articles[0].source == "hackernews"


def test_articles_published_at_preserved() -> None:
    item = _make_full_item()
    synthesizer, _ = _make_synthesizer()
    result = synthesizer.synthesize([item])
    assert result.articles[0].published_at == _DEFAULT_PUBLISHED_AT


def test_articles_score_preserved() -> None:
    score = 8
    item = _make_full_item(score=score)
    synthesizer, _ = _make_synthesizer()
    result = synthesizer.synthesize([item])
    assert result.articles[0].score == score


def test_articles_summary_preserved() -> None:
    item = _make_full_item(summary="Important insight.")
    synthesizer, _ = _make_synthesizer()
    result = synthesizer.synthesize([item])
    assert result.articles[0].summary == "Important insight."


def test_articles_have_no_full_text() -> None:
    """ScoredItem does not have full_text — verify the field is absent."""
    item = _make_full_item()
    synthesizer, _ = _make_synthesizer()
    result = synthesizer.synthesize([item])
    assert not hasattr(result.articles[0], "full_text")


# ---------------------------------------------------------------------------
# Happy path: date and LLM call count
# ---------------------------------------------------------------------------


def test_digest_date_is_today() -> None:
    synthesizer, _ = _make_synthesizer()
    result = synthesizer.synthesize([_make_full_item()])
    assert result.date == datetime.datetime.now(tz=datetime.UTC).date()


def test_digest_date_is_date_type() -> None:
    synthesizer, _ = _make_synthesizer()
    result = synthesizer.synthesize([_make_full_item()])
    assert isinstance(result.date, datetime.date)
    assert not isinstance(result.date, datetime.datetime)


def test_single_llm_call_for_all_articles() -> None:
    items = [_make_full_item(url=f"https://example.com/{i}") for i in range(5)]
    synthesizer, client = _make_synthesizer()
    synthesizer.synthesize(items)
    assert client.call_count == 1


def test_profile_role_in_system_prompt() -> None:
    synthesizer, client = _make_synthesizer()
    synthesizer.synthesize([_make_full_item()])
    assert "Engineering Lead" in client.calls[0]["system"]


def test_profile_interests_in_system_prompt() -> None:
    synthesizer, client = _make_synthesizer()
    synthesizer.synthesize([_make_full_item()])
    assert "AI" in client.calls[0]["system"]


def test_article_full_text_in_llm_prompt() -> None:
    unique_text = "uniquesentinel " * 60
    item = _make_full_item(full_text=unique_text.strip(), word_count=60)
    synthesizer, client = _make_synthesizer()
    synthesizer.synthesize([item])
    assert "uniquesentinel" in client.calls[0]["user"]


# ---------------------------------------------------------------------------
# Happy path: empty input
# ---------------------------------------------------------------------------


def test_empty_input_returns_digest() -> None:
    synthesizer, _ = _make_synthesizer(responses=[""])
    result = synthesizer.synthesize([])
    assert isinstance(result, Digest)


def test_empty_input_articles_is_empty_list() -> None:
    synthesizer, _ = _make_synthesizer(responses=[""])
    result = synthesizer.synthesize([])
    assert result.articles == []


def test_empty_input_executive_summary_is_empty() -> None:
    synthesizer, _ = _make_synthesizer(responses=[""])
    result = synthesizer.synthesize([])
    assert result.executive_summary == ""


def test_empty_input_no_llm_call() -> None:
    synthesizer, client = _make_synthesizer(responses=[""])
    synthesizer.synthesize([])
    assert client.call_count == 0


# ---------------------------------------------------------------------------
# Failure modes: missing or reordered sections
# ---------------------------------------------------------------------------


def test_missing_section_returns_empty_string() -> None:
    # Response has only three of the four sections
    partial_response = """\
## 📡 Executive Summary
- Only section present.

## 🔍 Contrarian & Non-Obvious Insights
Observation.

## 📈 Trending Themes
Theme.
"""
    client = TestLLMClient(responses=[partial_response])
    config = PipelineConfig()
    profile = ProfileConfig(interests=["AI"])
    synthesizer = Synthesizer(client, config, profile)
    result = synthesizer.synthesize([_make_full_item()])
    assert result.follow_up_questions == ""


def test_out_of_order_sections_parsed_correctly() -> None:
    reordered = """\
## 📈 Trending Themes
Theme first.

## ❓ Follow-Up Questions & Rabbit Holes
Question second.

## 🔍 Contrarian & Non-Obvious Insights
Insight third.

## 📡 Executive Summary
Summary last.
"""
    client = TestLLMClient(responses=[reordered])
    config = PipelineConfig()
    profile = ProfileConfig(interests=["AI"])
    synthesizer = Synthesizer(client, config, profile)
    result = synthesizer.synthesize([_make_full_item()])
    assert "Theme first" in result.trending_themes
    assert "Question second" in result.follow_up_questions
    assert "Insight third" in result.contrarian_insights
    assert "Summary last" in result.executive_summary


def test_empty_llm_response_all_fields_empty() -> None:
    client = TestLLMClient(responses=[""])
    config = PipelineConfig()
    profile = ProfileConfig(interests=["AI"])
    synthesizer = Synthesizer(client, config, profile)
    result = synthesizer.synthesize([_make_full_item()])
    assert result.executive_summary == ""
    assert result.contrarian_insights == ""
    assert result.follow_up_questions == ""
    assert result.trending_themes == ""


def test_empty_llm_response_does_not_raise() -> None:
    client = TestLLMClient(responses=[""])
    config = PipelineConfig()
    profile = ProfileConfig(interests=["AI"])
    synthesizer = Synthesizer(client, config, profile)
    # Must not raise
    synthesizer.synthesize([_make_full_item()])


def test_all_sections_empty_no_exception() -> None:
    response = """\
## 📡 Executive Summary

## 🔍 Contrarian & Non-Obvious Insights

## ❓ Follow-Up Questions & Rabbit Holes

## 📈 Trending Themes
"""
    client = TestLLMClient(responses=[response])
    config = PipelineConfig()
    profile = ProfileConfig(interests=["AI"])
    synthesizer = Synthesizer(client, config, profile)
    result = synthesizer.synthesize([_make_full_item()])
    assert result.executive_summary == ""
    assert result.contrarian_insights == ""
    assert result.follow_up_questions == ""
    assert result.trending_themes == ""


# ---------------------------------------------------------------------------
# Failure mode: LLMClient exception propagates
# ---------------------------------------------------------------------------


def test_llm_exception_propagates() -> None:
    class RaisingClient:
        def complete(
            self,
            system: str,  # noqa: ARG002
            user: str,  # noqa: ARG002
            model: str,  # noqa: ARG002
            response_format: dict[str, str] | None = None,  # noqa: ARG002
        ) -> str:
            msg = "API down"
            raise RuntimeError(msg)

    config = PipelineConfig()
    profile = ProfileConfig(interests=["AI"])
    synthesizer = Synthesizer(RaisingClient(), config, profile)  # type: ignore[arg-type]
    with pytest.raises(RuntimeError, match="API down"):
        synthesizer.synthesize([_make_full_item()])


# ---------------------------------------------------------------------------
# Contract tests
# ---------------------------------------------------------------------------


def test_constructor_accepts_client_config_profile() -> None:
    client = TestLLMClient()
    config = PipelineConfig()
    profile = ProfileConfig(interests=["AI"])
    synthesizer = Synthesizer(client, config, profile)
    assert synthesizer is not None


def test_return_type_is_digest() -> None:
    synthesizer, _ = _make_synthesizer()
    result = synthesizer.synthesize([_make_full_item()])
    assert isinstance(result, Digest)


def test_articles_type_is_list() -> None:
    synthesizer, _ = _make_synthesizer()
    result = synthesizer.synthesize([_make_full_item()])
    assert isinstance(result.articles, list)


def test_works_with_test_llm_client() -> None:
    synthesizer, _ = _make_synthesizer()
    result = synthesizer.synthesize([_make_full_item()])
    assert isinstance(result, Digest)


def test_source_stats_is_dict() -> None:
    synthesizer, _ = _make_synthesizer()
    result = synthesizer.synthesize([_make_full_item()])
    assert isinstance(result.source_stats, dict)


def test_source_stats_contains_synthesis_model() -> None:
    synthesizer, _ = _make_synthesizer()
    result = synthesizer.synthesize([_make_full_item()])
    assert result.source_stats.get("synthesis_model") == PipelineConfig().synthesis_model
