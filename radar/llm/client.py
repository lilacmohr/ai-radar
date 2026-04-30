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

import os
import time
from contextlib import nullcontext as _nullcontext

import langfuse  # patch target: radar.llm.client.langfuse.Langfuse
import litellm
import litellm.exceptions
import structlog
from langfuse import LangfuseGeneration

logger = structlog.get_logger(__name__)

# Populated by configure_model_aliases(); maps short alias → provider model string.
_MODEL_ALIASES: dict[str, str] = {}


def configure_litellm(*, drop_params: bool, max_retries: int) -> None:
    """Set litellm global settings for the process.

    Call once at pipeline startup before any LLMClient.complete() call.
    """
    litellm.drop_params = drop_params
    litellm.num_retries = max_retries


def configure_model_aliases(aliases: dict[str, str]) -> None:
    """Register model alias → provider model string mappings.

    Example: {"fast": "github/gpt-4o-mini", "fast_fallback": "anthropic/claude-haiku-4-5"}
    """
    _MODEL_ALIASES.update(aliases)


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
        lf_client = _make_langfuse_client()
        try:
            return self._complete_with_fallback(
                system=system,
                user=user,
                model=model,
                response_format=response_format,
                pipeline_stage=pipeline_stage,
                prompt_version=prompt_version,
                project=project,
                metadata=metadata,
                lf_client=lf_client,
            )
        finally:
            if lf_client is not None:
                lf_client.flush()

    def _complete_with_fallback(  # noqa: PLR0913
        self,
        system: str,
        user: str,
        model: str,
        response_format: dict[str, str] | None,
        pipeline_stage: str | None,
        prompt_version: str | None,
        project: str | None,
        metadata: dict[str, object] | None,
        lf_client: "langfuse.Langfuse | None",
    ) -> str:
        resolved = _MODEL_ALIASES.get(model, model)
        fallback_alias = f"{model}_fallback"
        has_fallback = fallback_alias in _MODEL_ALIASES

        try:
            return _call_litellm(
                resolved,
                system=system,
                user=user,
                response_format=response_format,
                pipeline_stage=pipeline_stage,
                prompt_version=prompt_version,
                project=project,
                metadata=metadata,
                lf_client=lf_client,
            )
        except litellm.exceptions.ServiceUnavailableError:
            if not has_fallback:
                raise
            fallback_model = _MODEL_ALIASES[fallback_alias]
            logger.warning(
                "llm_primary_unavailable_falling_back",
                primary=resolved,
                fallback=fallback_model,
            )
            try:
                return _call_litellm(
                    fallback_model,
                    system=system,
                    user=user,
                    response_format=response_format,
                    pipeline_stage=pipeline_stage,
                    prompt_version=prompt_version,
                    project=project,
                    metadata=metadata,
                    lf_client=lf_client,
                )
            except litellm.exceptions.ServiceUnavailableError as exc:
                msg = f"Both primary ({resolved}) and fallback ({fallback_model}) failed"
                raise RuntimeError(msg) from exc


def _call_litellm(  # noqa: PLR0913
    model: str,
    *,
    system: str,
    user: str,
    response_format: dict[str, str] | None,
    pipeline_stage: str | None,
    prompt_version: str | None,
    project: str | None,
    metadata: dict[str, object] | None,
    lf_client: "langfuse.Langfuse | None",
) -> str:
    messages = [
        {"role": "system", "content": system},
        {"role": "user", "content": user},
    ]
    kwargs: dict[str, object] = {"model": model, "messages": messages}
    if response_format is not None:
        kwargs["response_format"] = response_format

    tags = [project] if project else []
    with langfuse.propagate_attributes(tags=tags) if lf_client is not None else _nullcontext():
        observation = (
            _start_langfuse_generation(
                lf_client,
                model=model,
                pipeline_stage=pipeline_stage,
                prompt_version=prompt_version,
                project=project,
                metadata=metadata,
                messages=messages,
            )
            if lf_client is not None
            else None
        )
        t_start = time.monotonic()
        response = litellm.completion(**kwargs)
        elapsed_ms = int((time.monotonic() - t_start) * 1000)
        content: str = response.choices[0].message.content
        if observation is not None:
            observation.update(
                output=content,
                usage_details={
                    "input": response.usage.prompt_tokens,
                    "output": response.usage.completion_tokens,
                },
            )
            observation.end()

    logger.info(
        "llm_completion",
        model=model,
        prompt_tokens=response.usage.prompt_tokens,
        completion_tokens=response.usage.completion_tokens,
        tokens_used=response.usage.prompt_tokens + response.usage.completion_tokens,
        elapsed_ms=elapsed_ms,
    )
    return content


def _make_langfuse_client() -> "langfuse.Langfuse | None":
    if os.environ.get("LANGFUSE_PUBLIC_KEY") and os.environ.get("LANGFUSE_SECRET_KEY"):
        return langfuse.Langfuse()
    return None


def _start_langfuse_generation(  # noqa: PLR0913
    lf_client: "langfuse.Langfuse",
    *,
    model: str,
    pipeline_stage: str | None,
    prompt_version: str | None,
    project: str | None,
    metadata: dict[str, object] | None,
    messages: list[dict[str, str]],
) -> LangfuseGeneration:
    return lf_client.start_observation(
        as_type="generation",
        name=pipeline_stage or "llm_completion",
        version=prompt_version,
        input=messages,
        metadata={"model": model, "project": project, **(metadata or {})},
        model=model,
    )
