"""Tests for radar/sources/hn.py.

Verifies the Hacker News source connector:
- Field mapping from Algolia API response to RawItem
- Filtering: disabled connector, missing url/title
- Failure handling: HTTP errors and timeouts return []
- Contract: isinstance(Source), return type, timezone-aware published_at
"""

from datetime import UTC, datetime
from unittest.mock import MagicMock, patch

import httpx

from radar.config import HackerNewsConfig
from radar.models import RawItem
from radar.sources.base import Source
from radar.sources.hn import HNSource

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_ALGOLIA_PATCH = "radar.sources.hn.httpx.get"


def _make_config(
    *,
    enabled: bool = True,
    min_score: int = 50,
    keywords: list[str] | None = None,
) -> HackerNewsConfig:
    return HackerNewsConfig(
        enabled=enabled,
        min_score=min_score,
        keywords=keywords if keywords is not None else ["LLM", "AI"],
    )


def _make_hit(  # noqa: PLR0913
    object_id: str = "12345",
    title: str = "Test Story",
    url: str = "https://example.com/article",
    points: int = 150,
    num_comments: int = 42,
    created_at_i: int = 1744012800,
    author: str = "hnuser",
    story_text: str | None = None,
) -> dict:
    return {
        "objectID": object_id,
        "title": title,
        "url": url,
        "points": points,
        "num_comments": num_comments,
        "created_at_i": created_at_i,
        "author": author,
        "story_text": story_text,
    }


def _mock_response(hits: list[dict]) -> MagicMock:
    mock = MagicMock()
    mock.json.return_value = {"hits": hits}
    mock.raise_for_status.return_value = None
    return mock


# ---------------------------------------------------------------------------
# Happy path: field mapping
# ---------------------------------------------------------------------------


def test_fetch_returns_list_of_raw_items() -> None:
    with patch(_ALGOLIA_PATCH, return_value=_mock_response([_make_hit()])):
        result = HNSource(_make_config()).fetch()
    assert isinstance(result, list)
    assert all(isinstance(item, RawItem) for item in result)


def test_fetch_maps_url_correctly() -> None:
    hit = _make_hit(url="https://example.com/story")
    with patch(_ALGOLIA_PATCH, return_value=_mock_response([hit])):
        result = HNSource(_make_config()).fetch()
    assert result[0].url == "https://example.com/story"


def test_fetch_maps_title_correctly() -> None:
    hit = _make_hit(title="Amazing LLM Paper")
    with patch(_ALGOLIA_PATCH, return_value=_mock_response([hit])):
        result = HNSource(_make_config()).fetch()
    assert result[0].title == "Amazing LLM Paper"


def test_fetch_source_is_hackernews() -> None:
    with patch(_ALGOLIA_PATCH, return_value=_mock_response([_make_hit()])):
        result = HNSource(_make_config()).fetch()
    assert result[0].source == "hackernews"


def test_fetch_content_type_is_web() -> None:
    with patch(_ALGOLIA_PATCH, return_value=_mock_response([_make_hit()])):
        result = HNSource(_make_config()).fetch()
    assert result[0].content_type == "web"


def test_fetch_maps_published_at_from_unix_timestamp() -> None:
    # 1744012800 == 2025-04-07 08:00:00 UTC
    hit = _make_hit(created_at_i=1744012800)
    with patch(_ALGOLIA_PATCH, return_value=_mock_response([hit])):
        result = HNSource(_make_config()).fetch()
    expected = datetime.fromtimestamp(1744012800, tz=UTC)
    assert result[0].published_at == expected


def test_fetch_published_at_is_timezone_aware() -> None:
    with patch(_ALGOLIA_PATCH, return_value=_mock_response([_make_hit()])):
        result = HNSource(_make_config()).fetch()
    assert result[0].published_at.tzinfo is not None


def test_fetch_raw_content_from_story_text() -> None:
    hit = _make_hit(story_text="Ask HN: What do you think about LLMs?")
    with patch(_ALGOLIA_PATCH, return_value=_mock_response([hit])):
        result = HNSource(_make_config()).fetch()
    assert result[0].raw_content == "Ask HN: What do you think about LLMs?"


def test_fetch_raw_content_empty_when_story_text_is_null() -> None:
    hit = _make_hit(story_text=None)
    with patch(_ALGOLIA_PATCH, return_value=_mock_response([hit])):
        result = HNSource(_make_config()).fetch()
    assert result[0].raw_content == ""


def test_fetch_multiple_hits_all_returned() -> None:
    hit_count = 5
    hits = [_make_hit(object_id=str(i), url=f"https://example.com/{i}") for i in range(hit_count)]
    with patch(_ALGOLIA_PATCH, return_value=_mock_response(hits)):
        result = HNSource(_make_config()).fetch()
    assert len(result) == hit_count


# ---------------------------------------------------------------------------
# Happy path: edge cases
# ---------------------------------------------------------------------------


def test_fetch_empty_hits_returns_empty_list() -> None:
    with patch(_ALGOLIA_PATCH, return_value=_mock_response([])):
        result = HNSource(_make_config()).fetch()
    assert result == []


def test_fetch_disabled_returns_empty_without_http_call() -> None:
    config = _make_config(enabled=False)
    with patch(_ALGOLIA_PATCH) as mock_get:
        result = HNSource(config).fetch()
    assert result == []
    mock_get.assert_not_called()


def test_fetch_empty_keywords_calls_api_without_query_param() -> None:
    config = _make_config(keywords=[])
    with patch(_ALGOLIA_PATCH, return_value=_mock_response([_make_hit()])) as mock_get:
        HNSource(config).fetch()
    call_url: str = mock_get.call_args[0][0]
    assert "query" not in call_url


def test_fetch_with_keywords_includes_query_param() -> None:
    config = _make_config(keywords=["LLM", "transformer"])
    with patch(_ALGOLIA_PATCH, return_value=_mock_response([_make_hit()])) as mock_get:
        HNSource(config).fetch()
    call_url: str = mock_get.call_args[0][0]
    assert "query" in call_url


# ---------------------------------------------------------------------------
# Failure mode: HTTP error and timeout
# ---------------------------------------------------------------------------


def test_fetch_http_error_returns_empty_list() -> None:
    mock_resp = MagicMock()
    mock_resp.raise_for_status.side_effect = httpx.HTTPStatusError(
        "500", request=MagicMock(), response=MagicMock()
    )
    with patch(_ALGOLIA_PATCH, return_value=mock_resp):
        result = HNSource(_make_config()).fetch()
    assert result == []


def test_fetch_timeout_returns_empty_list() -> None:
    with patch(_ALGOLIA_PATCH, side_effect=httpx.TimeoutException("timeout")):
        result = HNSource(_make_config()).fetch()
    assert result == []


def test_fetch_connect_error_returns_empty_list() -> None:
    with patch(_ALGOLIA_PATCH, side_effect=httpx.ConnectError("connection refused")):
        result = HNSource(_make_config()).fetch()
    assert result == []


# ---------------------------------------------------------------------------
# Failure mode: missing fields in hit
# ---------------------------------------------------------------------------


def test_fetch_hit_missing_url_is_skipped() -> None:
    hit = _make_hit()
    del hit["url"]
    with patch(_ALGOLIA_PATCH, return_value=_mock_response([hit])):
        result = HNSource(_make_config()).fetch()
    assert result == []


def test_fetch_hit_missing_url_does_not_raise() -> None:
    hit = _make_hit()
    del hit["url"]
    with patch(_ALGOLIA_PATCH, return_value=_mock_response([hit])):
        HNSource(_make_config()).fetch()  # must not raise


def test_fetch_hit_missing_title_is_skipped() -> None:
    hit = _make_hit()
    del hit["title"]
    with patch(_ALGOLIA_PATCH, return_value=_mock_response([hit])):
        result = HNSource(_make_config()).fetch()
    assert result == []


def test_fetch_hit_missing_title_does_not_raise() -> None:
    hit = _make_hit()
    del hit["title"]
    with patch(_ALGOLIA_PATCH, return_value=_mock_response([hit])):
        HNSource(_make_config()).fetch()  # must not raise


def test_fetch_valid_hits_returned_when_some_missing_url() -> None:
    """Good hits after a bad one are still returned."""
    bad = _make_hit(object_id="1")
    del bad["url"]
    good = _make_hit(object_id="2", url="https://example.com/good")
    with patch(_ALGOLIA_PATCH, return_value=_mock_response([bad, good])):
        result = HNSource(_make_config()).fetch()
    assert len(result) == 1
    assert result[0].url == "https://example.com/good"


# ---------------------------------------------------------------------------
# Contract / interface tests
# ---------------------------------------------------------------------------


def test_hn_source_is_subclass_of_source() -> None:
    assert issubclass(HNSource, Source)


def test_hn_source_instance_is_source() -> None:
    assert isinstance(HNSource(_make_config()), Source)


def test_fetch_return_type_annotation() -> None:
    with patch(_ALGOLIA_PATCH, return_value=_mock_response([_make_hit()])):
        result = HNSource(_make_config()).fetch()
    assert isinstance(result, list)
