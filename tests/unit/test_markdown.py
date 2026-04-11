"""Tests for radar/output/markdown.py.

Verifies the MarkdownRenderer stage (final output):
- Happy path: Digest → markdown string with all six sections in order
- Section headings render verbatim from module constants
- Article Summaries: each ScoredItem rendered with title, source, URL, score (N/10), summary
- Date formatted as YYYY-MM-DD in H1 title
- Articles order preserved
- Disclosure footer rendered with date substituted
- Pipeline Metadata section includes synthesis_model from source_stats
- Failure modes: empty articles, empty LLM text fields, missing source_stats key
- Failure-digest: zero-article digest renders "no notable content today" message
- Contract: render(digest: Digest) -> str
"""

# 1. Standard library imports
import datetime

# 3. Internal imports
from radar.models import Digest, ScoredItem
from radar.output.markdown import (
    _DISCLOSURE_FOOTER_TEMPLATE,
    _HEADING_ARTICLE_SUMMARIES,
    _HEADING_CONTRARIAN_INSIGHTS,
    _HEADING_EXECUTIVE_SUMMARY,
    _HEADING_FOLLOW_UP_QUESTIONS,
    _HEADING_PIPELINE_METADATA,
    _HEADING_TRENDING_THEMES,
    _NO_NOTABLE_CONTENT,
    MarkdownRenderer,
)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_DEFAULT_DATE = datetime.date(2026, 4, 11)
_DEFAULT_PUBLISHED_AT = datetime.datetime(2026, 4, 11, 9, 0, 0, tzinfo=datetime.UTC)

# ---------------------------------------------------------------------------
# Factories
# ---------------------------------------------------------------------------


def _make_scored_item(**kwargs: object) -> ScoredItem:
    defaults: dict[str, object] = {
        "url": "https://example.com/article",
        "title": "Test Article Title",
        "source": "test-source",
        "published_at": _DEFAULT_PUBLISHED_AT,
        "excerpt": "A short excerpt.",
        "score": 7,
        "summary": "A two-sentence summary of the article.",
    }
    defaults.update(kwargs)
    return ScoredItem(**defaults)  # type: ignore[arg-type]


def _make_digest(**kwargs: object) -> Digest:
    defaults: dict[str, object] = {
        "date": _DEFAULT_DATE,
        "articles": [_make_scored_item()],
        "executive_summary": "- Key development one.\n- Key development two.",
        "contrarian_insights": "Observation on mainstream misunderstanding.",
        "follow_up_questions": "What are the second-order effects?",
        "trending_themes": "Theme: rapid model deployment.",
        "source_stats": {
            "synthesis_model": "gpt-4o",
            "summarization_model": "gpt-4o-mini",
            "sources_fetched": 3,
            "articles_scored": 20,
            "articles_in_digest": 1,
        },
    }
    defaults.update(kwargs)
    return Digest(**defaults)  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# Happy path: return type
# ---------------------------------------------------------------------------


def test_markdown_render_returns_str() -> None:
    renderer = MarkdownRenderer()
    result = renderer.render(_make_digest())
    assert isinstance(result, str)


# ---------------------------------------------------------------------------
# Happy path: section headings present
# ---------------------------------------------------------------------------


def test_markdown_executive_summary_heading_present() -> None:
    renderer = MarkdownRenderer()
    result = renderer.render(_make_digest())
    assert _HEADING_EXECUTIVE_SUMMARY in result


def test_markdown_article_summaries_heading_present() -> None:
    renderer = MarkdownRenderer()
    result = renderer.render(_make_digest())
    assert _HEADING_ARTICLE_SUMMARIES in result


def test_markdown_contrarian_insights_heading_present() -> None:
    renderer = MarkdownRenderer()
    result = renderer.render(_make_digest())
    assert _HEADING_CONTRARIAN_INSIGHTS in result


def test_markdown_follow_up_questions_heading_present() -> None:
    renderer = MarkdownRenderer()
    result = renderer.render(_make_digest())
    assert _HEADING_FOLLOW_UP_QUESTIONS in result


def test_markdown_trending_themes_heading_present() -> None:
    renderer = MarkdownRenderer()
    result = renderer.render(_make_digest())
    assert _HEADING_TRENDING_THEMES in result


def test_markdown_pipeline_metadata_heading_present() -> None:
    renderer = MarkdownRenderer()
    result = renderer.render(_make_digest())
    assert _HEADING_PIPELINE_METADATA in result


# ---------------------------------------------------------------------------
# Happy path: H1 title with YYYY-MM-DD date
# ---------------------------------------------------------------------------


def test_markdown_title_contains_date_yyyy_mm_dd() -> None:
    digest = _make_digest(date=datetime.date(2026, 4, 11))
    renderer = MarkdownRenderer()
    result = renderer.render(digest)
    assert "2026-04-11" in result


def test_markdown_title_prefix_present() -> None:
    renderer = MarkdownRenderer()
    result = renderer.render(_make_digest())
    assert "# ai-radar Daily Briefing" in result


# ---------------------------------------------------------------------------
# Happy path: Article Summaries section content
# ---------------------------------------------------------------------------


def test_markdown_article_title_in_output() -> None:
    item = _make_scored_item(title="Unique Article Title")
    renderer = MarkdownRenderer()
    result = renderer.render(_make_digest(articles=[item]))
    assert "Unique Article Title" in result


def test_markdown_article_url_in_output() -> None:
    item = _make_scored_item(url="https://example.com/my-article")
    renderer = MarkdownRenderer()
    result = renderer.render(_make_digest(articles=[item]))
    assert "https://example.com/my-article" in result


def test_markdown_article_source_in_output() -> None:
    item = _make_scored_item(source="hackernews")
    renderer = MarkdownRenderer()
    result = renderer.render(_make_digest(articles=[item]))
    assert "hackernews" in result


def test_markdown_article_summary_in_output() -> None:
    item = _make_scored_item(summary="Unique summary text for this test.")
    renderer = MarkdownRenderer()
    result = renderer.render(_make_digest(articles=[item]))
    assert "Unique summary text for this test." in result


def test_markdown_article_score_formatted_as_n_over_10() -> None:
    item = _make_scored_item(score=8)
    renderer = MarkdownRenderer()
    result = renderer.render(_make_digest(articles=[item]))
    assert "8/10" in result


# ---------------------------------------------------------------------------
# Happy path: LLM section bodies
# ---------------------------------------------------------------------------


def test_markdown_executive_summary_body_present() -> None:
    digest = _make_digest(executive_summary="Key development one.")
    renderer = MarkdownRenderer()
    result = renderer.render(digest)
    assert "Key development one." in result


def test_markdown_contrarian_insights_body_present() -> None:
    digest = _make_digest(contrarian_insights="Mainstream view is wrong here.")
    renderer = MarkdownRenderer()
    result = renderer.render(digest)
    assert "Mainstream view is wrong here." in result


def test_markdown_follow_up_questions_body_present() -> None:
    digest = _make_digest(follow_up_questions="What happens next?")
    renderer = MarkdownRenderer()
    result = renderer.render(digest)
    assert "What happens next?" in result


def test_markdown_trending_themes_body_present() -> None:
    digest = _make_digest(trending_themes="Theme: rapid iteration.")
    renderer = MarkdownRenderer()
    result = renderer.render(digest)
    assert "Theme: rapid iteration." in result


# ---------------------------------------------------------------------------
# Happy path: section order
# ---------------------------------------------------------------------------


def test_markdown_sections_in_spec_order() -> None:
    """Sections must appear in the order defined by SPEC.md §3.4."""
    renderer = MarkdownRenderer()
    result = renderer.render(_make_digest())
    exec_pos = result.index(_HEADING_EXECUTIVE_SUMMARY)
    articles_pos = result.index(_HEADING_ARTICLE_SUMMARIES)
    contrarian_pos = result.index(_HEADING_CONTRARIAN_INSIGHTS)
    followup_pos = result.index(_HEADING_FOLLOW_UP_QUESTIONS)
    themes_pos = result.index(_HEADING_TRENDING_THEMES)
    metadata_pos = result.index(_HEADING_PIPELINE_METADATA)
    assert exec_pos < articles_pos < contrarian_pos < followup_pos < themes_pos < metadata_pos


# ---------------------------------------------------------------------------
# Happy path: article order preserved
# ---------------------------------------------------------------------------


def test_markdown_articles_order_preserved() -> None:
    items = [
        _make_scored_item(url=f"https://example.com/{i}", title=f"Article {i}") for i in range(3)
    ]
    renderer = MarkdownRenderer()
    result = renderer.render(_make_digest(articles=items))
    pos_0 = result.index("Article 0")
    pos_1 = result.index("Article 1")
    pos_2 = result.index("Article 2")
    assert pos_0 < pos_1 < pos_2


# ---------------------------------------------------------------------------
# Happy path: single-article digest
# ---------------------------------------------------------------------------


def test_markdown_single_article_renders_correctly() -> None:
    item = _make_scored_item(title="Only Article")
    renderer = MarkdownRenderer()
    result = renderer.render(_make_digest(articles=[item]))
    assert "Only Article" in result
    assert isinstance(result, str)
    assert len(result) > 0


# ---------------------------------------------------------------------------
# Happy path: pipeline metadata
# ---------------------------------------------------------------------------


def test_markdown_pipeline_metadata_synthesis_model_present() -> None:
    digest = _make_digest(source_stats={"synthesis_model": "gpt-4o"})
    renderer = MarkdownRenderer()
    result = renderer.render(digest)
    assert "gpt-4o" in result


# ---------------------------------------------------------------------------
# Happy path: disclosure footer
# ---------------------------------------------------------------------------


def test_markdown_disclosure_footer_present() -> None:
    digest = _make_digest(date=datetime.date(2026, 4, 11))
    renderer = MarkdownRenderer()
    result = renderer.render(digest)
    expected = _DISCLOSURE_FOOTER_TEMPLATE.format(date="2026-04-11")
    assert expected in result


# ---------------------------------------------------------------------------
# Failure modes: empty articles
# ---------------------------------------------------------------------------


def test_markdown_empty_articles_does_not_raise() -> None:
    digest = _make_digest(articles=[])
    renderer = MarkdownRenderer()
    renderer.render(digest)  # must not raise


def test_markdown_empty_articles_article_summaries_heading_present() -> None:
    digest = _make_digest(articles=[])
    renderer = MarkdownRenderer()
    result = renderer.render(digest)
    assert _HEADING_ARTICLE_SUMMARIES in result


def test_markdown_failure_digest_no_notable_content_today() -> None:
    """Zero-article digest renders the 'no notable content' message per SPEC §3.7."""
    digest = _make_digest(articles=[])
    renderer = MarkdownRenderer()
    result = renderer.render(digest)
    assert _NO_NOTABLE_CONTENT in result


# ---------------------------------------------------------------------------
# Failure modes: empty LLM text fields
# ---------------------------------------------------------------------------


def test_markdown_empty_llm_fields_headings_still_present() -> None:
    digest = _make_digest(
        executive_summary="",
        contrarian_insights="",
        follow_up_questions="",
        trending_themes="",
    )
    renderer = MarkdownRenderer()
    result = renderer.render(digest)
    assert _HEADING_EXECUTIVE_SUMMARY in result
    assert _HEADING_CONTRARIAN_INSIGHTS in result
    assert _HEADING_FOLLOW_UP_QUESTIONS in result
    assert _HEADING_TRENDING_THEMES in result


def test_markdown_empty_llm_fields_does_not_raise() -> None:
    digest = _make_digest(
        executive_summary="",
        contrarian_insights="",
        follow_up_questions="",
        trending_themes="",
    )
    renderer = MarkdownRenderer()
    renderer.render(digest)  # must not raise


# ---------------------------------------------------------------------------
# Failure modes: missing source_stats key
# ---------------------------------------------------------------------------


def test_markdown_missing_synthesis_model_does_not_raise() -> None:
    """source_stats without synthesis_model key must not raise KeyError."""
    digest = _make_digest(source_stats={})
    renderer = MarkdownRenderer()
    renderer.render(digest)  # must not raise


def test_markdown_missing_synthesis_model_renders_gracefully() -> None:
    digest = _make_digest(source_stats={})
    renderer = MarkdownRenderer()
    result = renderer.render(digest)
    assert isinstance(result, str)


# ---------------------------------------------------------------------------
# Contract tests
# ---------------------------------------------------------------------------


def test_markdown_render_signature_accepted() -> None:
    """render(digest: Digest) -> str signature is callable."""
    renderer = MarkdownRenderer()
    digest = _make_digest()
    result = renderer.render(digest)
    assert isinstance(result, str)


def test_markdown_renderer_instantiates() -> None:
    renderer = MarkdownRenderer()
    assert renderer is not None
