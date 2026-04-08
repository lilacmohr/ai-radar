"""Tests for radar/sources/base.py — the Source abstract base class.

All tests in this file are expected to FAIL (red) until radar/sources/base.py
is implemented. See paired [IMPL] issue #30.

Spec reference: SPEC.md §3.1 (Source interface).
"""

from abc import ABCMeta
from datetime import UTC, datetime

import pytest
from radar.sources.base import Source

from radar.models import RawItem

# ---------------------------------------------------------------------------
# Shared test values
# ---------------------------------------------------------------------------

PUBLISHED_AT = datetime(2026, 4, 7, 9, 0, 0, tzinfo=UTC)
_ANOTHER_SOURCE_ITEM_COUNT = 2


def _make_raw_item() -> RawItem:
    return RawItem(
        url="https://example.com/article",
        title="Sample Article",
        source="test-source",
        published_at=PUBLISHED_AT,
        raw_content="Sample content.",
        content_type="web",
    )


# ---------------------------------------------------------------------------
# Concrete subclass helpers — defined at module level to avoid redefining
# in each test (and to make isinstance checks reliable)
# ---------------------------------------------------------------------------


class _ValidSource(Source):
    """Minimal concrete Source that returns a non-empty list."""

    def fetch(self) -> list[RawItem]:
        return [_make_raw_item()]


class _EmptySource(Source):
    """Minimal concrete Source that returns an empty list."""

    def fetch(self) -> list[RawItem]:
        return []


class _AnotherSource(Source):
    """Second concrete Source to verify multiple subclasses can coexist."""

    def fetch(self) -> list[RawItem]:
        return [_make_raw_item(), _make_raw_item()]


# ---------------------------------------------------------------------------
# Happy path tests
# ---------------------------------------------------------------------------


def test_concrete_source_can_be_instantiated() -> None:
    """A subclass that implements fetch() can be instantiated without error."""
    source = _ValidSource()
    assert source is not None


def test_fetch_returns_list_of_raw_items() -> None:
    """fetch() returns list[RawItem]."""
    source = _ValidSource()
    result = source.fetch()
    assert isinstance(result, list)
    assert all(isinstance(item, RawItem) for item in result)


def test_empty_list_is_valid_return_value() -> None:
    """fetch() returning [] is a valid result — no articles found is not an error."""
    source = _EmptySource()
    result = source.fetch()
    assert result == []


def test_multiple_source_subclasses_can_coexist_independently() -> None:
    """Multiple Source subclasses can be instantiated and called independently."""
    source_a = _EmptySource()
    source_b = _AnotherSource()
    assert source_a.fetch() == []
    assert len(source_b.fetch()) == _ANOTHER_SOURCE_ITEM_COUNT


# ---------------------------------------------------------------------------
# Failure mode tests
# ---------------------------------------------------------------------------


def test_subclass_without_fetch_raises_type_error() -> None:
    """A subclass that does NOT implement fetch() raises TypeError at instantiation."""

    class _IncompleteSource(Source):
        pass  # fetch() not implemented

    with pytest.raises(TypeError):
        _IncompleteSource()  # type: ignore[abstract]


def test_direct_source_instantiation_raises_type_error() -> None:
    """Instantiating Source directly (not via subclass) raises TypeError."""
    with pytest.raises(TypeError):
        Source()  # type: ignore[abstract]


# ---------------------------------------------------------------------------
# Interface / contract tests
# ---------------------------------------------------------------------------


def test_source_uses_abc_meta() -> None:
    """Source is defined using ABCMeta, not a plain class."""
    assert isinstance(Source, ABCMeta)


def test_valid_subclass_is_instance_of_source() -> None:
    """A correctly implemented subclass passes isinstance(instance, Source)."""
    source = _ValidSource()
    assert isinstance(source, Source)


def test_fetch_return_type_annotation_is_list_of_raw_item() -> None:
    """fetch() carries a return type annotation of list[RawItem]."""
    hints = Source.fetch.__annotations__
    assert "return" in hints, "fetch() must have a return type annotation"
    annotation = hints["return"]
    # Accept both stringified and evaluated forms, and generic alias forms
    annotation_str = str(annotation)
    assert "RawItem" in annotation_str, (
        f"fetch() return type must reference RawItem, got: {annotation_str}"
    )


def test_fetch_is_abstract() -> None:
    """fetch() is declared as an abstract method on Source."""
    assert getattr(Source.fetch, "__isabstractmethod__", False), (
        "fetch() must be decorated with @abstractmethod"
    )


def test_source_abstract_methods_set_contains_fetch() -> None:
    """Source.__abstractmethods__ lists fetch as required."""
    assert "fetch" in Source.__abstractmethods__
