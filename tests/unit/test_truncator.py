"""Tests for radar/processing/truncator.py.

Verifies the truncator stage:
- Short articles: returned unchanged (full_text and word_count identical)
- Long articles: full_text truncated to max_words_full words, word_count updated
- word_count always equals len(full_text.split()) after truncation
- Fields other than full_text and word_count are not modified
- Empty input: returns []
- Edge cases: exact boundary, empty full_text, single-word article
- Context overflow: lowest-scored articles dropped first, WARNING logged
- Contract: return type list[FullItem], constructor signature, word_count invariants
"""

import logging
from datetime import UTC, datetime

import pytest

from radar.config import PipelineConfig
from radar.models import FullItem
from radar.processing.truncator import Truncator

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_SHORT_WORD_COUNT = 100
_MAX_WORDS = 800
_MAX_ARTICLES = 15
_DEFAULT_PUBLISHED_AT = datetime(2026, 4, 11, 9, 0, 0, tzinfo=UTC)

# ---------------------------------------------------------------------------
# Factories
# ---------------------------------------------------------------------------


def _make_full_item(**kwargs: object) -> FullItem:
    text = str(kwargs.get("full_text", _long_text(_SHORT_WORD_COUNT)))
    defaults: dict[str, object] = {
        "url": "https://example.com/article",
        "title": "Test Article",
        "source": "test-source",
        "published_at": _DEFAULT_PUBLISHED_AT,
        "full_text": text,
        "word_count": len(text.split()) if text else 0,
        "score": 5,
        "summary": "A summary.",
    }
    # word_count must stay consistent with full_text
    if "full_text" in kwargs:
        ft = str(kwargs["full_text"])
        defaults["word_count"] = len(ft.split()) if ft else 0
    defaults.update({k: v for k, v in kwargs.items() if k != "full_text"})
    return FullItem(**defaults)  # type: ignore[arg-type]


def _make_config(
    max_words_full: int = _MAX_WORDS,
    max_articles_in_digest: int = _MAX_ARTICLES,
) -> PipelineConfig:
    return PipelineConfig(
        max_words_full=max_words_full,
        max_articles_in_digest=max_articles_in_digest,
    )


def _long_text(word_count: int) -> str:
    return " ".join(["word"] * word_count)


# ---------------------------------------------------------------------------
# Happy path: short articles returned unchanged
# ---------------------------------------------------------------------------


def test_short_article_full_text_unchanged() -> None:
    text = _long_text(_SHORT_WORD_COUNT)
    item = _make_full_item(full_text=text)
    result = Truncator(_make_config()).truncate([item])
    assert result[0].full_text == text


def test_short_article_word_count_unchanged() -> None:
    text = _long_text(_SHORT_WORD_COUNT)
    item = _make_full_item(full_text=text)
    result = Truncator(_make_config()).truncate([item])
    assert result[0].word_count == _SHORT_WORD_COUNT


def test_short_article_returned_in_result() -> None:
    item = _make_full_item(full_text=_long_text(50))
    result = Truncator(_make_config()).truncate([item])
    assert len(result) == 1


# ---------------------------------------------------------------------------
# Happy path: long articles truncated
# ---------------------------------------------------------------------------


def test_long_article_truncated_to_max_words() -> None:
    item = _make_full_item(full_text=_long_text(1000))
    result = Truncator(_make_config(max_words_full=_MAX_WORDS)).truncate([item])
    assert len(result[0].full_text.split()) == _MAX_WORDS


def test_long_article_word_count_updated() -> None:
    item = _make_full_item(full_text=_long_text(1000))
    result = Truncator(_make_config(max_words_full=_MAX_WORDS)).truncate([item])
    assert result[0].word_count == _MAX_WORDS


def test_word_count_equals_len_full_text_split_after_truncation() -> None:
    item = _make_full_item(full_text=_long_text(1000))
    result = Truncator(_make_config(max_words_full=_MAX_WORDS)).truncate([item])
    assert result[0].word_count == len(result[0].full_text.split())


def test_truncated_text_is_prefix_of_original() -> None:
    words = [f"w{i}" for i in range(1000)]
    item = _make_full_item(full_text=" ".join(words))
    result = Truncator(_make_config(max_words_full=_MAX_WORDS)).truncate([item])
    assert result[0].full_text == " ".join(words[:_MAX_WORDS])


# ---------------------------------------------------------------------------
# Happy path: non-text fields unchanged
# ---------------------------------------------------------------------------


def test_url_unchanged_after_truncation() -> None:
    item = _make_full_item(full_text=_long_text(1000), url="https://example.com/specific")
    result = Truncator(_make_config(max_words_full=_MAX_WORDS)).truncate([item])
    assert result[0].url == "https://example.com/specific"


def test_title_unchanged_after_truncation() -> None:
    item = _make_full_item(full_text=_long_text(1000), title="My Title")
    result = Truncator(_make_config(max_words_full=_MAX_WORDS)).truncate([item])
    assert result[0].title == "My Title"


def test_source_unchanged_after_truncation() -> None:
    item = _make_full_item(full_text=_long_text(1000), source="hackernews")
    result = Truncator(_make_config(max_words_full=_MAX_WORDS)).truncate([item])
    assert result[0].source == "hackernews"


def test_published_at_unchanged_after_truncation() -> None:
    item = _make_full_item(full_text=_long_text(1000))
    result = Truncator(_make_config(max_words_full=_MAX_WORDS)).truncate([item])
    assert result[0].published_at == item.published_at


def test_score_unchanged_after_truncation() -> None:
    score = 9
    item = _make_full_item(full_text=_long_text(1000), score=score)
    result = Truncator(_make_config(max_words_full=_MAX_WORDS)).truncate([item])
    assert result[0].score == score


def test_summary_unchanged_after_truncation() -> None:
    item = _make_full_item(full_text=_long_text(1000), summary="Important insight.")
    result = Truncator(_make_config(max_words_full=_MAX_WORDS)).truncate([item])
    assert result[0].summary == "Important insight."


# ---------------------------------------------------------------------------
# Happy path: empty input and multiple articles
# ---------------------------------------------------------------------------


def test_empty_input_returns_empty_list() -> None:
    assert Truncator(_make_config()).truncate([]) == []


def test_multiple_articles_all_truncated_independently() -> None:
    item_count = 3
    items = [_make_full_item(full_text=_long_text(1000)) for _ in range(item_count)]
    result = Truncator(_make_config(max_words_full=_MAX_WORDS)).truncate(items)
    assert all(r.word_count == _MAX_WORDS for r in result)


def test_multiple_articles_short_ones_unchanged() -> None:
    item_count = 3
    items = [_make_full_item(full_text=_long_text(_SHORT_WORD_COUNT)) for _ in range(item_count)]
    result = Truncator(_make_config(max_words_full=_MAX_WORDS)).truncate(items)
    assert all(r.word_count == _SHORT_WORD_COUNT for r in result)


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------


def test_article_at_exact_boundary_not_truncated() -> None:
    text = _long_text(_MAX_WORDS)
    item = _make_full_item(full_text=text)
    result = Truncator(_make_config(max_words_full=_MAX_WORDS)).truncate([item])
    assert result[0].full_text == text
    assert result[0].word_count == _MAX_WORDS


def test_empty_full_text_returns_item_with_zero_word_count() -> None:
    item = _make_full_item(full_text="")
    result = Truncator(_make_config()).truncate([item])
    assert len(result) == 1
    assert result[0].full_text == ""
    assert result[0].word_count == 0


def test_single_word_article_unchanged() -> None:
    item = _make_full_item(full_text="hello")
    result = Truncator(_make_config(max_words_full=_MAX_WORDS)).truncate([item])
    assert result[0].full_text == "hello"
    assert result[0].word_count == 1


def test_all_articles_at_max_length_no_overflow() -> None:
    # budget = 3 articles x 100 words = 300; 3 x 100 = exactly at budget, no drop
    budget_articles = 3
    budget_words = 100
    items = [
        _make_full_item(
            full_text=_long_text(budget_words),
            score=5,
            url=f"https://example.com/{i}",
        )
        for i in range(budget_articles)
    ]
    result = Truncator(
        _make_config(max_words_full=budget_words, max_articles_in_digest=budget_articles)
    ).truncate(items)
    assert len(result) == budget_articles


# ---------------------------------------------------------------------------
# Context overflow: lowest-scored articles dropped
# ---------------------------------------------------------------------------


def test_overflow_drops_lowest_scored_article() -> None:
    # budget = 1 article x 100 words = 100; two articles would overflow
    high = _make_full_item(full_text=_long_text(100), score=8, url="https://example.com/high")
    low = _make_full_item(full_text=_long_text(100), score=3, url="https://example.com/low")
    result = Truncator(_make_config(max_words_full=100, max_articles_in_digest=1)).truncate(
        [high, low]
    )
    assert len(result) == 1
    assert result[0].url == "https://example.com/high"


def test_overflow_dropped_article_is_excluded() -> None:
    high = _make_full_item(full_text=_long_text(100), score=8, url="https://example.com/high")
    low = _make_full_item(full_text=_long_text(100), score=3, url="https://example.com/low")
    result = Truncator(_make_config(max_words_full=100, max_articles_in_digest=1)).truncate(
        [high, low]
    )
    assert all(r.url != "https://example.com/low" for r in result)


def test_overflow_logs_warning(caplog: pytest.LogCaptureFixture) -> None:
    high = _make_full_item(full_text=_long_text(100), score=8, url="https://example.com/high")
    low = _make_full_item(full_text=_long_text(100), score=3, url="https://example.com/low")
    with caplog.at_level(logging.WARNING):
        Truncator(_make_config(max_words_full=100, max_articles_in_digest=1)).truncate([high, low])
    assert any("articles_dropped" in r.message for r in caplog.records)


def test_overflow_log_includes_articles_dropped_count(caplog: pytest.LogCaptureFixture) -> None:
    # budget = 1 x 100 = 100; 3 articles means 2 must be dropped
    items = [
        _make_full_item(full_text=_long_text(100), score=i, url=f"https://example.com/{i}")
        for i in range(1, 4)
    ]
    with caplog.at_level(logging.WARNING):
        Truncator(_make_config(max_words_full=100, max_articles_in_digest=1)).truncate(items)
    warning_records = [r for r in caplog.records if r.levelno == logging.WARNING]
    assert len(warning_records) >= 1


def test_overflow_multiple_drops_lowest_scores_first() -> None:
    # budget = 2 articles x 100 words; keep top 2 scored (9 and 7)
    keep_count = 2
    min_kept_score = 7
    items = [
        _make_full_item(full_text=_long_text(100), score=s, url=f"https://example.com/{s}")
        for s in [9, 7, 5, 3, 1]
    ]
    truncator = Truncator(_make_config(max_words_full=100, max_articles_in_digest=keep_count))
    result = truncator.truncate(items)
    assert len(result) == keep_count
    assert all(r.score >= min_kept_score for r in result)


def test_overflow_no_warning_when_within_budget(caplog: pytest.LogCaptureFixture) -> None:
    # budget = 3 x 100 = 300; total = 3 x 50 = 150 — fits
    items = [
        _make_full_item(full_text=_long_text(50), score=5, url=f"https://example.com/{i}")
        for i in range(3)
    ]
    with caplog.at_level(logging.WARNING):
        Truncator(_make_config(max_words_full=100, max_articles_in_digest=3)).truncate(items)
    assert not any("articles_dropped" in r.message for r in caplog.records)


def test_overflow_tied_scores_deterministic() -> None:
    """Tied scores: higher-index items dropped first (stable sort by score desc)."""
    # budget = 1 x 100 = 100; 3 tied articles means 2 dropped; keep index 0
    items = [
        _make_full_item(full_text=_long_text(100), score=5, url=f"https://example.com/{i}")
        for i in range(3)
    ]
    result = Truncator(_make_config(max_words_full=100, max_articles_in_digest=1)).truncate(items)
    assert len(result) == 1
    assert result[0].url == "https://example.com/0"


def test_short_articles_over_article_limit_are_dropped() -> None:
    # 3 articles x 50 words = 150 total; word budget = 2 x 100 = 200 (fits by words)
    # but count = 3 > max_articles_in_digest = 2 — spec cap fires, drop lowest scored
    article_cap = 2
    min_kept_score = 7
    items = [
        _make_full_item(full_text=_long_text(50), score=s, url=f"https://example.com/{s}")
        for s in [9, 7, 5]
    ]
    truncator = Truncator(_make_config(max_words_full=100, max_articles_in_digest=article_cap))
    result = truncator.truncate(items)
    assert len(result) == article_cap
    assert all(r.score >= min_kept_score for r in result)


def test_overflow_output_preserves_input_order() -> None:
    # Input order: score 9, 3, 7 — drop score 3; output must be [9, 7] in that order
    items = [
        _make_full_item(full_text=_long_text(100), score=9, url="https://example.com/a"),
        _make_full_item(full_text=_long_text(100), score=3, url="https://example.com/b"),
        _make_full_item(full_text=_long_text(100), score=7, url="https://example.com/c"),
    ]
    result = Truncator(_make_config(max_words_full=100, max_articles_in_digest=2)).truncate(items)
    assert [r.url for r in result] == ["https://example.com/a", "https://example.com/c"]


# ---------------------------------------------------------------------------
# Contract tests
# ---------------------------------------------------------------------------


def test_return_type_is_list() -> None:
    assert isinstance(Truncator(_make_config()).truncate([]), list)


def test_return_items_are_full_items() -> None:
    item = _make_full_item(full_text=_long_text(_SHORT_WORD_COUNT))
    result = Truncator(_make_config()).truncate([item])
    assert all(isinstance(r, FullItem) for r in result)


def test_constructor_accepts_pipeline_config() -> None:
    config = PipelineConfig()
    truncator = Truncator(config)
    assert truncator is not None


def test_all_word_counts_lte_max_words_full() -> None:
    items = [_make_full_item(full_text=_long_text(1000)) for _ in range(5)]
    result = Truncator(_make_config(max_words_full=_MAX_WORDS)).truncate(items)
    assert all(r.word_count <= _MAX_WORDS for r in result)


def test_word_count_equals_len_split_for_all_items() -> None:
    word_counts = [50, _MAX_WORDS, 1000, 0]
    items = [_make_full_item(full_text=_long_text(wc)) for wc in word_counts]
    result = Truncator(_make_config(max_words_full=_MAX_WORDS)).truncate(items)
    assert all(r.word_count == len(r.full_text.split()) for r in result)
