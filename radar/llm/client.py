"""LLM backend abstraction for ai-radar.

Wraps the GitHub Models OpenAI-compatible endpoint with exponential-backoff
retry logic. All outbound LLM calls in the pipeline go through this module —
Summarizer and Synthesizer receive an LLMClient instance rather than calling
the OpenAI SDK directly.

Retry policy (SPEC.md §3.7):
  Retryable:     RateLimitError (429), APIStatusError (5xx), APITimeoutError
  Non-retryable: APIStatusError (4xx except 429)
  Max retries:   3 (4 total attempts)
  Backoff:       1s, 2s, 4s
"""

import os
import time

import openai
import structlog

logger = structlog.get_logger(__name__)

_MAX_RETRIES = 3
_BACKOFF_BASE = 1  # seconds; doubles each retry: 1, 2, 4
_HTTP_SERVER_ERROR_MIN = 500


class LLMClient:
    """GitHub Models LLM client with exponential-backoff retry.

    Reads GH_MODELS_TOKEN from the environment on construction.
    Raises ValueError immediately if the token is not set.
    """

    def __init__(self) -> None:
        token = os.environ.get("GH_MODELS_TOKEN")
        if not token:
            msg = (
                "GH_MODELS_TOKEN environment variable is not set. "
                "Set it to a GitHub personal access token with Models: Read-only scope."
            )
            raise ValueError(msg)
        self._client = openai.OpenAI(
            base_url="https://models.github.ai/inference",
            api_key=token,
        )

    def complete(
        self,
        system: str,
        user: str,
        model: str,
        response_format: dict[str, str] | None = None,
    ) -> str:
        """Send a chat completion request and return the response text.

        Pass response_format={"type": "json_object"} to enable JSON mode.
        Retries up to _MAX_RETRIES times on transient errors (429, 5xx, timeout)
        with exponential backoff. Re-raises on exhaustion. Non-retryable errors
        (4xx other than 429) are raised immediately without retrying.
        """
        last_exc: openai.APIError | None = None

        for attempt in range(_MAX_RETRIES + 1):
            try:
                kwargs: dict[str, object] = {
                    "model": model,
                    "messages": [
                        {"role": "system", "content": system},
                        {"role": "user", "content": user},
                    ],
                }
                if response_format is not None:
                    kwargs["response_format"] = response_format
                response = self._client.chat.completions.create(**kwargs)  # type: ignore[call-overload]
                return str(response.choices[0].message.content)

            except openai.APIStatusError as exc:
                # RateLimitError (429) is a subclass of APIStatusError — always retry.
                # Other 4xx errors are not transient; re-raise immediately.
                is_rate_limit = isinstance(exc, openai.RateLimitError)
                if not is_rate_limit and exc.response.status_code < _HTTP_SERVER_ERROR_MIN:
                    raise
                last_exc = exc

            except openai.APITimeoutError as exc:
                last_exc = exc

            if attempt < _MAX_RETRIES:
                delay = _BACKOFF_BASE * (2**attempt)
                logger.warning(
                    "llm_retry",
                    attempt=attempt + 1,
                    max_retries=_MAX_RETRIES,
                    delay_s=delay,
                    error=str(last_exc),
                )
                time.sleep(delay)

        logger.error("llm_retry_exhausted", attempts=_MAX_RETRIES + 1, error=str(last_exc))
        raise last_exc  # type: ignore[misc]
