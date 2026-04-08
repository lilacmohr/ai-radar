"""Tests for radar/processing/deduplicator.py.

Two-phase deduplication:
  Phase 1 — dedup_by_url: RawItem list filtered by url_hash (computed from item.url)
  Phase 2 — dedup_by_content: ExcerptItem list filtered by content_hash (field on item)

Key contract: neither function calls cache.mark_seen() — items are only
marked seen by pipeline.py after successful digest generation.
"""

from datetime import UTC, datetime
from pathlib import Path

import pytest

from radar.cache import Cache
from radar.models import ExcerptItem, RawItem
from radar.processing.deduplicator import (
    dedup_by_content,
    dedup_by_url,
    url_to_hash,
)

# ---------------------------------------------------------------------------
# Fixtures and factories
# ---------------------------------------------------------------------------


@pytest.fixture
def cache(temp_cache_dir: Path) -> Cache:
    return Cache(temp_cache_dir / "radar.db")


def _make_raw_item(
    url: str = "https://example.com/article",
    title: str = "Test Article",
    raw_content: str = "Some raw content.",
) -> RawItem:
    return RawItem(
        url=url,
        title=title,
        source="test",
        published_at=datetime(2026, 4, 7, 9, 0, 0, tzinfo=UTC),
        raw_content=raw_content,
        content_type="web",
    )


def _make_excerpt_item(
    url: str = "https://example.com/article",
    title: str = "Test Article",
    url_hash: str = "urlhash_abc",
    content_hash: str = "contenthash_xyz",
    excerpt: str = "Some excerpt.",
) -> ExcerptItem:
    return ExcerptItem(
        url=url,
        title=title,
        source="test",
        published_at=datetime(2026, 4, 7, 9, 0, 0, tzinfo=UTC),
        excerpt=excerpt,
        url_hash=url_hash,
        content_hash=content_hash,
    )


# ---------------------------------------------------------------------------
# url_to_hash — normalization helper
# ---------------------------------------------------------------------------


def test_url_to_hash_returns_string() -> None:
    result = url_to_hash("https://example.com/article")
    assert isinstance(result, str)
    assert len(result) > 0


def test_url_to_hash_strips_utm_params() -> None:
    clean = url_to_hash("https://example.com/article")
    with_utm = url_to_hash("https://example.com/article?utm_source=newsletter&utm_medium=email")
    assert clean == with_utm


def test_url_to_hash_preserves_non_utm_params() -> None:
    with_param = url_to_hash("https://example.com/article?page=2")
    without_param = url_to_hash("https://example.com/article")
    assert with_param != without_param


def test_url_to_hash_same_url_same_hash() -> None:
    url = "https://example.com/article"
    assert url_to_hash(url) == url_to_hash(url)


def test_url_to_hash_different_urls_different_hashes() -> None:
    assert url_to_hash("https://example.com/a") != url_to_hash("https://example.com/b")


# ---------------------------------------------------------------------------
# Phase 1 — dedup_by_url: happy path
# ---------------------------------------------------------------------------


def test_dedup_by_url_unseen_items_pass_through(cache: Cache) -> None:
    item = _make_raw_item(url="https://example.com/new")
    result = dedup_by_url([item], cache)
    assert result == [item]


def test_dedup_by_url_seen_item_is_filtered(cache: Cache) -> None:
    url = "https://example.com/old"
    cache.mark_seen(url_hash=url_to_hash(url), content_hash="ch_placeholder")
    item = _make_raw_item(url=url)
    result = dedup_by_url([item], cache)
    assert result == []


def test_dedup_by_url_mixed_returns_only_unseen(cache: Cache) -> None:
    seen_url = "https://example.com/old"
    unseen_url = "https://example.com/new"
    cache.mark_seen(url_hash=url_to_hash(seen_url), content_hash="ch1")
    seen = _make_raw_item(url=seen_url)
    unseen = _make_raw_item(url=unseen_url)
    result = dedup_by_url([seen, unseen], cache)
    assert result == [unseen]


def test_dedup_by_url_order_preserved(cache: Cache) -> None:
    items = [_make_raw_item(url=f"https://example.com/{i}") for i in range(5)]
    result = dedup_by_url(items, cache)
    assert [r.url for r in result] == [item.url for item in items]


def test_dedup_by_url_empty_input(cache: Cache) -> None:
    assert dedup_by_url([], cache) == []


# ---------------------------------------------------------------------------
# Phase 1 — URL normalization: utm_* tracking params
# ---------------------------------------------------------------------------


def test_dedup_by_url_utm_params_treated_as_duplicate(cache: Cache) -> None:
    """Two items with same URL differing only by utm_* params share a url_hash."""
    base_url = "https://example.com/article"
    utm_url = "https://example.com/article?utm_source=newsletter&utm_medium=email"
    item1 = _make_raw_item(url=base_url)
    item2 = _make_raw_item(url=utm_url)
    # item2 should be filtered: same normalized URL → same hash → duplicate of item1
    result = dedup_by_url([item1, item2], cache)
    assert len(result) == 1
    assert result[0] is item1


# ---------------------------------------------------------------------------
# Phase 1 — cache-empty baseline and edge cases
# ---------------------------------------------------------------------------


def test_dedup_by_url_empty_cache_all_pass(cache: Cache) -> None:
    items = [_make_raw_item(url=f"https://example.com/{i}") for i in range(3)]
    assert dedup_by_url(items, cache) == items


def test_dedup_by_url_all_seen_returns_empty(cache: Cache) -> None:
    items = [_make_raw_item(url=f"https://example.com/{i}") for i in range(3)]
    for item in items:
        cache.mark_seen(url_hash=url_to_hash(item.url), content_hash=f"ch_{item.url}")
    assert dedup_by_url(items, cache) == []


def test_dedup_by_url_single_seen_item_returns_empty(cache: Cache) -> None:
    url = "https://example.com/only"
    cache.mark_seen(url_hash=url_to_hash(url), content_hash="ch1")
    assert dedup_by_url([_make_raw_item(url=url)], cache) == []


# ---------------------------------------------------------------------------
# Phase 1 — contract
# ---------------------------------------------------------------------------


def test_dedup_by_url_returns_original_objects(cache: Cache) -> None:
    item = _make_raw_item(url="https://example.com/fresh")
    result = dedup_by_url([item], cache)
    assert result[0] is item


def test_dedup_by_url_return_type_is_list_of_raw_items(cache: Cache) -> None:
    item = _make_raw_item(url="https://example.com/fresh")
    result = dedup_by_url([item], cache)
    assert isinstance(result, list)
    assert all(isinstance(x, RawItem) for x in result)


def test_dedup_by_url_does_not_call_mark_seen(cache: Cache) -> None:
    item = _make_raw_item(url="https://example.com/fresh")
    dedup_by_url([item], cache)
    # Cache must remain empty — dedup_by_url must not call mark_seen
    assert not cache.is_seen(url_hash=url_to_hash(item.url))


# ---------------------------------------------------------------------------
# Phase 2 — dedup_by_content: happy path
# ---------------------------------------------------------------------------


def test_dedup_by_content_unseen_items_pass_through(cache: Cache) -> None:
    item = _make_excerpt_item(content_hash="new_content_hash")
    result = dedup_by_content([item], cache)
    assert result == [item]


def test_dedup_by_content_seen_item_is_filtered(cache: Cache) -> None:
    cache.mark_seen(url_hash="uh1", content_hash="seen_content_hash")
    item = _make_excerpt_item(content_hash="seen_content_hash")
    result = dedup_by_content([item], cache)
    assert result == []


def test_dedup_by_content_mixed_returns_only_unseen(cache: Cache) -> None:
    cache.mark_seen(url_hash="uh1", content_hash="seen_ch")
    seen = _make_excerpt_item(url="https://a.com/1", content_hash="seen_ch")
    unseen = _make_excerpt_item(url="https://a.com/2", content_hash="new_ch")
    result = dedup_by_content([seen, unseen], cache)
    assert result == [unseen]


def test_dedup_by_content_same_content_different_urls_deduped(cache: Cache) -> None:
    """Same article at two URLs: second is filtered once first makes hash seen."""
    shared_hash = "same_article_hash"
    item1 = _make_excerpt_item(
        url="https://mirror1.com/article", url_hash="uh_1", content_hash=shared_hash
    )
    item2 = _make_excerpt_item(
        url="https://mirror2.com/article", url_hash="uh_2", content_hash=shared_hash
    )
    result = dedup_by_content([item1, item2], cache)
    assert len(result) == 1
    assert result[0] is item1


def test_dedup_by_content_empty_input(cache: Cache) -> None:
    assert dedup_by_content([], cache) == []


def test_dedup_by_content_order_preserved(cache: Cache) -> None:
    items = [
        _make_excerpt_item(
            url=f"https://example.com/{i}", url_hash=f"uh_{i}", content_hash=f"ch_{i}"
        )
        for i in range(5)
    ]
    result = dedup_by_content(items, cache)
    assert [r.url for r in result] == [item.url for item in items]


# ---------------------------------------------------------------------------
# Phase 2 — cache-empty baseline and edge cases
# ---------------------------------------------------------------------------


def test_dedup_by_content_empty_cache_all_pass(cache: Cache) -> None:
    items = [
        _make_excerpt_item(
            url=f"https://example.com/{i}", url_hash=f"uh_{i}", content_hash=f"ch_{i}"
        )
        for i in range(3)
    ]
    assert dedup_by_content(items, cache) == items


def test_dedup_by_content_all_seen_returns_empty(cache: Cache) -> None:
    for i in range(3):
        cache.mark_seen(url_hash=f"uh_{i}", content_hash=f"ch_{i}")
    items = [
        _make_excerpt_item(
            url=f"https://example.com/{i}", url_hash=f"uh_{i}", content_hash=f"ch_{i}"
        )
        for i in range(3)
    ]
    assert dedup_by_content(items, cache) == []


def test_dedup_by_content_single_seen_item_returns_empty(cache: Cache) -> None:
    cache.mark_seen(url_hash="uh1", content_hash="only_ch")
    item = _make_excerpt_item(content_hash="only_ch")
    assert dedup_by_content([item], cache) == []


# ---------------------------------------------------------------------------
# Phase 2 — contract
# ---------------------------------------------------------------------------


def test_dedup_by_content_returns_original_objects(cache: Cache) -> None:
    item = _make_excerpt_item(content_hash="fresh_ch")
    result = dedup_by_content([item], cache)
    assert result[0] is item


def test_dedup_by_content_return_type_is_list_of_excerpt_items(cache: Cache) -> None:
    item = _make_excerpt_item(content_hash="fresh_ch")
    result = dedup_by_content([item], cache)
    assert isinstance(result, list)
    assert all(isinstance(x, ExcerptItem) for x in result)


def test_dedup_by_content_does_not_call_mark_seen(cache: Cache) -> None:
    item = _make_excerpt_item(url_hash="uh1", content_hash="fresh_ch")
    dedup_by_content([item], cache)
    # Cache must remain empty — dedup_by_content must not call mark_seen
    assert not cache.is_seen(content_hash="fresh_ch")
