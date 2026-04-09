"""Tests for radar/sources/arxiv.py.

Verifies the ArXiv source connector:
- Happy path: valid Atom response maps to list[RawItem] with content_type="arxiv"
- Field mapping: url, title, source="arxiv", published_at (tz-aware), raw_content from summary
- Guard clauses: disabled connector, empty categories → return [] without API call
- Multiple categories → joined in query string (cat:X+OR+cat:Y)
- Failure modes: URLError, timeout → log WARNING, return []
- Missing fields: no link → skip entry; no title → skip entry; no summary → raw_content=""
- Contract: isinstance(Source), return type list[RawItem], content_type="arxiv"
"""

# 1. Standard library imports
import time
import urllib.error
from datetime import UTC
from unittest.mock import patch

# 2. Internal imports
from radar.config import ArxivConfig
from radar.models import RawItem
from radar.sources.arxiv import ArxivSource
from radar.sources.base import Source

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_FEEDPARSER_PATCH = "radar.sources.arxiv.feedparser.parse"

# ---------------------------------------------------------------------------
# Factories
# ---------------------------------------------------------------------------

_DEFAULT_PUBLISHED = time.strptime("2026-01-15 12:00:00", "%Y-%m-%d %H:%M:%S")


def _make_entry(
    link: str = "https://arxiv.org/abs/2501.12345",
    title: str = "Attention Is All You Need",
    summary: str = "We propose a new simple network architecture...",
    published_parsed: time.struct_time | None = _DEFAULT_PUBLISHED,
) -> dict[str, object]:
    entry: dict[str, object] = {
        "title": title,
        "summary": summary,
    }
    if link is not None:
        entry["link"] = link
    if published_parsed is not None:
        entry["published_parsed"] = published_parsed
    return entry


def _make_config(
    *,
    enabled: bool = True,
    categories: list[str] | None = None,
) -> ArxivConfig:
    return ArxivConfig(
        enabled=enabled,
        categories=categories if categories is not None else ["cs.AI"],
    )


def _make_feedparser_result(entries: list[dict[str, object]]) -> dict[str, object]:
    return {"entries": entries}


# ---------------------------------------------------------------------------
# Happy path: field mapping
# ---------------------------------------------------------------------------


def test_fetch_returns_list_of_raw_items() -> None:
    config = _make_config()
    mock_result = _make_feedparser_result([_make_entry()])
    with patch(_FEEDPARSER_PATCH, return_value=mock_result):
        result = ArxivSource(config).fetch()
    assert isinstance(result, list)
    assert len(result) == 1
    assert isinstance(result[0], RawItem)


def test_content_type_is_arxiv() -> None:
    config = _make_config()
    mock_result = _make_feedparser_result([_make_entry()])
    with patch(_FEEDPARSER_PATCH, return_value=mock_result):
        result = ArxivSource(config).fetch()
    assert result[0].content_type == "arxiv"


def test_url_populated_from_entry_link() -> None:
    url = "https://arxiv.org/abs/2501.99999"
    config = _make_config()
    mock_result = _make_feedparser_result([_make_entry(link=url)])
    with patch(_FEEDPARSER_PATCH, return_value=mock_result):
        result = ArxivSource(config).fetch()
    assert result[0].url == url


def test_title_populated_from_entry_title() -> None:
    title = "A Groundbreaking Paper"
    config = _make_config()
    mock_result = _make_feedparser_result([_make_entry(title=title)])
    with patch(_FEEDPARSER_PATCH, return_value=mock_result):
        result = ArxivSource(config).fetch()
    assert result[0].title == title


def test_source_is_arxiv_string() -> None:
    config = _make_config()
    mock_result = _make_feedparser_result([_make_entry()])
    with patch(_FEEDPARSER_PATCH, return_value=mock_result):
        result = ArxivSource(config).fetch()
    assert result[0].source == "arxiv"


def test_raw_content_populated_from_summary() -> None:
    abstract = "This paper proposes a novel approach to solving problems."
    config = _make_config()
    mock_result = _make_feedparser_result([_make_entry(summary=abstract)])
    with patch(_FEEDPARSER_PATCH, return_value=mock_result):
        result = ArxivSource(config).fetch()
    assert result[0].raw_content == abstract


def test_published_at_is_timezone_aware() -> None:
    config = _make_config()
    mock_result = _make_feedparser_result([_make_entry()])
    with patch(_FEEDPARSER_PATCH, return_value=mock_result):
        result = ArxivSource(config).fetch()
    assert result[0].published_at.tzinfo is not None


def test_published_at_is_utc() -> None:
    config = _make_config()
    mock_result = _make_feedparser_result([_make_entry()])
    with patch(_FEEDPARSER_PATCH, return_value=mock_result):
        result = ArxivSource(config).fetch()
    assert result[0].published_at.tzinfo == UTC


def test_published_at_matches_struct_time() -> None:
    expected_year = 2026
    expected_month = 3
    expected_day = 1
    published = time.strptime("2026-03-01 08:30:00", "%Y-%m-%d %H:%M:%S")
    config = _make_config()
    mock_result = _make_feedparser_result([_make_entry(published_parsed=published)])
    with patch(_FEEDPARSER_PATCH, return_value=mock_result):
        result = ArxivSource(config).fetch()
    assert result[0].published_at.year == expected_year
    assert result[0].published_at.month == expected_month
    assert result[0].published_at.day == expected_day


# ---------------------------------------------------------------------------
# Happy path: guard clauses and multiple items
# ---------------------------------------------------------------------------


def test_disabled_connector_returns_empty_list() -> None:
    config = _make_config(enabled=False)
    with patch(_FEEDPARSER_PATCH) as mock_parse:
        result = ArxivSource(config).fetch()
    assert result == []
    mock_parse.assert_not_called()


def test_empty_categories_returns_empty_list() -> None:
    config = _make_config(categories=[])
    with patch(_FEEDPARSER_PATCH) as mock_parse:
        result = ArxivSource(config).fetch()
    assert result == []
    mock_parse.assert_not_called()


def test_empty_entries_returns_empty_list() -> None:
    config = _make_config()
    mock_result = _make_feedparser_result([])
    with patch(_FEEDPARSER_PATCH, return_value=mock_result):
        result = ArxivSource(config).fetch()
    assert result == []


def test_multiple_entries_all_returned() -> None:
    entry_count = 4
    entries = [_make_entry(link=f"https://arxiv.org/abs/2501.{i:05d}") for i in range(entry_count)]
    config = _make_config()
    mock_result = _make_feedparser_result(entries)
    with patch(_FEEDPARSER_PATCH, return_value=mock_result):
        result = ArxivSource(config).fetch()
    assert len(result) == entry_count


def test_order_of_entries_preserved() -> None:
    urls = [f"https://arxiv.org/abs/2501.{i:05d}" for i in range(3)]
    entries = [_make_entry(link=url) for url in urls]
    config = _make_config()
    mock_result = _make_feedparser_result(entries)
    with patch(_FEEDPARSER_PATCH, return_value=mock_result):
        result = ArxivSource(config).fetch()
    assert [r.url for r in result] == urls


# ---------------------------------------------------------------------------
# Happy path: multiple categories → query string
# ---------------------------------------------------------------------------


def test_multiple_categories_included_in_query() -> None:
    config = _make_config(categories=["cs.AI", "cs.LG", "stat.ML"])
    captured_url: list[str] = []

    def capture(url: str, **_kwargs: object) -> dict[str, object]:
        captured_url.append(url)
        return _make_feedparser_result([])

    with patch(_FEEDPARSER_PATCH, side_effect=capture):
        ArxivSource(config).fetch()

    assert len(captured_url) == 1
    assert "cs.AI" in captured_url[0]
    assert "cs.LG" in captured_url[0]
    assert "stat.ML" in captured_url[0]


def test_single_category_no_or_needed() -> None:
    config = _make_config(categories=["cs.AI"])
    captured_url: list[str] = []

    def capture(url: str, **_kwargs: object) -> dict[str, object]:
        captured_url.append(url)
        return _make_feedparser_result([])

    with patch(_FEEDPARSER_PATCH, side_effect=capture):
        ArxivSource(config).fetch()

    assert "cs.AI" in captured_url[0]


# ---------------------------------------------------------------------------
# Failure modes
# ---------------------------------------------------------------------------


def test_url_error_returns_empty_list() -> None:
    config = _make_config()
    with patch(_FEEDPARSER_PATCH, side_effect=urllib.error.URLError("connection refused")):
        result = ArxivSource(config).fetch()
    assert result == []


def test_url_error_does_not_raise() -> None:
    config = _make_config()
    with patch(_FEEDPARSER_PATCH, side_effect=urllib.error.URLError("dns failure")):
        ArxivSource(config).fetch()  # must not raise


def test_timeout_error_returns_empty_list() -> None:
    config = _make_config()
    with patch(_FEEDPARSER_PATCH, side_effect=TimeoutError("timed out")):
        result = ArxivSource(config).fetch()
    assert result == []


def test_timeout_error_does_not_raise() -> None:
    config = _make_config()
    with patch(_FEEDPARSER_PATCH, side_effect=TimeoutError("timed out")):
        ArxivSource(config).fetch()  # must not raise


# ---------------------------------------------------------------------------
# Missing fields
# ---------------------------------------------------------------------------


def test_entry_missing_link_is_skipped() -> None:
    entry: dict[str, object] = {
        "title": "Some Paper",
        "summary": "Some abstract.",
        "published_parsed": _DEFAULT_PUBLISHED,
    }
    config = _make_config()
    mock_result = _make_feedparser_result([entry])
    with patch(_FEEDPARSER_PATCH, return_value=mock_result):
        result = ArxivSource(config).fetch()
    assert result == []


def test_entry_missing_title_is_skipped() -> None:
    entry: dict[str, object] = {
        "link": "https://arxiv.org/abs/2501.12345",
        "summary": "Some abstract.",
        "published_parsed": _DEFAULT_PUBLISHED,
    }
    config = _make_config()
    mock_result = _make_feedparser_result([entry])
    with patch(_FEEDPARSER_PATCH, return_value=mock_result):
        result = ArxivSource(config).fetch()
    assert result == []


def test_entry_missing_summary_uses_empty_string() -> None:
    entry: dict[str, object] = {
        "link": "https://arxiv.org/abs/2501.12345",
        "title": "A Paper Without Abstract",
        "published_parsed": _DEFAULT_PUBLISHED,
    }
    config = _make_config()
    mock_result = _make_feedparser_result([entry])
    with patch(_FEEDPARSER_PATCH, return_value=mock_result):
        result = ArxivSource(config).fetch()
    assert len(result) == 1
    assert result[0].raw_content == ""


def test_entry_missing_link_does_not_affect_other_entries() -> None:
    bad_entry: dict[str, object] = {
        "title": "No Link Paper",
        "summary": "Abstract.",
        "published_parsed": _DEFAULT_PUBLISHED,
    }
    good_entry = _make_entry(link="https://arxiv.org/abs/2501.99999")
    config = _make_config()
    mock_result = _make_feedparser_result([bad_entry, good_entry])
    with patch(_FEEDPARSER_PATCH, return_value=mock_result):
        result = ArxivSource(config).fetch()
    assert len(result) == 1
    assert result[0].url == "https://arxiv.org/abs/2501.99999"


def test_entry_missing_published_parsed_falls_back_to_now() -> None:
    entry: dict[str, object] = {
        "link": "https://arxiv.org/abs/2501.12345",
        "title": "No Date Paper",
        "summary": "Abstract without date.",
    }
    config = _make_config()
    mock_result = _make_feedparser_result([entry])
    with patch(_FEEDPARSER_PATCH, return_value=mock_result):
        result = ArxivSource(config).fetch()
    assert len(result) == 1
    assert result[0].published_at.tzinfo is not None


# ---------------------------------------------------------------------------
# Contract / return type
# ---------------------------------------------------------------------------


def test_arxiv_source_is_instance_of_source() -> None:
    config = _make_config()
    assert isinstance(ArxivSource(config), Source)


def test_fetch_return_type_is_list() -> None:
    config = _make_config(enabled=False)
    result = ArxivSource(config).fetch()
    assert isinstance(result, list)


def test_all_returned_items_are_raw_items() -> None:
    entries = [_make_entry(link=f"https://arxiv.org/abs/2501.{i:05d}") for i in range(3)]
    config = _make_config()
    mock_result = _make_feedparser_result(entries)
    with patch(_FEEDPARSER_PATCH, return_value=mock_result):
        result = ArxivSource(config).fetch()
    assert all(isinstance(item, RawItem) for item in result)


def test_all_returned_items_have_arxiv_content_type() -> None:
    entries = [_make_entry(link=f"https://arxiv.org/abs/2501.{i:05d}") for i in range(3)]
    config = _make_config()
    mock_result = _make_feedparser_result(entries)
    with patch(_FEEDPARSER_PATCH, return_value=mock_result):
        result = ArxivSource(config).fetch()
    assert all(item.content_type == "arxiv" for item in result)
