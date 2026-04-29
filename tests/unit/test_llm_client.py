"""Tests for radar/llm/client.py — TDD red phase for LiteLLM migration (issue #127).

Covers:
- configure_litellm(): sets litellm globals (drop_params, num_retries)
- configure_model_aliases(): resolves short aliases ("fast") to provider strings
- complete(): happy path via litellm.completion, model alias resolution
- complete(): fallback on ServiceUnavailableError; RuntimeError when both fail
- complete(): no fallback when alias has no _fallback entry
- complete(): Langfuse flush() called on success and on error when keys present
- complete(): Langfuse NOT instantiated when keys are absent
- Contract: complete() signature matches TestLLMClient (including new kwargs)
"""

from __future__ import annotations

import inspect
from typing import TYPE_CHECKING
from unittest.mock import MagicMock, patch

import litellm
import litellm.exceptions
import pytest

import radar.llm.client as _client_module
from radar.llm.client import LLMClient, configure_litellm, configure_model_aliases
from tests.conftest import TestLLMClient

if TYPE_CHECKING:
    from collections.abc import Generator

# ---------------------------------------------------------------------------
# Patch targets
# ---------------------------------------------------------------------------

_LITELLM_COMPLETION = "litellm.completion"
_LANGFUSE_PATCH = "radar.llm.client.langfuse.Langfuse"

_FALLBACK_CALL_COUNT = 2  # primary attempt + one fallback attempt

# ---------------------------------------------------------------------------
# Factories
# ---------------------------------------------------------------------------


def _make_litellm_response(content: str = "hello from llm") -> MagicMock:
    mock = MagicMock()
    mock.choices = [MagicMock(message=MagicMock(content=content))]
    mock.usage = MagicMock(prompt_tokens=10, completion_tokens=20)
    return mock


def _service_unavailable() -> litellm.exceptions.ServiceUnavailableError:
    return litellm.exceptions.ServiceUnavailableError(
        message="service down",
        llm_provider="github_models",
        model="gpt-4o-mini",
        response=MagicMock(),
    )


def _rate_limit_error() -> litellm.exceptions.RateLimitError:
    return litellm.exceptions.RateLimitError(
        message="rate limited",
        llm_provider="github_models",
        model="gpt-4o-mini",
        response=MagicMock(),
    )


def _auth_error() -> litellm.exceptions.AuthenticationError:
    return litellm.exceptions.AuthenticationError(
        message="unauthorized",
        llm_provider="github_models",
        model="gpt-4o-mini",
        response=MagicMock(),
    )


def _timeout_error() -> litellm.exceptions.Timeout:
    return litellm.exceptions.Timeout(
        message="request timed out",
        llm_provider="github_models",
        model="gpt-4o-mini",
    )


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _reset_model_aliases() -> Generator[None, None, None]:
    """Clear module-level _MODEL_ALIASES before and after each test."""
    _client_module._MODEL_ALIASES.clear()  # noqa: SLF001
    yield
    _client_module._MODEL_ALIASES.clear()  # noqa: SLF001


# ---------------------------------------------------------------------------
# configure_litellm
# ---------------------------------------------------------------------------


def test_configure_litellm_sets_drop_params() -> None:
    configure_litellm(drop_params=True, max_retries=3)
    assert litellm.drop_params is True


def test_configure_litellm_sets_num_retries() -> None:
    configure_litellm(drop_params=False, max_retries=5)
    assert litellm.num_retries == 5  # noqa: PLR2004


def test_configure_litellm_drop_params_false() -> None:
    configure_litellm(drop_params=False, max_retries=1)
    assert litellm.drop_params is False


# ---------------------------------------------------------------------------
# configure_model_aliases
# ---------------------------------------------------------------------------


def test_configure_model_aliases_resolves_alias_in_complete() -> None:
    """complete(model="fast") must call litellm.completion with the resolved model string."""
    configure_model_aliases({"fast": "github_models/gpt-4o-mini"})
    with patch(_LITELLM_COMPLETION) as mock_completion:
        mock_completion.return_value = _make_litellm_response()
        LLMClient().complete(system="s", user="u", model="fast")
    assert mock_completion.call_args.kwargs["model"] == "github_models/gpt-4o-mini"


def test_configure_model_aliases_passes_literal_model_if_no_alias() -> None:
    """If model string is not in _MODEL_ALIASES, pass it through unchanged."""
    with patch(_LITELLM_COMPLETION) as mock_completion:
        mock_completion.return_value = _make_litellm_response()
        LLMClient().complete(system="s", user="u", model="github_models/gpt-4o-mini")
    assert mock_completion.call_args.kwargs["model"] == "github_models/gpt-4o-mini"


# ---------------------------------------------------------------------------
# complete(): happy path
# ---------------------------------------------------------------------------


def test_complete_returns_str() -> None:
    with patch(_LITELLM_COMPLETION) as mock_completion:
        mock_completion.return_value = _make_litellm_response()
        result = LLMClient().complete(system="sys", user="usr", model="gpt-4o-mini")
    assert isinstance(result, str)


def test_complete_returns_response_content() -> None:
    with patch(_LITELLM_COMPLETION) as mock_completion:
        mock_completion.return_value = _make_litellm_response("expected content")
        result = LLMClient().complete(system="sys", user="usr", model="gpt-4o-mini")
    assert result == "expected content"


def test_complete_passes_system_and_user_as_messages() -> None:
    with patch(_LITELLM_COMPLETION) as mock_completion:
        mock_completion.return_value = _make_litellm_response()
        LLMClient().complete(system="my-system", user="my-user", model="gpt-4o-mini")
        messages = mock_completion.call_args.kwargs["messages"]
    assert any(m["content"] == "my-system" for m in messages)
    assert any(m["content"] == "my-user" for m in messages)


def test_complete_passes_model_to_litellm() -> None:
    with patch(_LITELLM_COMPLETION) as mock_completion:
        mock_completion.return_value = _make_litellm_response()
        LLMClient().complete(system="s", user="u", model="github_models/gpt-4o")
    assert mock_completion.call_args.kwargs["model"] == "github_models/gpt-4o"


def test_complete_multiple_sequential_calls_return_correct_responses() -> None:
    with patch(_LITELLM_COMPLETION) as mock_completion:
        mock_completion.side_effect = [
            _make_litellm_response("first"),
            _make_litellm_response("second"),
        ]
        client = LLMClient()
        r1 = client.complete(system="s", user="u1", model="m")
        r2 = client.complete(system="s", user="u2", model="m")
    assert r1 == "first"
    assert r2 == "second"


# ---------------------------------------------------------------------------
# complete(): response_format passthrough
# ---------------------------------------------------------------------------


def test_response_format_forwarded_when_provided() -> None:
    fmt = {"type": "json_object"}
    with patch(_LITELLM_COMPLETION) as mock_completion:
        mock_completion.return_value = _make_litellm_response()
        LLMClient().complete(system="s", user="u", model="m", response_format=fmt)
    assert mock_completion.call_args.kwargs["response_format"] == fmt


def test_response_format_omitted_when_none() -> None:
    with patch(_LITELLM_COMPLETION) as mock_completion:
        mock_completion.return_value = _make_litellm_response()
        LLMClient().complete(system="s", user="u", model="m", response_format=None)
    assert "response_format" not in mock_completion.call_args.kwargs


# ---------------------------------------------------------------------------
# complete(): fallback on transient errors
# ---------------------------------------------------------------------------


def test_complete_falls_back_on_service_unavailable() -> None:
    """Primary model ServiceUnavailableError → fallback model returns response."""
    configure_model_aliases(
        {
            "fast": "github_models/gpt-4o-mini",
            "fast_fallback": "anthropic/claude-haiku-4-5",
        }
    )
    with patch(_LITELLM_COMPLETION) as mock_completion:
        mock_completion.side_effect = [
            _service_unavailable(),
            _make_litellm_response("fallback response"),
        ]
        result = LLMClient().complete(system="s", user="u", model="fast")
    assert result == "fallback response"
    assert mock_completion.call_count == _FALLBACK_CALL_COUNT
    second_model = mock_completion.call_args_list[1].kwargs["model"]
    assert second_model == "anthropic/claude-haiku-4-5"


def test_complete_raises_runtime_error_if_primary_and_fallback_both_fail() -> None:
    """If both primary and fallback fail, RuntimeError is raised."""
    configure_model_aliases(
        {
            "quality": "github_models/gpt-4o",
            "quality_fallback": "anthropic/claude-haiku-4-5",
        }
    )
    with patch(_LITELLM_COMPLETION) as mock_completion:
        mock_completion.side_effect = [_service_unavailable(), _service_unavailable()]
        with pytest.raises(RuntimeError):
            LLMClient().complete(system="s", user="u", model="quality")


def test_complete_no_fallback_when_alias_not_registered() -> None:
    """If model has no fallback alias, transient error propagates immediately."""
    with patch(_LITELLM_COMPLETION) as mock_completion:
        mock_completion.side_effect = _service_unavailable()
        with pytest.raises(litellm.exceptions.ServiceUnavailableError):
            LLMClient().complete(system="s", user="u", model="github_models/gpt-4o-mini")
    assert mock_completion.call_count == 1


def test_rate_limit_error_propagates_without_fallback() -> None:
    """RateLimitError is not a fallback trigger — it propagates immediately."""
    configure_model_aliases(
        {
            "fast": "github_models/gpt-4o-mini",
            "fast_fallback": "anthropic/claude-haiku-4-5",
        }
    )
    with patch(_LITELLM_COMPLETION) as mock_completion:
        mock_completion.side_effect = _rate_limit_error()
        with pytest.raises(litellm.exceptions.RateLimitError):
            LLMClient().complete(system="s", user="u", model="fast")
    assert mock_completion.call_count == 1


def test_auth_error_propagates_immediately_even_with_fallback() -> None:
    """AuthenticationError must never trigger fallback — it is a config failure, not transient."""
    configure_model_aliases(
        {
            "fast": "github_models/gpt-4o-mini",
            "fast_fallback": "anthropic/claude-haiku-4-5",
        }
    )
    with patch(_LITELLM_COMPLETION) as mock_completion:
        mock_completion.side_effect = _auth_error()
        with pytest.raises(litellm.exceptions.AuthenticationError):
            LLMClient().complete(system="s", user="u", model="fast")
    assert mock_completion.call_count == 1


def test_timeout_propagates_without_fallback() -> None:
    """Timeout propagates without triggering the fallback model."""
    configure_model_aliases(
        {
            "fast": "github_models/gpt-4o-mini",
            "fast_fallback": "anthropic/claude-haiku-4-5",
        }
    )
    with patch(_LITELLM_COMPLETION) as mock_completion:
        mock_completion.side_effect = _timeout_error()
        with pytest.raises(litellm.exceptions.Timeout):
            LLMClient().complete(system="s", user="u", model="fast")
    assert mock_completion.call_count == 1


# ---------------------------------------------------------------------------
# complete(): Langfuse tracing
# ---------------------------------------------------------------------------


def test_complete_without_langfuse_keys_no_langfuse_instantiated(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """When LANGFUSE_PUBLIC_KEY is absent, Langfuse must not be instantiated."""
    monkeypatch.delenv("LANGFUSE_PUBLIC_KEY", raising=False)
    monkeypatch.delenv("LANGFUSE_SECRET_KEY", raising=False)
    with patch(_LITELLM_COMPLETION) as mock_completion, patch(_LANGFUSE_PATCH) as mock_langfuse:
        mock_completion.return_value = _make_litellm_response()
        LLMClient().complete(system="s", user="u", model="m")
    mock_langfuse.assert_not_called()


def test_complete_with_langfuse_keys_calls_flush(monkeypatch: pytest.MonkeyPatch) -> None:
    """When Langfuse keys are present, flush() must be called after each completion."""
    monkeypatch.setenv("LANGFUSE_PUBLIC_KEY", "pk-test")
    monkeypatch.setenv("LANGFUSE_SECRET_KEY", "sk-test")
    with patch(_LITELLM_COMPLETION) as mock_completion, patch(_LANGFUSE_PATCH) as mock_langfuse_cls:
        mock_completion.return_value = _make_litellm_response()
        mock_instance = mock_langfuse_cls.return_value
        LLMClient().complete(system="s", user="u", model="m")
    mock_instance.flush.assert_called_once()


def test_complete_langfuse_flush_called_even_on_llm_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Langfuse flush() must be called even when litellm.completion raises."""
    monkeypatch.setenv("LANGFUSE_PUBLIC_KEY", "pk-test")
    monkeypatch.setenv("LANGFUSE_SECRET_KEY", "sk-test")
    with patch(_LITELLM_COMPLETION) as mock_completion, patch(_LANGFUSE_PATCH) as mock_langfuse_cls:
        mock_completion.side_effect = _service_unavailable()
        mock_instance = mock_langfuse_cls.return_value
        with pytest.raises((litellm.exceptions.ServiceUnavailableError, RuntimeError)):
            LLMClient().complete(system="s", user="u", model="m")
    mock_instance.flush.assert_called_once()


def test_complete_with_langfuse_keys_forwards_trace_metadata(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """pipeline_stage, prompt_version, project, and metadata must appear in Langfuse trace calls."""
    monkeypatch.setenv("LANGFUSE_PUBLIC_KEY", "pk-test")
    monkeypatch.setenv("LANGFUSE_SECRET_KEY", "sk-test")
    with patch(_LITELLM_COMPLETION) as mock_completion, patch(_LANGFUSE_PATCH) as mock_langfuse_cls:
        mock_completion.return_value = _make_litellm_response()
        mock_instance = mock_langfuse_cls.return_value
        LLMClient().complete(
            system="s",
            user="u",
            model="m",
            pipeline_stage="pass1",
            prompt_version="pass1-v1",
            project="ai-radar",
            metadata={"item_count": 5},
        )
    calls_repr = repr(mock_instance.mock_calls)
    assert "pass1" in calls_repr, "pipeline_stage not forwarded to Langfuse"
    assert "pass1-v1" in calls_repr, "prompt_version not forwarded to Langfuse"
    assert "ai-radar" in calls_repr, "project not forwarded to Langfuse"
    assert "item_count" in calls_repr, "metadata not forwarded to Langfuse"


# ---------------------------------------------------------------------------
# Contract: signature parity between LLMClient and TestLLMClient
# ---------------------------------------------------------------------------


def test_complete_signature_matches_test_llm_client() -> None:
    """LLMClient.complete and TestLLMClient.complete must have identical parameter names."""
    llm_params = list(inspect.signature(LLMClient.complete).parameters.keys())
    test_params = list(inspect.signature(TestLLMClient.complete).parameters.keys())
    assert llm_params == test_params


def test_new_kwargs_all_default_to_none() -> None:
    """pipeline_stage, prompt_version, project, metadata must all default to None."""
    sig = inspect.signature(LLMClient.complete)
    for kwarg in ("pipeline_stage", "prompt_version", "project", "metadata"):
        assert kwarg in sig.parameters, f"missing param: {kwarg}"
        assert sig.parameters[kwarg].default is None, f"{kwarg} default is not None"
