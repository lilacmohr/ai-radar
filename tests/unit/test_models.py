"""Tests for radar/models.py — pipeline dataclass definitions.

All tests in this file are expected to FAIL (red) until radar/models.py
is implemented. See paired [IMPL] issue #17.

Spec reference: SPEC.md §3.1 (data models), §4.2 (data flow / stage types).
"""

from datetime import UTC, date, datetime

import pytest

from radar.models import (
    Digest,
    ExcerptItem,
    FullItem,
    NormalizedItem,
    RawItem,
    ScoredItem,
)

# ---------------------------------------------------------------------------
# Shared test values — defined once to avoid magic literals in assertions
# ---------------------------------------------------------------------------

PUBLISHED_AT = datetime(2026, 4, 7, 9, 0, 0, tzinfo=UTC)
DIGEST_DATE = date(2026, 4, 7)
EXPECTED_SCORE = 8
EXPECTED_WORD_COUNT = 500
EXPECTED_MIN_SCORE = 1
EXPECTED_MAX_SCORE = 10


# ---------------------------------------------------------------------------
# RawItem
# ---------------------------------------------------------------------------


def test_raw_item_can_be_instantiated() -> None:
    item = RawItem(
        url="https://example.com/article",
        title="Test Article",
        source="rss",
        published_at=PUBLISHED_AT,
        raw_content="<p>Some raw HTML content</p>",
        content_type="web",
    )
    assert item.url == "https://example.com/article"
    assert item.title == "Test Article"
    assert item.source == "rss"
    assert item.published_at == PUBLISHED_AT
    assert item.raw_content == "<p>Some raw HTML content</p>"
    assert item.content_type == "web"


def test_raw_item_published_at_is_datetime() -> None:
    item = RawItem(
        url="https://example.com/article",
        title="Test Article",
        source="rss",
        published_at=PUBLISHED_AT,
        raw_content="content",
        content_type="web",
    )
    assert isinstance(item.published_at, datetime)


def test_raw_item_equality_with_identical_fields() -> None:
    kwargs = {
        "url": "https://example.com/article",
        "title": "Test Article",
        "source": "rss",
        "published_at": PUBLISHED_AT,
        "raw_content": "content",
        "content_type": "web",
    }
    assert RawItem(**kwargs) == RawItem(**kwargs)


# ---------------------------------------------------------------------------
# NormalizedItem
# ---------------------------------------------------------------------------


def test_normalized_item_can_be_instantiated() -> None:
    item = NormalizedItem(
        url="https://example.com/article",
        title="Test Article",
        source="rss",
        published_at=PUBLISHED_AT,
        clean_text="Some clean text content here",
        word_count=5,
        url_hash="abc123",
        content_hash="def456",
    )
    assert item.url == "https://example.com/article"
    assert item.clean_text == "Some clean text content here"
    assert item.url_hash == "abc123"
    assert item.content_hash == "def456"


def test_normalized_item_word_count_is_int() -> None:
    item = NormalizedItem(
        url="https://example.com/article",
        title="Title",
        source="rss",
        published_at=PUBLISHED_AT,
        clean_text="clean",
        word_count=1,
        url_hash="abc",
        content_hash="def",
    )
    assert isinstance(item.word_count, int)


# ---------------------------------------------------------------------------
# ExcerptItem
# ---------------------------------------------------------------------------


def test_excerpt_item_can_be_instantiated() -> None:
    item = ExcerptItem(
        url="https://example.com/article",
        title="Test Article",
        source="hackernews",
        published_at=PUBLISHED_AT,
        excerpt="This is the first ~200 words of the article.",
        url_hash="abc123",
        content_hash="def456",
    )
    assert item.url == "https://example.com/article"
    assert item.excerpt == "This is the first ~200 words of the article."
    assert item.url_hash == "abc123"
    assert item.content_hash == "def456"


def test_excerpt_item_fields_accessible_by_name() -> None:
    item = ExcerptItem(
        url="https://example.com",
        title="Title",
        source="arxiv",
        published_at=PUBLISHED_AT,
        excerpt="Excerpt text",
        url_hash="u1",
        content_hash="c1",
    )
    # Field access by name — not index
    assert item.source == "arxiv"
    assert item.title == "Title"


# ---------------------------------------------------------------------------
# ScoredItem
# ---------------------------------------------------------------------------


def test_scored_item_can_be_instantiated() -> None:
    item = ScoredItem(
        url="https://example.com/article",
        title="Test Article",
        source="arxiv",
        published_at=PUBLISHED_AT,
        excerpt="Article excerpt text",
        score=EXPECTED_SCORE,
        summary="This article covers LLM inference optimizations.",
    )
    assert item.url == "https://example.com/article"
    assert item.score == EXPECTED_SCORE
    assert item.summary == "This article covers LLM inference optimizations."


def test_scored_item_score_is_int() -> None:
    item = ScoredItem(
        url="https://example.com",
        title="Title",
        source="rss",
        published_at=PUBLISHED_AT,
        excerpt="Excerpt",
        score=EXPECTED_SCORE,
        summary="Summary",
    )
    assert isinstance(item.score, int)


def test_scored_item_equality_with_identical_fields() -> None:
    kwargs = {
        "url": "https://example.com",
        "title": "Title",
        "source": "rss",
        "published_at": PUBLISHED_AT,
        "excerpt": "Excerpt",
        "score": EXPECTED_SCORE,
        "summary": "Summary",
    }
    assert ScoredItem(**kwargs) == ScoredItem(**kwargs)


# ---------------------------------------------------------------------------
# FullItem
# ---------------------------------------------------------------------------


def test_full_item_can_be_instantiated() -> None:
    item = FullItem(
        url="https://example.com/article",
        title="Test Article",
        source="rss",
        published_at=PUBLISHED_AT,
        full_text="Full article text spanning many words.",
        word_count=EXPECTED_WORD_COUNT,
        score=EXPECTED_SCORE,
        summary="Summary from Pass 1.",
    )
    assert item.url == "https://example.com/article"
    assert item.full_text == "Full article text spanning many words."
    assert item.word_count == EXPECTED_WORD_COUNT
    assert item.score == EXPECTED_SCORE


def test_full_item_word_count_is_int() -> None:
    item = FullItem(
        url="https://example.com",
        title="Title",
        source="rss",
        published_at=PUBLISHED_AT,
        full_text="Full text",
        word_count=EXPECTED_WORD_COUNT,
        score=EXPECTED_SCORE,
        summary="Summary",
    )
    assert isinstance(item.word_count, int)


def test_full_item_score_is_int() -> None:
    item = FullItem(
        url="https://example.com",
        title="Title",
        source="rss",
        published_at=PUBLISHED_AT,
        full_text="Full text",
        word_count=EXPECTED_WORD_COUNT,
        score=EXPECTED_SCORE,
        summary="Summary",
    )
    assert isinstance(item.score, int)


# ---------------------------------------------------------------------------
# Digest
# ---------------------------------------------------------------------------


def test_digest_can_be_instantiated() -> None:
    article = ScoredItem(
        url="https://example.com/article",
        title="Test Article",
        source="rss",
        published_at=PUBLISHED_AT,
        excerpt="Excerpt",
        score=EXPECTED_SCORE,
        summary="Summary text.",
    )
    digest = Digest(
        date=DIGEST_DATE,
        articles=[article],
        executive_summary="Today's top AI stories.",
        contrarian_insights="Some contrarian take.",
        follow_up_questions="What are the implications?",
        trending_themes="LLM inference is trending.",
        source_stats={"rss": 5, "hackernews": 3},
    )
    assert digest.date == DIGEST_DATE
    assert len(digest.articles) == 1
    assert digest.executive_summary == "Today's top AI stories."


def test_digest_accepts_empty_articles_list() -> None:
    """Zero-article digest is valid per SPEC.md §3.7 (pipeline exit code 0)."""
    digest = Digest(
        date=DIGEST_DATE,
        articles=[],
        executive_summary="No notable content today.",
        contrarian_insights="",
        follow_up_questions="",
        trending_themes="",
        source_stats={},
    )
    assert digest.articles == []


def test_digest_date_is_date_not_datetime() -> None:
    digest = Digest(
        date=DIGEST_DATE,
        articles=[],
        executive_summary="",
        contrarian_insights="",
        follow_up_questions="",
        trending_themes="",
        source_stats={},
    )
    assert isinstance(digest.date, date)
    assert not isinstance(digest.date, datetime)


def test_digest_articles_holds_scored_item_instances() -> None:
    """Digest.articles must contain ScoredItem instances, not dicts."""
    scored = ScoredItem(
        url="https://example.com",
        title="Title",
        source="rss",
        published_at=PUBLISHED_AT,
        excerpt="Excerpt",
        score=EXPECTED_SCORE,
        summary="Summary",
    )
    digest = Digest(
        date=DIGEST_DATE,
        articles=[scored],
        executive_summary="",
        contrarian_insights="",
        follow_up_questions="",
        trending_themes="",
        source_stats={},
    )
    assert all(isinstance(a, ScoredItem) for a in digest.articles)


def test_digest_source_stats_is_dict() -> None:
    digest = Digest(
        date=DIGEST_DATE,
        articles=[],
        executive_summary="",
        contrarian_insights="",
        follow_up_questions="",
        trending_themes="",
        source_stats={"rss": 5, "run_duration_s": 42},
    )
    assert isinstance(digest.source_stats, dict)


# ---------------------------------------------------------------------------
# Cross-type: stage boundary compatibility
# ---------------------------------------------------------------------------


def test_scored_item_fields_are_subset_of_excerpt_item() -> None:
    """ScoredItem extends ExcerptItem fields with score + summary at Pass 1 boundary."""
    excerpt = ExcerptItem(
        url="https://example.com",
        title="Title",
        source="rss",
        published_at=PUBLISHED_AT,
        excerpt="Excerpt",
        url_hash="u1",
        content_hash="c1",
    )
    scored = ScoredItem(
        url=excerpt.url,
        title=excerpt.title,
        source=excerpt.source,
        published_at=excerpt.published_at,
        excerpt=excerpt.excerpt,
        score=EXPECTED_SCORE,
        summary="Summary",
    )
    assert scored.url == excerpt.url
    assert scored.excerpt == excerpt.excerpt


def test_full_item_carries_score_and_summary_from_pass1() -> None:
    """FullItem must carry score + summary from ScoredItem through Pass 2 boundary."""
    scored = ScoredItem(
        url="https://example.com",
        title="Title",
        source="rss",
        published_at=PUBLISHED_AT,
        excerpt="Excerpt",
        score=EXPECTED_SCORE,
        summary="Pass 1 summary",
    )
    full = FullItem(
        url=scored.url,
        title=scored.title,
        source=scored.source,
        published_at=scored.published_at,
        full_text="Full article text",
        word_count=EXPECTED_WORD_COUNT,
        score=scored.score,
        summary=scored.summary,
    )
    assert full.score == scored.score
    assert full.summary == scored.summary


# ---------------------------------------------------------------------------
# Type annotation smoke tests (runtime checks complementing mypy)
# ---------------------------------------------------------------------------


def test_score_int_not_accepted_as_float() -> None:
    """ScoredItem.score must be int; a float score should not silently pass."""
    item = ScoredItem(
        url="https://example.com",
        title="Title",
        source="rss",
        published_at=PUBLISHED_AT,
        excerpt="Excerpt",
        score=EXPECTED_SCORE,
        summary="Summary",
    )
    # Runtime: score must be int, not float
    assert isinstance(item.score, int)
    assert not isinstance(item.score, float)


@pytest.mark.parametrize(
    "content_type",
    ["email", "web", "arxiv"],
)
def test_raw_item_accepts_valid_content_types(content_type: str) -> None:
    item = RawItem(
        url="https://example.com",
        title="Title",
        source="rss",
        published_at=PUBLISHED_AT,
        raw_content="content",
        content_type=content_type,
    )
    assert item.content_type == content_type
