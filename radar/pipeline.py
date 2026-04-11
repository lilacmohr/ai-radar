"""Orchestrates the ai-radar pipeline end to end.

Stage: top-level orchestrator
Input: config, profile, sources, cache, injected stage instances
Output: int exit code (0 = success, 1 = partial failure, 2 = fatal)

Pipeline stages in order:
  1. Source fetch  → list[RawItem]
  2. dedup_by_url  → list[RawItem]
  3. excerpt_fetcher → list[ExcerptItem]
  4. dedup_by_content → list[ExcerptItem]
  5. pre_filter    → list[ExcerptItem]
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
from radar.processing.deduplicator import dedup_by_content, dedup_by_url  # noqa: F401
from radar.processing.excerpt_fetcher import excerpt_fetcher  # noqa: F401
from radar.processing.full_fetcher import FullFetcher
from radar.processing.pre_filter import pre_filter  # noqa: F401
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

    def run(self) -> int:
        """Execute the full pipeline. Returns an exit code per SPEC.md §3.7."""
        return _EXIT_FATAL
