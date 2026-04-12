"""Tests for radar/processing/pre_filter.py.

Verifies keyword-based pre-filtering of ExcerptItems:
- Case-insensitive substring matching against title and excerpt
- OR semantics across keywords
- Edge cases: empty inputs, empty fields, large lists
- Contract: return type, identity (not copies), order preservation
"""

from datetime import UTC, datetime

from radar.models import ExcerptItem
from radar.processing.pre_filter import pre_filter


def _make_excerpt_item(
    title: str = "Default Title",
    excerpt: str = "Default excerpt.",
    url: str = "https://example.com/article",
) -> ExcerptItem:
    return ExcerptItem(
        url=url,
        title=title,
        source="test",
        published_at=datetime(2026, 4, 7, 9, 0, 0, tzinfo=UTC),
        excerpt=excerpt,
        url_hash="abc123",
        content_hash="def456",
    )


# ---------------------------------------------------------------------------
# Happy path — title match
# ---------------------------------------------------------------------------


def test_keyword_matches_title() -> None:
    item = _make_excerpt_item(title="New LLM benchmark released")
    result = pre_filter([item], ["LLM"])
    assert result == [item]


def test_keyword_matches_excerpt() -> None:
    item = _make_excerpt_item(excerpt="Researchers publish a new LLM benchmark.")
    result = pre_filter([item], ["LLM"])
    assert result == [item]


# ---------------------------------------------------------------------------
# Case-insensitivity
# ---------------------------------------------------------------------------


def test_case_insensitive_lower_keyword() -> None:
    item = _make_excerpt_item(title="New LLM paper published")
    result = pre_filter([item], ["llm"])
    assert result == [item]


def test_case_insensitive_mixed_title() -> None:
    item = _make_excerpt_item(title="New Llm paper published")
    result = pre_filter([item], ["LLM"])
    assert result == [item]


def test_case_insensitive_upper_title() -> None:
    item = _make_excerpt_item(title="LLM AND LARGE MODELS")
    result = pre_filter([item], ["llm"])
    assert result == [item]


def test_case_insensitive_substring_in_sentence() -> None:
    item = _make_excerpt_item(title="This LLM paper is great")
    result = pre_filter([item], ["LLM"])
    assert result == [item]


# ---------------------------------------------------------------------------
# Multi-word keywords
# ---------------------------------------------------------------------------


def test_multiword_keyword_matches_title() -> None:
    item = _make_excerpt_item(title="LLM inference and serving at scale")
    result = pre_filter([item], ["LLM inference"])
    assert result == [item]


def test_multiword_interest_matches_on_individual_token() -> None:
    """'LLM inference' should match a title containing just 'LLM' (tokenized matching)."""
    item = _make_excerpt_item(title="LLM paper published")
    result = pre_filter([item], ["LLM inference"])
    assert result == [item]


# ---------------------------------------------------------------------------
# OR semantics
# ---------------------------------------------------------------------------


def test_any_keyword_matches_or_semantics() -> None:
    item = _make_excerpt_item(title="Transformer architecture advances")
    result = pre_filter([item], ["LLM", "transformer"])
    assert result == [item]


def test_item_passes_if_second_keyword_matches() -> None:
    item = _make_excerpt_item(title="Reinforcement learning from human feedback")
    result = pre_filter([item], ["LLM", "reinforcement learning"])
    assert result == [item]


def test_item_filtered_out_if_no_keyword_matches() -> None:
    item = _make_excerpt_item(title="Stock market rally continues")
    result = pre_filter([item], ["LLM", "transformer"])
    assert result == []


# ---------------------------------------------------------------------------
# All-pass / all-fail / empty cases
# ---------------------------------------------------------------------------


def test_all_items_pass() -> None:
    items = [
        _make_excerpt_item(title="LLM news", url="https://example.com/1"),
        _make_excerpt_item(title="Another LLM update", url="https://example.com/2"),
    ]
    result = pre_filter(items, ["LLM"])
    assert result == items


def test_no_items_pass_returns_empty() -> None:
    items = [
        _make_excerpt_item(title="Sports recap", url="https://example.com/1"),
        _make_excerpt_item(title="Weather update", url="https://example.com/2"),
    ]
    result = pre_filter(items, ["LLM"])
    assert result == []


def test_empty_interests_returns_empty() -> None:
    item = _make_excerpt_item(title="LLM paper")
    result = pre_filter([item], [])
    assert result == []


def test_empty_input_returns_empty() -> None:
    result = pre_filter([], ["LLM"])
    assert result == []


# ---------------------------------------------------------------------------
# Failure mode / edge cases
# ---------------------------------------------------------------------------


def test_empty_title_and_excerpt_does_not_raise_and_does_not_match() -> None:
    item = _make_excerpt_item(title="", excerpt="")
    result = pre_filter([item], ["LLM"])
    assert result == []


def test_single_char_keyword_matches_if_substring() -> None:
    item = _make_excerpt_item(title="AI models are great")
    result = pre_filter([item], ["a"])
    assert result == [item]


def test_large_list_returns_correct_subset() -> None:
    matching = [
        _make_excerpt_item(title=f"LLM topic {i}", url=f"https://example.com/{i}")
        for i in range(100)
    ]
    non_matching = [
        _make_excerpt_item(title=f"Unrelated topic {i}", url=f"https://example.com/x{i}")
        for i in range(100)
    ]
    items = matching + non_matching
    result = pre_filter(items, ["LLM"])
    assert result == matching


# ---------------------------------------------------------------------------
# Contract / interface tests
# ---------------------------------------------------------------------------


def test_return_type_is_list_of_excerpt_items() -> None:
    item = _make_excerpt_item(title="LLM paper")
    result = pre_filter([item], ["LLM"])
    assert isinstance(result, list)
    assert all(isinstance(x, ExcerptItem) for x in result)


def test_returned_items_are_original_objects_not_copies() -> None:
    item = _make_excerpt_item(title="LLM paper")
    result = pre_filter([item], ["LLM"])
    assert result[0] is item


def test_order_of_returned_items_preserved() -> None:
    items = [
        _make_excerpt_item(title="LLM paper A", url="https://example.com/a"),
        _make_excerpt_item(title="LLM paper B", url="https://example.com/b"),
        _make_excerpt_item(title="LLM paper C", url="https://example.com/c"),
    ]
    result = pre_filter(items, ["LLM"])
    assert [r.url for r in result] == [
        "https://example.com/a",
        "https://example.com/b",
        "https://example.com/c",
    ]


def test_non_matching_item_not_in_result() -> None:
    matching = _make_excerpt_item(title="LLM paper", url="https://example.com/match")
    non_matching = _make_excerpt_item(title="Stock market", url="https://example.com/nomatch")
    result = pre_filter([matching, non_matching], ["LLM"])
    assert matching in result
    assert non_matching not in result


# ---------------------------------------------------------------------------
# Excerpt match contract
# ---------------------------------------------------------------------------


def test_excerpt_match_returns_original_object() -> None:
    item = _make_excerpt_item(title="Unrelated title", excerpt="Deep dive into LLMs.")
    result = pre_filter([item], ["LLM"])
    assert result == [item]
    assert result[0] is item
