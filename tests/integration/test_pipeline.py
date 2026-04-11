"""Tests for radar/pipeline.py.

Verifies the Pipeline orchestrator (issue #96):
- Happy path: all stages run, exit code 0, digest file written
- Partial failure: one source fails, pipeline continues, exit code 1
- All sources fail: failure-digest written, exit code 2
- Zero articles through pre-filter: minimal digest written, exit code 0
- LLM error propagates as exit code 2
- Cache safety: mark_seen called only after successful digest write, not at all on fatal failure
- Contract: run() -> int, constructor accepts expected args
"""

# 1. Standard library imports
import datetime
import json
from pathlib import Path
from unittest.mock import MagicMock

# 2. Third-party imports
import pytest

# 3. Internal imports
from radar.cache import Cache
from radar.config import PipelineConfig, ProfileConfig
from radar.llm.summarizer import Summarizer
from radar.llm.synthesizer import Synthesizer
from radar.models import ExcerptItem, FullItem, RawItem
from radar.output.markdown import MarkdownRenderer
from radar.pipeline import (
    _EXIT_FATAL,
    _EXIT_PARTIAL,
    _EXIT_SUCCESS,
    _FAILURE_DIGEST_CONTENT,
    Pipeline,
)
from radar.processing.full_fetcher import FullFetcher
from radar.processing.truncator import Truncator
from radar.sources.base import Source
from tests.conftest import TestLLMClient

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_DEFAULT_PUBLISHED_AT = datetime.datetime(2026, 4, 11, 9, 0, 0, tzinfo=datetime.UTC)
_ARTICLE_URL = "https://example.com/article"

_PASS1_CANNED_RESPONSE = json.dumps(
    [{"url": _ARTICLE_URL, "score": 8, "summary": "A summary of the AI article."}]
)

_PASS2_CANNED_RESPONSE = """\
## 📡 Executive Summary
- Key AI development.

## 🔍 Contrarian & Non-Obvious Insights
Contrarian observation here.

## ❓ Follow-Up Questions & Rabbit Holes
What are the follow-up questions?

## 📈 Trending Themes
Rapid AI deployment.
"""

# ---------------------------------------------------------------------------
# Mock classes
# ---------------------------------------------------------------------------


class MockSource(Source):
    """Test double for Source ABC."""

    def __init__(self, items: list[RawItem], *, raise_on_fetch: bool = False) -> None:
        self._items = items
        self._raise_on_fetch = raise_on_fetch

    def fetch(self) -> list[RawItem]:
        if self._raise_on_fetch:
            msg = "Source fetch failed"
            raise RuntimeError(msg)
        return list(self._items)


# ---------------------------------------------------------------------------
# Factories
# ---------------------------------------------------------------------------


def _make_raw_item(**kwargs: object) -> RawItem:
    defaults: dict[str, object] = {
        "url": _ARTICLE_URL,
        "title": "AI Model Advances in 2026",
        "source": "test-source",
        "published_at": _DEFAULT_PUBLISHED_AT,
        "raw_content": "Content about AI.",
        "content_type": "web",
    }
    defaults.update(kwargs)
    return RawItem(**defaults)  # type: ignore[arg-type]


def _make_excerpt_item(**kwargs: object) -> ExcerptItem:
    defaults: dict[str, object] = {
        "url": _ARTICLE_URL,
        "title": "AI Model Advances in 2026",
        "source": "test-source",
        "published_at": _DEFAULT_PUBLISHED_AT,
        "excerpt": "This article discusses AI and machine learning advances in detail.",
        "url_hash": "urlhash_abc123",
        "content_hash": "contenthash_def456",
    }
    defaults.update(kwargs)
    return ExcerptItem(**defaults)  # type: ignore[arg-type]


def _make_full_item(**kwargs: object) -> FullItem:
    defaults: dict[str, object] = {
        "url": _ARTICLE_URL,
        "title": "AI Model Advances in 2026",
        "source": "test-source",
        "published_at": _DEFAULT_PUBLISHED_AT,
        "full_text": "Full text about AI advances " * 10,
        "word_count": 50,
        "score": 8,
        "summary": "A summary of the article.",
    }
    defaults.update(kwargs)
    return FullItem(**defaults)  # type: ignore[arg-type]


def _make_pipeline(  # noqa: PLR0913
    monkeypatch: pytest.MonkeyPatch,
    *,
    sources: list[Source] | None = None,
    excerpt_items: list[ExcerptItem] | None = None,
    full_items: list[FullItem] | None = None,
    pass1_responses: list[str] | None = None,
    pass2_responses: list[str] | None = None,
    output_dir: Path,
) -> tuple[Pipeline, MagicMock]:
    """Build a Pipeline with all external I/O mocked out.

    Patches radar.pipeline.excerpt_fetcher so no HTTP calls are made.
    Returns (pipeline, mock_cache) so tests can assert on cache.mark_seen calls.
    """
    _excerpt_items = excerpt_items if excerpt_items is not None else [_make_excerpt_item()]
    _full_items = full_items if full_items is not None else [_make_full_item()]

    # Patch the module-level excerpt_fetcher imported by pipeline.py
    monkeypatch.setattr("radar.pipeline.excerpt_fetcher", lambda _items: _excerpt_items)

    cache: MagicMock = MagicMock(spec=Cache)
    cache.is_seen.return_value = False

    config = PipelineConfig()
    profile = ProfileConfig(role="Engineer", interests=["AI"])

    pass1_client = TestLLMClient(responses=pass1_responses or [_PASS1_CANNED_RESPONSE])
    pass2_client = TestLLMClient(responses=pass2_responses or [_PASS2_CANNED_RESPONSE])

    summarizer = Summarizer(pass1_client, config, profile)
    synthesizer = Synthesizer(pass2_client, config, profile)

    mock_full_fetcher: MagicMock = MagicMock(spec=FullFetcher)
    mock_full_fetcher.fetch.return_value = _full_items

    truncator = Truncator(config)
    renderer = MarkdownRenderer()

    if sources is None:
        sources = [MockSource([_make_raw_item()])]

    pipeline = Pipeline(
        config=config,
        profile=profile,
        sources=sources,
        cache=cache,
        summarizer=summarizer,
        full_fetcher=mock_full_fetcher,  # type: ignore[arg-type]
        truncator=truncator,
        synthesizer=synthesizer,
        renderer=renderer,
        output_dir=output_dir,
    )
    return pipeline, cache


# ---------------------------------------------------------------------------
# Contract tests
# ---------------------------------------------------------------------------


def test_pipeline_constructor_accepts_expected_args(
    monkeypatch: pytest.MonkeyPatch,
    temp_output_dir: Path,
) -> None:
    """Pipeline instantiation with full args does not raise."""
    pipeline, _ = _make_pipeline(monkeypatch, output_dir=temp_output_dir)
    assert pipeline is not None


def test_pipeline_run_returns_int(
    monkeypatch: pytest.MonkeyPatch,
    temp_output_dir: Path,
) -> None:
    """run() return value is an int."""
    pipeline, _ = _make_pipeline(monkeypatch, output_dir=temp_output_dir)
    result = pipeline.run()
    assert isinstance(result, int)


# ---------------------------------------------------------------------------
# Happy path
# ---------------------------------------------------------------------------


def test_pipeline_happy_path_returns_exit_code_0(
    monkeypatch: pytest.MonkeyPatch,
    temp_output_dir: Path,
) -> None:
    pipeline, _ = _make_pipeline(monkeypatch, output_dir=temp_output_dir)
    assert pipeline.run() == _EXIT_SUCCESS


def test_pipeline_writes_markdown_file(
    monkeypatch: pytest.MonkeyPatch,
    temp_output_dir: Path,
) -> None:
    pipeline, _ = _make_pipeline(monkeypatch, output_dir=temp_output_dir)
    pipeline.run()
    md_files = list(temp_output_dir.glob("*.md"))
    assert len(md_files) >= 1


def test_pipeline_digest_contains_article_title(
    monkeypatch: pytest.MonkeyPatch,
    temp_output_dir: Path,
) -> None:
    excerpt_items = [_make_excerpt_item(title="Unique Pipeline Test Article")]
    full_items = [_make_full_item(title="Unique Pipeline Test Article")]
    pass1 = json.dumps([{"url": _ARTICLE_URL, "score": 8, "summary": "Summary of unique article."}])
    pipeline, _ = _make_pipeline(
        monkeypatch,
        excerpt_items=excerpt_items,
        full_items=full_items,
        pass1_responses=[pass1],
        output_dir=temp_output_dir,
    )
    pipeline.run()
    md_files = list(temp_output_dir.glob("*.md"))
    assert md_files
    content = md_files[0].read_text()
    assert "Unique Pipeline Test Article" in content


def test_pipeline_mark_seen_called_after_successful_run(
    monkeypatch: pytest.MonkeyPatch,
    temp_output_dir: Path,
) -> None:
    """mark_seen must be called after digest write (cache safety rule)."""
    pipeline, cache = _make_pipeline(monkeypatch, output_dir=temp_output_dir)
    pipeline.run()
    assert cache.mark_seen.called


# ---------------------------------------------------------------------------
# Partial failure: one source fails
# ---------------------------------------------------------------------------


def test_pipeline_single_source_fails_continues_with_remaining(
    monkeypatch: pytest.MonkeyPatch,
    temp_output_dir: Path,
) -> None:
    """Pipeline produces a digest even when one of two sources fails."""
    good_source = MockSource([_make_raw_item()])
    bad_source = MockSource([], raise_on_fetch=True)
    pipeline, _ = _make_pipeline(
        monkeypatch,
        sources=[bad_source, good_source],
        output_dir=temp_output_dir,
    )
    pipeline.run()
    md_files = list(temp_output_dir.glob("*.md"))
    assert len(md_files) >= 1


def test_pipeline_single_source_fails_returns_exit_code_1(
    monkeypatch: pytest.MonkeyPatch,
    temp_output_dir: Path,
) -> None:
    good_source = MockSource([_make_raw_item()])
    bad_source = MockSource([], raise_on_fetch=True)
    pipeline, _ = _make_pipeline(
        monkeypatch,
        sources=[bad_source, good_source],
        output_dir=temp_output_dir,
    )
    assert pipeline.run() == _EXIT_PARTIAL


# ---------------------------------------------------------------------------
# All sources fail
# ---------------------------------------------------------------------------


def test_pipeline_all_sources_fail_returns_exit_code_2(
    monkeypatch: pytest.MonkeyPatch,
    temp_output_dir: Path,
) -> None:
    pipeline, _ = _make_pipeline(
        monkeypatch,
        sources=[MockSource([], raise_on_fetch=True)],
        output_dir=temp_output_dir,
    )
    assert pipeline.run() == _EXIT_FATAL


def test_pipeline_all_sources_fail_writes_failure_digest(
    monkeypatch: pytest.MonkeyPatch,
    temp_output_dir: Path,
) -> None:
    """A failure-digest file must be written even when all sources fail."""
    pipeline, _ = _make_pipeline(
        monkeypatch,
        sources=[MockSource([], raise_on_fetch=True)],
        output_dir=temp_output_dir,
    )
    pipeline.run()
    md_files = list(temp_output_dir.glob("*.md"))
    assert md_files
    content = md_files[0].read_text()
    assert _FAILURE_DIGEST_CONTENT in content


def test_pipeline_all_sources_fail_mark_seen_not_called(
    monkeypatch: pytest.MonkeyPatch,
    temp_output_dir: Path,
) -> None:
    """mark_seen must not be called when no digest is generated."""
    pipeline, cache = _make_pipeline(
        monkeypatch,
        sources=[MockSource([], raise_on_fetch=True)],
        output_dir=temp_output_dir,
    )
    pipeline.run()
    cache.mark_seen.assert_not_called()


# ---------------------------------------------------------------------------
# Zero articles through pre-filter
# ---------------------------------------------------------------------------


def test_pipeline_zero_articles_pass_prefilter_returns_exit_code_0(
    monkeypatch: pytest.MonkeyPatch,
    temp_output_dir: Path,
) -> None:
    """Zero articles after pre-filter → minimal digest written, exit code 0."""
    # Title and excerpt with no interest keyword → pre_filter drops it
    no_match_item = _make_excerpt_item(
        title="Breaking news: sports results",
        excerpt="Breaking news about sports and weather forecasts.",
    )
    pipeline, _ = _make_pipeline(
        monkeypatch,
        excerpt_items=[no_match_item],
        output_dir=temp_output_dir,
    )
    assert pipeline.run() == _EXIT_SUCCESS


def test_pipeline_zero_articles_writes_minimal_digest(
    monkeypatch: pytest.MonkeyPatch,
    temp_output_dir: Path,
) -> None:
    """Zero articles → digest file written with no-notable-content message."""
    no_match_item = _make_excerpt_item(
        title="Breaking news: sports results",
        excerpt="Breaking news about sports and weather forecasts.",
    )
    pipeline, _ = _make_pipeline(
        monkeypatch,
        excerpt_items=[no_match_item],
        output_dir=temp_output_dir,
    )
    pipeline.run()
    md_files = list(temp_output_dir.glob("*.md"))
    assert md_files
    content = md_files[0].read_text()
    assert "No notable content" in content


# ---------------------------------------------------------------------------
# LLM error
# ---------------------------------------------------------------------------


def test_pipeline_llm_error_returns_exit_code_2(
    monkeypatch: pytest.MonkeyPatch,
    temp_output_dir: Path,
) -> None:
    """LLM API error during Pass 1 → pipeline returns exit code 2."""

    class _RaisingClient:
        def complete(
            self,
            system: str,  # noqa: ARG002
            user: str,  # noqa: ARG002
            model: str,  # noqa: ARG002
            response_format: dict[str, str] | None = None,  # noqa: ARG002
        ) -> str:
            msg = "LLM API down"
            raise RuntimeError(msg)

    excerpt_items = [_make_excerpt_item()]
    monkeypatch.setattr("radar.pipeline.excerpt_fetcher", lambda _items: excerpt_items)

    cache: MagicMock = MagicMock(spec=Cache)
    cache.is_seen.return_value = False

    config = PipelineConfig()
    profile = ProfileConfig(role="Engineer", interests=["AI"])

    summarizer = Summarizer(_RaisingClient(), config, profile)  # type: ignore[arg-type]
    pass2_client = TestLLMClient(responses=[_PASS2_CANNED_RESPONSE])
    synthesizer = Synthesizer(pass2_client, config, profile)

    mock_full_fetcher: MagicMock = MagicMock(spec=FullFetcher)
    mock_full_fetcher.fetch.return_value = [_make_full_item()]

    pipeline = Pipeline(
        config=config,
        profile=profile,
        sources=[MockSource([_make_raw_item()])],
        cache=cache,
        summarizer=summarizer,
        full_fetcher=mock_full_fetcher,  # type: ignore[arg-type]
        truncator=Truncator(config),
        synthesizer=synthesizer,
        renderer=MarkdownRenderer(),
        output_dir=temp_output_dir,
    )
    assert pipeline.run() == _EXIT_FATAL


# ---------------------------------------------------------------------------
# LLM error — cache safety
# ---------------------------------------------------------------------------


def test_pipeline_llm_error_mark_seen_not_called(
    monkeypatch: pytest.MonkeyPatch,
    temp_output_dir: Path,
) -> None:
    """mark_seen must not be called when LLM error causes fatal failure."""

    class _RaisingClient:
        def complete(
            self,
            system: str,  # noqa: ARG002
            user: str,  # noqa: ARG002
            model: str,  # noqa: ARG002
            response_format: dict[str, str] | None = None,  # noqa: ARG002
        ) -> str:
            msg = "LLM API down"
            raise RuntimeError(msg)

    excerpt_items = [_make_excerpt_item()]
    monkeypatch.setattr("radar.pipeline.excerpt_fetcher", lambda _items: excerpt_items)

    cache: MagicMock = MagicMock(spec=Cache)
    cache.is_seen.return_value = False

    config = PipelineConfig()
    profile = ProfileConfig(role="Engineer", interests=["AI"])

    summarizer = Summarizer(_RaisingClient(), config, profile)  # type: ignore[arg-type]
    pass2_client = TestLLMClient(responses=[_PASS2_CANNED_RESPONSE])
    synthesizer = Synthesizer(pass2_client, config, profile)

    mock_full_fetcher: MagicMock = MagicMock(spec=FullFetcher)
    mock_full_fetcher.fetch.return_value = [_make_full_item()]

    pipeline = Pipeline(
        config=config,
        profile=profile,
        sources=[MockSource([_make_raw_item()])],
        cache=cache,
        summarizer=summarizer,
        full_fetcher=mock_full_fetcher,  # type: ignore[arg-type]
        truncator=Truncator(config),
        synthesizer=synthesizer,
        renderer=MarkdownRenderer(),
        output_dir=temp_output_dir,
    )
    pipeline.run()
    cache.mark_seen.assert_not_called()


# ---------------------------------------------------------------------------
# Cache safety: mark_seen called with correct hashes
# ---------------------------------------------------------------------------


def test_pipeline_mark_seen_called_with_correct_hashes(
    monkeypatch: pytest.MonkeyPatch,
    temp_output_dir: Path,
) -> None:
    """mark_seen must be called with the url_hash and content_hash of each seen item."""
    item = _make_excerpt_item(url_hash="urlhash_abc123", content_hash="contenthash_def456")
    pipeline, cache = _make_pipeline(
        monkeypatch,
        excerpt_items=[item],
        output_dir=temp_output_dir,
    )
    pipeline.run()
    cache.mark_seen.assert_called_once_with("urlhash_abc123", "contenthash_def456")


# ---------------------------------------------------------------------------
# Exported constants (regression: importable from radar.pipeline)
# ---------------------------------------------------------------------------


def test_exit_success_is_zero() -> None:
    assert _EXIT_SUCCESS == 0


def test_exit_partial_is_one() -> None:
    assert _EXIT_PARTIAL == 1


def test_exit_fatal_is_two() -> None:
    assert _EXIT_FATAL == 2  # noqa: PLR2004


def test_failure_digest_content_is_str() -> None:
    assert isinstance(_FAILURE_DIGEST_CONTENT, str)
    assert len(_FAILURE_DIGEST_CONTENT) > 0
