"""Tests for radar/processing/full_fetcher.py.

Verifies the full article fetcher stage:
- Happy path: ScoredItem → FullItem with correct fields
- Field carry-over: score, summary, url, title, source, published_at
- word_count: matches len(full_text.split())
- Paywall/extraction failure: trafilatura returns None → item skipped (INFO log)
- Short extraction: < 50 words → item skipped (INFO log)
- HTTP failures: TimeoutException, ConnectError → item skipped (WARNING log)
- Partial failure: failing items excluded, successful items returned
- All fail: returns []
- Empty input: returns [] without HTTP calls
- Multiple items: all returned when all succeed
- Contract: return type list[FullItem], constructor signature, word_count >= 0
"""

import logging
from datetime import UTC, datetime
from unittest.mock import MagicMock, patch

import httpx
import pytest

from radar.config import PipelineConfig
from radar.models import FullItem, ScoredItem
from radar.processing.full_fetcher import FullFetcher

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_FETCH_PATCH = "radar.processing.full_fetcher.httpx.get"
_EXTRACT_PATCH = "radar.processing.full_fetcher.trafilatura.extract"
_MIN_WORDS = 50
_SCORE_MIN = 1
_SCORE_MAX = 10

# ---------------------------------------------------------------------------
# Factories
# ---------------------------------------------------------------------------


_DEFAULT_URL = "https://example.com/article"
_DEFAULT_TITLE = "Test Article"
_DEFAULT_SOURCE = "test-source"
_DEFAULT_SCORE = 7
_DEFAULT_SUMMARY = "A brief summary."
_DEFAULT_EXCERPT = "Short excerpt."
_DEFAULT_PUBLISHED_AT = datetime(2026, 4, 11, 9, 0, 0, tzinfo=UTC)


def _make_scored_item(**kwargs: object) -> ScoredItem:
    defaults: dict[str, object] = {
        "url": _DEFAULT_URL,
        "title": _DEFAULT_TITLE,
        "source": _DEFAULT_SOURCE,
        "score": _DEFAULT_SCORE,
        "summary": _DEFAULT_SUMMARY,
        "excerpt": _DEFAULT_EXCERPT,
        "published_at": _DEFAULT_PUBLISHED_AT,
    }
    defaults.update(kwargs)
    return ScoredItem(**defaults)  # type: ignore[arg-type]


def _mock_http_response(html: str = "<html><body>content</body></html>") -> MagicMock:
    mock = MagicMock()
    mock.text = html
    mock.raise_for_status.return_value = None
    return mock


def _long_text(word_count: int) -> str:
    return " ".join(["word"] * word_count)


def _make_config() -> PipelineConfig:
    return PipelineConfig()


# ---------------------------------------------------------------------------
# Happy path: ScoredItem → FullItem
# ---------------------------------------------------------------------------


def test_returns_full_item_for_successful_fetch() -> None:
    item = _make_scored_item()
    with (
        patch(_FETCH_PATCH, return_value=_mock_http_response()),
        patch(_EXTRACT_PATCH, return_value=_long_text(80)),
    ):
        result = FullFetcher(_make_config()).fetch([item])
    assert len(result) == 1
    assert isinstance(result[0], FullItem)


def test_full_text_contains_extracted_body() -> None:
    extracted = _long_text(80)
    item = _make_scored_item()
    with (
        patch(_FETCH_PATCH, return_value=_mock_http_response()),
        patch(_EXTRACT_PATCH, return_value=extracted),
    ):
        result = FullFetcher(_make_config()).fetch([item])
    assert result[0].full_text == extracted


def test_word_count_matches_full_text_split() -> None:
    extracted = _long_text(80)
    item = _make_scored_item()
    with (
        patch(_FETCH_PATCH, return_value=_mock_http_response()),
        patch(_EXTRACT_PATCH, return_value=extracted),
    ):
        result = FullFetcher(_make_config()).fetch([item])
    assert result[0].word_count == len(extracted.split())


def test_score_carried_over_from_scored_item() -> None:
    score = 9
    item = _make_scored_item(score=score)
    with (
        patch(_FETCH_PATCH, return_value=_mock_http_response()),
        patch(_EXTRACT_PATCH, return_value=_long_text(80)),
    ):
        result = FullFetcher(_make_config()).fetch([item])
    assert result[0].score == score


def test_summary_carried_over_from_scored_item() -> None:
    item = _make_scored_item(summary="Important insight about AI.")
    with (
        patch(_FETCH_PATCH, return_value=_mock_http_response()),
        patch(_EXTRACT_PATCH, return_value=_long_text(80)),
    ):
        result = FullFetcher(_make_config()).fetch([item])
    assert result[0].summary == "Important insight about AI."


def test_url_carried_over_from_scored_item() -> None:
    item = _make_scored_item(url="https://example.com/specific")
    with (
        patch(_FETCH_PATCH, return_value=_mock_http_response()),
        patch(_EXTRACT_PATCH, return_value=_long_text(80)),
    ):
        result = FullFetcher(_make_config()).fetch([item])
    assert result[0].url == "https://example.com/specific"


def test_title_carried_over_from_scored_item() -> None:
    item = _make_scored_item(title="My Important Article")
    with (
        patch(_FETCH_PATCH, return_value=_mock_http_response()),
        patch(_EXTRACT_PATCH, return_value=_long_text(80)),
    ):
        result = FullFetcher(_make_config()).fetch([item])
    assert result[0].title == "My Important Article"


def test_source_carried_over_from_scored_item() -> None:
    item = _make_scored_item(source="hackernews")
    with (
        patch(_FETCH_PATCH, return_value=_mock_http_response()),
        patch(_EXTRACT_PATCH, return_value=_long_text(80)),
    ):
        result = FullFetcher(_make_config()).fetch([item])
    assert result[0].source == "hackernews"


def test_published_at_carried_over_from_scored_item() -> None:
    item = _make_scored_item()
    with (
        patch(_FETCH_PATCH, return_value=_mock_http_response()),
        patch(_EXTRACT_PATCH, return_value=_long_text(80)),
    ):
        result = FullFetcher(_make_config()).fetch([item])
    assert result[0].published_at == item.published_at


# ---------------------------------------------------------------------------
# Happy path: edge cases
# ---------------------------------------------------------------------------


def test_empty_input_returns_empty_list() -> None:
    with patch(_FETCH_PATCH) as mock_get:
        result = FullFetcher(_make_config()).fetch([])
    assert result == []
    mock_get.assert_not_called()


def test_multiple_items_all_returned_when_all_succeed() -> None:
    item_count = 4
    items = [_make_scored_item(url=f"https://example.com/{i}") for i in range(item_count)]
    with (
        patch(_FETCH_PATCH, return_value=_mock_http_response()),
        patch(_EXTRACT_PATCH, return_value=_long_text(80)),
    ):
        result = FullFetcher(_make_config()).fetch(items)
    assert len(result) == item_count


# ---------------------------------------------------------------------------
# Failure modes: paywall / extraction failure
# ---------------------------------------------------------------------------


def test_trafilatura_returns_none_skips_item() -> None:
    item = _make_scored_item()
    with (
        patch(_FETCH_PATCH, return_value=_mock_http_response()),
        patch(_EXTRACT_PATCH, return_value=None),
    ):
        result = FullFetcher(_make_config()).fetch([item])
    assert result == []


def test_trafilatura_returns_none_does_not_raise() -> None:
    item = _make_scored_item()
    with (
        patch(_FETCH_PATCH, return_value=_mock_http_response()),
        patch(_EXTRACT_PATCH, return_value=None),
    ):
        FullFetcher(_make_config()).fetch([item])  # must not raise


def test_trafilatura_returns_none_logs_info(caplog: pytest.LogCaptureFixture) -> None:
    item = _make_scored_item()
    with (
        patch(_FETCH_PATCH, return_value=_mock_http_response()),
        patch(_EXTRACT_PATCH, return_value=None),
        caplog.at_level(logging.INFO),
    ):
        FullFetcher(_make_config()).fetch([item])
    assert any("full_fetch_skipped_paywall" in r.message for r in caplog.records)


def test_fewer_than_50_words_skips_item() -> None:
    item = _make_scored_item()
    with (
        patch(_FETCH_PATCH, return_value=_mock_http_response()),
        patch(_EXTRACT_PATCH, return_value=_long_text(_MIN_WORDS - 1)),
    ):
        result = FullFetcher(_make_config()).fetch([item])
    assert result == []


def test_fewer_than_50_words_does_not_raise() -> None:
    item = _make_scored_item()
    with (
        patch(_FETCH_PATCH, return_value=_mock_http_response()),
        patch(_EXTRACT_PATCH, return_value=_long_text(_MIN_WORDS - 1)),
    ):
        FullFetcher(_make_config()).fetch([item])  # must not raise


def test_fewer_than_50_words_logs_info(caplog: pytest.LogCaptureFixture) -> None:
    item = _make_scored_item()
    with (
        patch(_FETCH_PATCH, return_value=_mock_http_response()),
        patch(_EXTRACT_PATCH, return_value=_long_text(_MIN_WORDS - 1)),
        caplog.at_level(logging.INFO),
    ):
        FullFetcher(_make_config()).fetch([item])
    assert any("full_fetch_skipped_short" in r.message for r in caplog.records)


def test_exactly_50_words_passes() -> None:
    item = _make_scored_item()
    with (
        patch(_FETCH_PATCH, return_value=_mock_http_response()),
        patch(_EXTRACT_PATCH, return_value=_long_text(_MIN_WORDS)),
    ):
        result = FullFetcher(_make_config()).fetch([item])
    assert len(result) == 1


# ---------------------------------------------------------------------------
# Failure modes: HTTP errors
# ---------------------------------------------------------------------------


def test_timeout_exception_skips_item() -> None:
    item = _make_scored_item()
    with patch(_FETCH_PATCH, side_effect=httpx.TimeoutException("timeout")):
        result = FullFetcher(_make_config()).fetch([item])
    assert result == []


def test_timeout_exception_does_not_raise() -> None:
    item = _make_scored_item()
    with patch(_FETCH_PATCH, side_effect=httpx.TimeoutException("timeout")):
        FullFetcher(_make_config()).fetch([item])  # must not raise


def test_timeout_exception_logs_warning(caplog: pytest.LogCaptureFixture) -> None:
    item = _make_scored_item()
    with (
        patch(_FETCH_PATCH, side_effect=httpx.TimeoutException("timeout")),
        caplog.at_level(logging.WARNING),
    ):
        FullFetcher(_make_config()).fetch([item])
    assert any("full_fetch_timeout" in r.message for r in caplog.records)


def test_connect_error_skips_item() -> None:
    item = _make_scored_item()
    with patch(_FETCH_PATCH, side_effect=httpx.ConnectError("refused")):
        result = FullFetcher(_make_config()).fetch([item])
    assert result == []


def test_connect_error_does_not_raise() -> None:
    item = _make_scored_item()
    with patch(_FETCH_PATCH, side_effect=httpx.ConnectError("refused")):
        FullFetcher(_make_config()).fetch([item])  # must not raise


def test_connect_error_logs_warning(caplog: pytest.LogCaptureFixture) -> None:
    item = _make_scored_item()
    with (
        patch(_FETCH_PATCH, side_effect=httpx.ConnectError("refused")),
        caplog.at_level(logging.WARNING),
    ):
        FullFetcher(_make_config()).fetch([item])
    assert any("full_fetch_connection_error" in r.message for r in caplog.records)


# ---------------------------------------------------------------------------
# Failure modes: all fail / partial failure
# ---------------------------------------------------------------------------


def test_all_items_fail_returns_empty_list() -> None:
    items = [_make_scored_item(url=f"https://example.com/{i}") for i in range(3)]
    with patch(_FETCH_PATCH, side_effect=httpx.TimeoutException("timeout")):
        result = FullFetcher(_make_config()).fetch(items)
    assert result == []


def test_one_item_fails_others_succeed() -> None:
    failing = _make_scored_item(url="https://example.com/fail")
    good1 = _make_scored_item(url="https://example.com/good1")
    good2 = _make_scored_item(url="https://example.com/good2")
    responses = [
        httpx.TimeoutException("timeout"),
        _mock_http_response(),
        _mock_http_response(),
    ]
    with (
        patch(_FETCH_PATCH, side_effect=responses),
        patch(_EXTRACT_PATCH, return_value=_long_text(80)),
    ):
        result = FullFetcher(_make_config()).fetch([failing, good1, good2])
    good_count = 2
    assert len(result) == good_count
    assert all(r.url != "https://example.com/fail" for r in result)


def test_paywall_item_does_not_affect_subsequent_items() -> None:
    paywall = _make_scored_item(url="https://example.com/paywall")
    good = _make_scored_item(url="https://example.com/good")
    with (
        patch(_FETCH_PATCH, return_value=_mock_http_response()),
        patch(_EXTRACT_PATCH, side_effect=[None, _long_text(80)]),
    ):
        result = FullFetcher(_make_config()).fetch([paywall, good])
    assert len(result) == 1
    assert result[0].url == "https://example.com/good"


# ---------------------------------------------------------------------------
# Contract tests
# ---------------------------------------------------------------------------


def test_return_type_is_list() -> None:
    assert isinstance(FullFetcher(_make_config()).fetch([]), list)


def test_return_items_are_full_items() -> None:
    item = _make_scored_item()
    with (
        patch(_FETCH_PATCH, return_value=_mock_http_response()),
        patch(_EXTRACT_PATCH, return_value=_long_text(80)),
    ):
        result = FullFetcher(_make_config()).fetch([item])
    assert all(isinstance(r, FullItem) for r in result)


def test_constructor_accepts_pipeline_config() -> None:
    config = PipelineConfig()
    fetcher = FullFetcher(config)
    assert fetcher is not None


def test_word_count_is_non_negative() -> None:
    item = _make_scored_item()
    with (
        patch(_FETCH_PATCH, return_value=_mock_http_response()),
        patch(_EXTRACT_PATCH, return_value=_long_text(80)),
    ):
        result = FullFetcher(_make_config()).fetch([item])
    assert all(r.word_count >= 0 for r in result)


def test_score_values_in_valid_range() -> None:
    items = [_make_scored_item(score=s) for s in [1, 5, 10]]
    with (
        patch(_FETCH_PATCH, return_value=_mock_http_response()),
        patch(_EXTRACT_PATCH, return_value=_long_text(80)),
    ):
        result = FullFetcher(_make_config()).fetch(items)
    assert all(_SCORE_MIN <= r.score <= _SCORE_MAX for r in result)
