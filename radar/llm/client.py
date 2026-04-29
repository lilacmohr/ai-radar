"""LLM backend abstraction for ai-radar.

Routes all LLM calls through litellm with model alias resolution, automatic
fallback, and optional Langfuse tracing. Call configure_litellm() and
configure_model_aliases() once at pipeline startup before any LLMClient calls.

Alias convention (SPEC.md §4.2):
  "fast"             → primary model for Pass 1
  "fast_fallback"    → fallback if "fast" raises ServiceUnavailableError
  "quality"          → primary model for Pass 2
  "quality_fallback" → fallback if "quality" raises ServiceUnavailableError

Langfuse tracing is enabled automatically when LANGFUSE_PUBLIC_KEY and
LANGFUSE_SECRET_KEY are present in the environment; flush() is called after
every completion (success or error) to prevent data loss in short-lived runs.
"""

import structlog

logger = structlog.get_logger(__name__)

# Populated by configure_model_aliases(); maps short alias → provider model string.
_MODEL_ALIASES: dict[str, str] = {}


def configure_litellm(*, drop_params: bool, max_retries: int) -> None:
    """Set litellm global settings for the process.

    Call once at pipeline startup before any LLMClient.complete() call.
    """
    raise NotImplementedError


def configure_model_aliases(aliases: dict[str, str]) -> None:
    """Register model alias → provider model string mappings.

    Example: {"fast": "github_models/gpt-4o-mini", "fast_fallback": "anthropic/claude-haiku-4-5"}
    """
    raise NotImplementedError


class LLMClient:
    """LLM client backed by litellm with model alias resolution and optional Langfuse tracing.

    Configuration is set at the process level via configure_litellm() and
    configure_model_aliases() before any calls to complete().
    """

    def __init__(self) -> None:
        pass  # litellm uses module-level config; no client object to construct

    def complete(  # noqa: PLR0913
        self,
        system: str,
        user: str,
        model: str,
        response_format: dict[str, str] | None = None,
        pipeline_stage: str | None = None,
        prompt_version: str | None = None,
        project: str | None = None,
        metadata: dict[str, object] | None = None,
    ) -> str:
        """Send a chat completion request and return the response text.

        Resolves model alias via _MODEL_ALIASES, calls litellm.completion,
        falls back to <alias>_fallback on ServiceUnavailableError, and flushes
        Langfuse if LANGFUSE_PUBLIC_KEY / LANGFUSE_SECRET_KEY are set.
        """
        raise NotImplementedError
