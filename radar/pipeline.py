"""Orchestrates the ai-radar pipeline end to end.

Stage: top-level orchestrator
Input: config, profile, sources, cache, injected stage instances
Output: int exit code (0 = success, 1 = partial failure, 2 = fatal)

Pipeline stages in order:
  1. Source fetch  → list[RawItem]
  2. dedup_by_url  → list[RawItem]
  3. excerpt_fetcher → list[ExcerptItem]
  4. dedup_by_content → list[ExcerptItem]
  5. cap to max_articles_to_summarize (by recency)
  6. Summarizer (Pass 1) → list[ScoredItem]
  7. FullFetcher   → list[FullItem]
  8. Truncator     → list[FullItem]
  9. Synthesizer (Pass 2) → Digest
  10. MarkdownRenderer → str
  11. Write digest file
  12. cache.mark_seen() for all deduped items (AFTER successful write)

Exit codes per SPEC.md §3.7:
  0 — success (including zero-article digest)
  1 — partial failure (some sources failed, digest still generated)
  2 — fatal failure (no digest generated)

Cache safety rule (SPEC.md §4.4): mark_seen is called ONLY after a successful
digest file write. Never at fetch time.

Spec reference: SPEC.md §3.2 (pipeline steps), §3.7 (failure handling), §4.4 (cache safety).
"""

# 1. Standard library imports
import datetime
from pathlib import Path

# 2. Third-party imports
import structlog

# 3. Internal imports
from radar.cache import Cache
from radar.config import PipelineConfig, ProfileConfig
from radar.llm.summarizer import Summarizer
from radar.llm.synthesizer import Synthesizer
from radar.models import ExcerptItem  # noqa: F401
from radar.output.markdown import MarkdownRenderer
from radar.processing.deduplicator import dedup_by_content, dedup_by_url
from radar.processing.excerpt_fetcher import excerpt_fetcher
from radar.processing.full_fetcher import FullFetcher
from radar.processing.truncator import Truncator
from radar.sources.base import Source

# 4. Module-level logger
logger = structlog.get_logger(__name__)

# 5. Constants
_FAILURE_DIGEST_CONTENT = "Pipeline encountered an error. No digest generated today."
_EXIT_SUCCESS = 0
_EXIT_PARTIAL = 1
_EXIT_FATAL = 2


class Pipeline:
    """Runs the full ai-radar pipeline and returns an exit code."""

    def __init__(  # noqa: PLR0913
        self,
        config: PipelineConfig,
        profile: ProfileConfig,
        sources: list[Source],
        cache: Cache,
        summarizer: Summarizer,
        full_fetcher: FullFetcher,
        truncator: Truncator,
        synthesizer: Synthesizer,
        renderer: MarkdownRenderer,
        output_dir: Path,
    ) -> None:
        self._config = config
        self._profile = profile
        self._sources = sources
        self._cache = cache
        self._summarizer = summarizer
        self._full_fetcher = full_fetcher
        self._truncator = truncator
        self._synthesizer = synthesizer
        self._renderer = renderer
        self._output_dir = output_dir

    def run(self, run_date: datetime.date | None = None) -> int:
        """Execute the full pipeline. Returns an exit code per SPEC.md §3.7."""
        today = run_date if run_date is not None else datetime.datetime.now(tz=datetime.UTC).date()
        partial_failure = False

        # Stage 1: Source fetch
        raw_items = []
        for source in self._sources:
            try:
                fetched = source.fetch()
                raw_items.extend(fetched)
                logger.info(
                    "source_fetch_complete",
                    source=type(source).__name__,
                    item_count=len(fetched),
                )
            except Exception:  # noqa: BLE001
                logger.warning("source_fetch_failed", source=type(source).__name__)
                partial_failure = True

        if not raw_items and partial_failure:
            self._write_failure_digest(today)
            return _EXIT_FATAL

        # Stage 2: dedup by URL
        deduped_by_url = dedup_by_url(raw_items, self._cache)

        # Stage 3: excerpt fetch
        excerpt_items = excerpt_fetcher(deduped_by_url)

        # Stage 4: dedup by content
        deduped_items = dedup_by_content(excerpt_items, self._cache)

        # Stage 5: cap articles sent to Pass 1 (sort by recency, take top N)
        cap = self._config.max_articles_to_summarize
        capped_items = sorted(deduped_items, key=lambda x: x.published_at or datetime.datetime.min.replace(tzinfo=datetime.timezone.utc), reverse=True)[:cap]
        logger.info("pre_summarizer_cap", input=len(deduped_items), capped=len(capped_items), cap=cap)

        # Stage 6: Pass 1 (Summarizer) — raises on LLM error
        try:
            scored_items = self._summarizer.summarize(capped_items)
        except Exception:
            logger.exception("summarizer_failed")
            self._write_failure_digest(today)
            return _EXIT_FATAL

        # Stage 7: full fetch (skip if nothing scored — Synthesizer handles empty list)
        if scored_items:
            full_items = self._full_fetcher.fetch(scored_items)
            truncated_items = self._truncator.truncate(full_items)
        else:
            truncated_items = []

        # Stage 9: Pass 2 (Synthesizer) — raises on LLM error
        try:
            source_stats = {
                "summarization_model": self._config.summarization_model,
                "synthesis_model": self._config.synthesis_model,
                "sources_fetched": len(self._sources),
                "articles_scored": len(scored_items),
                "articles_in_digest": len(truncated_items),
            }
            digest = self._synthesizer.synthesize(truncated_items, run_date=today)
            digest.source_stats.update(source_stats)
        except Exception:
            logger.exception("synthesizer_failed")
            self._write_failure_digest(today)
            return _EXIT_FATAL

        # Stage 10: render
        markdown = self._renderer.render(digest)

        # Stage 11: write digest file
        output_path = self._output_dir / f"{today.strftime('%Y-%m-%d')}-digest.md"
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(markdown)
        logger.info("digest_written", output_path=str(output_path))

        # Stage 12: mark seen — ONLY after successful write
        for item in deduped_items:
            self._cache.mark_seen(item.url_hash, item.content_hash)

        return _EXIT_PARTIAL if partial_failure else _EXIT_SUCCESS

    def _write_failure_digest(self, today: datetime.date) -> None:
        """Write a failure-digest file when no articles could be fetched."""
        output_path = self._output_dir / f"{today.strftime('%Y-%m-%d')}-digest.md"
        output_path.write_text(_FAILURE_DIGEST_CONTENT)
        logger.error("failure_digest_written", output_path=str(output_path))
