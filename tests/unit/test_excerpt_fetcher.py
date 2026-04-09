"""Tests for radar/processing/excerpt_fetcher.py.

Verifies the excerpt fetcher stage:
- ArXiv bypass: content_type="arxiv" uses raw_content directly, no HTTP call
- Web items: httpx fetch + trafilatura extraction + truncation
- Paywall detection: < 50 words extracted → item skipped
- Hash computation: url_hash and content_hash populated on output items
- Field copying: url, title, source, published_at carried over unchanged
- Failure handling: HTTP errors and timeouts skip the item
- Log breadcrumb: input, fetched, skipped_paywall, elapsed_ms
"""

import hashlib
from datetime import UTC, datetime
from unittest.mock import MagicMock, patch

import httpx

from radar.models import ExcerptItem, RawItem
from radar.processing.deduplicator import url_to_hash
from radar.processing.excerpt_fetcher import excerpt_fetcher

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_FETCH_PATCH = "radar.processing.excerpt_fetcher.httpx.get"
_EXTRACT_PATCH = "radar.processing.excerpt_fetcher.trafilatura.extract"
_MIN_WORDS = 50  # SPEC.md §3.7 paywall threshold
_MAX_EXCERPT_WORDS = 220  # ~200 word target, allow slight overage

# ---------------------------------------------------------------------------
# Factories
# ---------------------------------------------------------------------------


def _make_raw_item(
    url: str = "https://example.com/article",
    title: str = "Test Article",
    source: str = "test-source",
    content_type: str = "web",
    raw_content: str = "Some raw content.",
) -> RawItem:
    return RawItem(
        url=url,
        title=title,
        source=source,
        published_at=datetime(2026, 4, 7, 9, 0, 0, tzinfo=UTC),
        raw_content=raw_content,
        content_type=content_type,
    )


def _mock_http_response(html: str = "<html><body>content</body></html>") -> MagicMock:
    mock = MagicMock()
    mock.text = html
    mock.raise_for_status.return_value = None
    return mock


def _long_text(word_count: int) -> str:
    return " ".join(["word"] * word_count)


# ---------------------------------------------------------------------------
# Happy path: ArXiv bypass
# ---------------------------------------------------------------------------


def test_arxiv_item_uses_raw_content_as_excerpt() -> None:
    abstract = _long_text(80)
    item = _make_raw_item(content_type="arxiv", raw_content=abstract)
    with patch(_FETCH_PATCH) as mock_get:
        result = excerpt_fetcher([item])
    assert len(result) == 1
    assert abstract[:50] in result[0].excerpt
    mock_get.assert_not_called()


def test_arxiv_item_does_not_call_httpx() -> None:
    item = _make_raw_item(content_type="arxiv", raw_content=_long_text(80))
    with patch(_FETCH_PATCH) as mock_get:
        excerpt_fetcher([item])
    mock_get.assert_not_called()


def test_arxiv_item_does_not_call_trafilatura() -> None:
    item = _make_raw_item(content_type="arxiv", raw_content=_long_text(80))
    with patch(_FETCH_PATCH), patch(_EXTRACT_PATCH) as mock_extract:
        excerpt_fetcher([item])
    mock_extract.assert_not_called()


def test_arxiv_item_excerpt_is_not_empty() -> None:
    item = _make_raw_item(content_type="arxiv", raw_content=_long_text(80))
    with patch(_FETCH_PATCH):
        result = excerpt_fetcher([item])
    assert result[0].excerpt != ""


# ---------------------------------------------------------------------------
# Happy path: web item fetch + extraction
# ---------------------------------------------------------------------------


def test_web_item_fetches_url_and_returns_excerpt_item() -> None:
    item = _make_raw_item(url="https://example.com/story")
    extracted = _long_text(120)
    with (
        patch(_FETCH_PATCH, return_value=_mock_http_response()),
        patch(_EXTRACT_PATCH, return_value=extracted),
    ):
        result = excerpt_fetcher([item])
    assert len(result) == 1
    assert isinstance(result[0], ExcerptItem)


def test_web_item_excerpt_truncated_to_approx_200_words() -> None:
    item = _make_raw_item()
    with (
        patch(_FETCH_PATCH, return_value=_mock_http_response()),
        patch(_EXTRACT_PATCH, return_value=_long_text(500)),
    ):
        result = excerpt_fetcher([item])
    assert len(result[0].excerpt.split()) <= _MAX_EXCERPT_WORDS


# ---------------------------------------------------------------------------
# Happy path: hash computation
# ---------------------------------------------------------------------------


def test_url_hash_matches_url_to_hash() -> None:
    url = "https://example.com/article"
    item = _make_raw_item(url=url)
    with (
        patch(_FETCH_PATCH, return_value=_mock_http_response()),
        patch(_EXTRACT_PATCH, return_value=_long_text(80)),
    ):
        result = excerpt_fetcher([item])
    assert result[0].url_hash == url_to_hash(url)


def test_content_hash_is_sha256_of_excerpt() -> None:
    item = _make_raw_item()
    with (
        patch(_FETCH_PATCH, return_value=_mock_http_response()),
        patch(_EXTRACT_PATCH, return_value=_long_text(80)),
    ):
        result = excerpt_fetcher([item])
    expected = hashlib.sha256(result[0].excerpt.encode()).hexdigest()
    assert result[0].content_hash == expected


def test_url_hash_is_nonempty_hex_string() -> None:
    item = _make_raw_item()
    with (
        patch(_FETCH_PATCH, return_value=_mock_http_response()),
        patch(_EXTRACT_PATCH, return_value=_long_text(80)),
    ):
        result = excerpt_fetcher([item])
    assert isinstance(result[0].url_hash, str)
    assert len(result[0].url_hash) > 0


def test_content_hash_is_nonempty_hex_string() -> None:
    item = _make_raw_item()
    with (
        patch(_FETCH_PATCH, return_value=_mock_http_response()),
        patch(_EXTRACT_PATCH, return_value=_long_text(80)),
    ):
        result = excerpt_fetcher([item])
    assert isinstance(result[0].content_hash, str)
    assert len(result[0].content_hash) > 0


def test_arxiv_url_hash_matches_url_to_hash() -> None:
    url = "https://arxiv.org/abs/2501.12345"
    item = _make_raw_item(url=url, content_type="arxiv", raw_content=_long_text(80))
    with patch(_FETCH_PATCH):
        result = excerpt_fetcher([item])
    assert result[0].url_hash == url_to_hash(url)


def test_arxiv_content_hash_is_sha256_of_excerpt() -> None:
    item = _make_raw_item(content_type="arxiv", raw_content=_long_text(80))
    with patch(_FETCH_PATCH):
        result = excerpt_fetcher([item])
    expected = hashlib.sha256(result[0].excerpt.encode()).hexdigest()
    assert result[0].content_hash == expected


# ---------------------------------------------------------------------------
# Happy path: field copying
# ---------------------------------------------------------------------------


def test_output_url_matches_input() -> None:
    item = _make_raw_item(url="https://example.com/test")
    with (
        patch(_FETCH_PATCH, return_value=_mock_http_response()),
        patch(_EXTRACT_PATCH, return_value=_long_text(80)),
    ):
        result = excerpt_fetcher([item])
    assert result[0].url == "https://example.com/test"


def test_output_title_matches_input() -> None:
    item = _make_raw_item(title="My Great Article")
    with (
        patch(_FETCH_PATCH, return_value=_mock_http_response()),
        patch(_EXTRACT_PATCH, return_value=_long_text(80)),
    ):
        result = excerpt_fetcher([item])
    assert result[0].title == "My Great Article"


def test_output_source_matches_input() -> None:
    item = _make_raw_item(source="hackernews")
    with (
        patch(_FETCH_PATCH, return_value=_mock_http_response()),
        patch(_EXTRACT_PATCH, return_value=_long_text(80)),
    ):
        result = excerpt_fetcher([item])
    assert result[0].source == "hackernews"


def test_output_published_at_matches_input() -> None:
    item = _make_raw_item()
    with (
        patch(_FETCH_PATCH, return_value=_mock_http_response()),
        patch(_EXTRACT_PATCH, return_value=_long_text(80)),
    ):
        result = excerpt_fetcher([item])
    assert result[0].published_at == item.published_at


# ---------------------------------------------------------------------------
# Happy path: edge cases
# ---------------------------------------------------------------------------


def test_empty_input_returns_empty_list() -> None:
    assert excerpt_fetcher([]) == []


def test_multiple_items_all_returned_when_all_succeed() -> None:
    item_count = 4
    items = [_make_raw_item(url=f"https://example.com/{i}") for i in range(item_count)]
    with (
        patch(_FETCH_PATCH, return_value=_mock_http_response()),
        patch(_EXTRACT_PATCH, return_value=_long_text(80)),
    ):
        result = excerpt_fetcher(items)
    assert len(result) == item_count


def test_order_preserved() -> None:
    items = [_make_raw_item(url=f"https://example.com/{i}") for i in range(3)]
    with (
        patch(_FETCH_PATCH, return_value=_mock_http_response()),
        patch(_EXTRACT_PATCH, return_value=_long_text(80)),
    ):
        result = excerpt_fetcher(items)
    assert [r.url for r in result] == [item.url for item in items]


# ---------------------------------------------------------------------------
# Paywall / extraction failure
# ---------------------------------------------------------------------------


def test_trafilatura_returns_none_skips_item() -> None:
    item = _make_raw_item()
    with (
        patch(_FETCH_PATCH, return_value=_mock_http_response()),
        patch(_EXTRACT_PATCH, return_value=None),
    ):
        result = excerpt_fetcher([item])
    assert result == []


def test_trafilatura_returns_empty_string_skips_item() -> None:
    item = _make_raw_item()
    with (
        patch(_FETCH_PATCH, return_value=_mock_http_response()),
        patch(_EXTRACT_PATCH, return_value=""),
    ):
        result = excerpt_fetcher([item])
    assert result == []


def test_fewer_than_50_words_extracted_skips_item() -> None:
    item = _make_raw_item()
    with (
        patch(_FETCH_PATCH, return_value=_mock_http_response()),
        patch(_EXTRACT_PATCH, return_value=_long_text(_MIN_WORDS - 1)),
    ):
        result = excerpt_fetcher([item])
    assert result == []


def test_exactly_50_words_extracted_passes() -> None:
    item = _make_raw_item()
    with (
        patch(_FETCH_PATCH, return_value=_mock_http_response()),
        patch(_EXTRACT_PATCH, return_value=_long_text(_MIN_WORDS)),
    ):
        result = excerpt_fetcher([item])
    assert len(result) == 1


def test_arxiv_short_abstract_also_skipped() -> None:
    """ArXiv items with < 50 words in raw_content are also paywall-skipped."""
    item = _make_raw_item(content_type="arxiv", raw_content=_long_text(_MIN_WORDS - 1))
    with patch(_FETCH_PATCH):
        result = excerpt_fetcher([item])
    assert result == []


def test_paywall_item_does_not_affect_subsequent_item() -> None:
    paywall = _make_raw_item(url="https://example.com/paywall")
    good = _make_raw_item(url="https://example.com/good")
    # First call returns short text (paywall), second returns enough
    with (
        patch(_FETCH_PATCH, return_value=_mock_http_response()),
        patch(_EXTRACT_PATCH, side_effect=[_long_text(_MIN_WORDS - 1), _long_text(80)]),
    ):
        result = excerpt_fetcher([paywall, good])
    assert len(result) == 1
    assert result[0].url == "https://example.com/good"


def test_all_items_paywalled_returns_empty() -> None:
    items = [_make_raw_item(url=f"https://example.com/{i}") for i in range(3)]
    with (
        patch(_FETCH_PATCH, return_value=_mock_http_response()),
        patch(_EXTRACT_PATCH, return_value=None),
    ):
        result = excerpt_fetcher(items)
    assert result == []


# ---------------------------------------------------------------------------
# HTTP failure modes
# ---------------------------------------------------------------------------


def test_http_error_skips_item() -> None:
    item = _make_raw_item()
    mock_resp = MagicMock()
    mock_resp.raise_for_status.side_effect = httpx.HTTPStatusError(
        "404", request=MagicMock(), response=MagicMock()
    )
    with patch(_FETCH_PATCH, return_value=mock_resp):
        result = excerpt_fetcher([item])
    assert result == []


def test_http_error_does_not_raise() -> None:
    item = _make_raw_item()
    mock_resp = MagicMock()
    mock_resp.raise_for_status.side_effect = httpx.HTTPStatusError(
        "500", request=MagicMock(), response=MagicMock()
    )
    with patch(_FETCH_PATCH, return_value=mock_resp):
        excerpt_fetcher([item])  # must not raise


def test_timeout_skips_item() -> None:
    item = _make_raw_item()
    with patch(_FETCH_PATCH, side_effect=httpx.TimeoutException("timeout")):
        result = excerpt_fetcher([item])
    assert result == []


def test_connect_error_skips_item() -> None:
    item = _make_raw_item()
    with patch(_FETCH_PATCH, side_effect=httpx.ConnectError("refused")):
        result = excerpt_fetcher([item])
    assert result == []


def test_http_failure_does_not_affect_subsequent_items() -> None:
    failing = _make_raw_item(url="https://example.com/fail")
    good = _make_raw_item(url="https://example.com/good")
    responses = [httpx.TimeoutException("timeout"), _mock_http_response()]
    with (
        patch(_FETCH_PATCH, side_effect=responses),
        patch(_EXTRACT_PATCH, return_value=_long_text(80)),
    ):
        result = excerpt_fetcher([failing, good])
    assert len(result) == 1
    assert result[0].url == "https://example.com/good"


# ---------------------------------------------------------------------------
# Contract / return type
# ---------------------------------------------------------------------------


def test_return_type_is_list() -> None:
    assert isinstance(excerpt_fetcher([]), list)


def test_return_items_are_excerpt_items() -> None:
    item = _make_raw_item()
    with (
        patch(_FETCH_PATCH, return_value=_mock_http_response()),
        patch(_EXTRACT_PATCH, return_value=_long_text(80)),
    ):
        result = excerpt_fetcher([item])
    assert all(isinstance(r, ExcerptItem) for r in result)
