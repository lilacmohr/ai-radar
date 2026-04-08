"""Tests for radar/sources/rss.py — the RSS/Atom source connector.

All tests in this file are expected to FAIL (red) until radar/sources/rss.py
is implemented. See paired [IMPL] issue #32.

Spec reference: SPEC.md §3.1 (RSS/Atom connector), §3.2 step 1, §6.3 (60s timeout).

Design decision — missing entry title:
    Entries that are missing a 'title' key (or have an empty title) are SKIPPED
    and logged at WARNING. Rationale: title is part of the Pass 1 excerpt input;
    an untitled article cannot be meaningfully scored. Using an empty string
    would silently pass garbage into the LLM. Skipping is the conservative choice.
    This matches CLAUDE.md §5: "single source fetch fails → skip, continue pipeline".
"""

import time
import urllib.error
from datetime import UTC, datetime
from unittest.mock import patch

from radar.sources.rss import RSSSource

from radar.config import RssFeedEntryConfig, RssFeedsConfig
from radar.models import RawItem
from radar.sources.base import Source

# ---------------------------------------------------------------------------
# Shared constants
# ---------------------------------------------------------------------------

_HTTP_ERROR_THRESHOLD = 400
_MULTI_FEED_ITEM_COUNT = 2

_FEED_A_NAME = "Test Blog A"
_FEED_A_URL = "https://feeds.example.com/blog-a.xml"
_FEED_B_NAME = "Test Blog B"
_FEED_B_URL = "https://feeds.example.com/blog-b.xml"

# Realistic feedparser published_parsed struct and the expected datetime it maps to.
# feedparser returns time.struct_time in UTC; the implementation must convert to datetime.
_PUBLISHED_STRUCT = time.struct_time((2026, 4, 7, 9, 0, 0, 1, 97, -1))
_EXPECTED_PUBLISHED_AT = datetime(2026, 4, 7, 9, 0, 0, tzinfo=UTC)


# ---------------------------------------------------------------------------
# Fixture factories
# ---------------------------------------------------------------------------


def _make_config(
    *,
    enabled: bool = True,
    feeds: list[tuple[str, str]] | None = None,
) -> RssFeedsConfig:
    """Build an RssFeedsConfig. feeds is a list of (name, url) tuples."""
    if feeds is None:
        feeds = [(_FEED_A_NAME, _FEED_A_URL)]
    return RssFeedsConfig(
        enabled=enabled,
        feeds=[RssFeedEntryConfig(name=name, url=url) for name, url in feeds],
    )


def _make_feedparser_entry(
    *,
    title: str = "Sample Article Title",
    link: str = "https://example.com/article-1",
    summary: str = "First 200 words of the article content.",
    published_parsed: time.struct_time | None = None,
) -> dict:
    """Build a realistic feedparser entry dict."""
    entry: dict = {
        "link": link,
        "title": title,
        "summary": summary,
        "published_parsed": published_parsed or _PUBLISHED_STRUCT,
    }
    return entry


def _make_feedparser_result(entries: list[dict], *, status: int = 200) -> dict:
    """Build a realistic feedparser parse() return value."""
    return {
        "bozo": status >= _HTTP_ERROR_THRESHOLD,
        "status": status,
        "entries": entries,
        "feed": {"title": "Feed Title"},
    }


# ---------------------------------------------------------------------------
# Happy path tests
# ---------------------------------------------------------------------------


def test_fetch_returns_list_of_raw_items() -> None:
    """fetch() with a valid feed returns a non-empty list[RawItem]."""
    config = _make_config()
    result_dict = _make_feedparser_result([_make_feedparser_entry()])

    with patch("radar.sources.rss.feedparser.parse", return_value=result_dict):
        source = RSSSource(config)
        result = source.fetch()

    assert isinstance(result, list)
    assert len(result) == 1
    assert isinstance(result[0], RawItem)


def test_raw_items_have_web_content_type() -> None:
    """All RawItems produced by RSSSource have content_type='web'."""
    config = _make_config()
    entries = [_make_feedparser_entry(link=f"https://example.com/{i}") for i in range(3)]
    result_dict = _make_feedparser_result(entries)

    with patch("radar.sources.rss.feedparser.parse", return_value=result_dict):
        source = RSSSource(config)
        items = source.fetch()

    assert all(item.content_type == "web" for item in items)


def test_raw_item_fields_populated_from_feed_entry() -> None:
    """RawItem fields are correctly mapped from the feedparser entry."""
    config = _make_config(feeds=[(_FEED_A_NAME, _FEED_A_URL)])
    entry = _make_feedparser_entry(
        title="My Article",
        link="https://example.com/my-article",
        summary="Article summary text here.",
        published_parsed=_PUBLISHED_STRUCT,
    )
    result_dict = _make_feedparser_result([entry])

    with patch("radar.sources.rss.feedparser.parse", return_value=result_dict):
        source = RSSSource(config)
        items = source.fetch()

    assert len(items) == 1
    item = items[0]
    assert item.url == "https://example.com/my-article"
    assert item.title == "My Article"
    assert item.source == _FEED_A_NAME
    assert item.raw_content == "Article summary text here."
    assert item.published_at == _EXPECTED_PUBLISHED_AT


def test_multiple_feeds_aggregated_into_single_list() -> None:
    """Items from multiple configured feeds are combined into one flat list."""
    config = _make_config(feeds=[(_FEED_A_NAME, _FEED_A_URL), (_FEED_B_NAME, _FEED_B_URL)])
    entry_a = _make_feedparser_entry(link="https://example.com/from-a", title="From A")
    entry_b = _make_feedparser_entry(link="https://example.com/from-b", title="From B")

    def _side_effect(url: str, **_: object) -> dict:
        if url == _FEED_A_URL:
            return _make_feedparser_result([entry_a])
        return _make_feedparser_result([entry_b])

    with patch("radar.sources.rss.feedparser.parse", side_effect=_side_effect):
        source = RSSSource(config)
        items = source.fetch()

    urls = {item.url for item in items}
    assert "https://example.com/from-a" in urls
    assert "https://example.com/from-b" in urls
    assert len(items) == _MULTI_FEED_ITEM_COUNT


def test_empty_feed_returns_empty_list() -> None:
    """A feed with no entries returns [] without error."""
    config = _make_config()
    result_dict = _make_feedparser_result([])

    with patch("radar.sources.rss.feedparser.parse", return_value=result_dict):
        source = RSSSource(config)
        items = source.fetch()

    assert items == []


def test_disabled_connector_returns_empty_list_without_fetching() -> None:
    """When enabled=False, fetch() returns [] immediately and never calls feedparser."""
    config = _make_config(enabled=False)

    with patch("radar.sources.rss.feedparser.parse") as mock_parse:
        source = RSSSource(config)
        items = source.fetch()

    assert items == []
    mock_parse.assert_not_called()


# ---------------------------------------------------------------------------
# Failure mode tests
# ---------------------------------------------------------------------------


def test_feed_with_http_error_is_skipped_and_others_continue() -> None:
    """A feed that raises URLError is skipped; remaining feeds are still processed."""
    config = _make_config(feeds=[(_FEED_A_NAME, _FEED_A_URL), (_FEED_B_NAME, _FEED_B_URL)])
    entry_b = _make_feedparser_entry(link="https://example.com/from-b", title="From B")

    def _side_effect(url: str, **_: object) -> dict:
        if url == _FEED_A_URL:
            err = urllib.error.URLError("HTTP 404 Not Found")
            raise err
        return _make_feedparser_result([entry_b])

    with patch("radar.sources.rss.feedparser.parse", side_effect=_side_effect):
        source = RSSSource(config)
        items = source.fetch()

    # Feed A failed — only Feed B's item should be present
    assert len(items) == 1
    assert items[0].url == "https://example.com/from-b"


def test_entry_missing_title_is_skipped() -> None:
    """An entry without a 'title' key is skipped (logged, not raised).

    Design decision: skip rather than use empty string. An untitled article
    cannot be meaningfully scored in Pass 1 (title is part of the excerpt).
    See module docstring for full rationale.
    """
    config = _make_config()
    entry_no_title: dict = {
        "link": "https://example.com/no-title",
        "summary": "Some content without a title.",
        "published_parsed": _PUBLISHED_STRUCT,
        # 'title' key intentionally absent
    }
    entry_with_title = _make_feedparser_entry(link="https://example.com/has-title")
    result_dict = _make_feedparser_result([entry_no_title, entry_with_title])

    with patch("radar.sources.rss.feedparser.parse", return_value=result_dict):
        source = RSSSource(config)
        items = source.fetch()

    # Only the entry with a title should be returned
    assert len(items) == 1
    assert items[0].url == "https://example.com/has-title"


def test_feed_with_timeout_is_skipped_and_others_continue() -> None:
    """A feed that times out is skipped; remaining feeds are still processed."""
    config = _make_config(feeds=[(_FEED_A_NAME, _FEED_A_URL), (_FEED_B_NAME, _FEED_B_URL)])
    entry_b = _make_feedparser_entry(link="https://example.com/from-b", title="From B")

    def _side_effect(url: str, **_: object) -> dict:
        if url == _FEED_A_URL:
            err = TimeoutError("timed out")
            raise err
        return _make_feedparser_result([entry_b])

    with patch("radar.sources.rss.feedparser.parse", side_effect=_side_effect):
        source = RSSSource(config)
        items = source.fetch()

    assert len(items) == 1
    assert items[0].url == "https://example.com/from-b"


def test_all_feeds_fail_returns_empty_list() -> None:
    """When all feeds fail, fetch() returns [] rather than raising."""
    config = _make_config(feeds=[(_FEED_A_NAME, _FEED_A_URL), (_FEED_B_NAME, _FEED_B_URL)])

    conn_err = urllib.error.URLError("connection refused")
    with patch("radar.sources.rss.feedparser.parse", side_effect=conn_err):
        source = RSSSource(config)
        items = source.fetch()

    assert items == []


# ---------------------------------------------------------------------------
# Interface / contract tests
# ---------------------------------------------------------------------------


def test_rss_source_is_subclass_of_source() -> None:
    """RSSSource is a subclass of the Source ABC."""
    config = _make_config(enabled=False)
    source = RSSSource(config)
    assert isinstance(source, Source)


def test_fetch_returns_list_not_dict_or_any() -> None:
    """fetch() returns list[RawItem], not list[dict] or any other type."""
    config = _make_config()
    entry = _make_feedparser_entry()
    result_dict = _make_feedparser_result([entry])

    with patch("radar.sources.rss.feedparser.parse", return_value=result_dict):
        source = RSSSource(config)
        items = source.fetch()

    assert isinstance(items, list)
    for item in items:
        assert isinstance(item, RawItem), f"Expected RawItem, got {type(item)}"
        assert not isinstance(item, dict)


def test_published_at_is_datetime_not_string() -> None:
    """RawItem.published_at is a datetime object, not a raw feedparser string."""
    config = _make_config()
    entry = _make_feedparser_entry(published_parsed=_PUBLISHED_STRUCT)
    result_dict = _make_feedparser_result([entry])

    with patch("radar.sources.rss.feedparser.parse", return_value=result_dict):
        source = RSSSource(config)
        items = source.fetch()

    assert len(items) == 1
    assert isinstance(items[0].published_at, datetime)
    assert items[0].published_at.tzinfo is not None, "published_at must be timezone-aware"
