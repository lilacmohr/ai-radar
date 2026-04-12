"""Tests for radar/llm/client.py.

Verifies:
- complete() returns the LLM response content as a plain str
- Missing GH_MODELS_TOKEN raises ValueError on construction
- Retry logic: RateLimitError (429), APIStatusError (5xx), APITimeoutError
  → exponential backoff (1s, 2s, 4s), max 3 retries
- Exhaustion: all 3 retries fail → exception propagates (never returns None or "")
- Partial retry: first attempt fails, second succeeds → returns response
- Contract: complete() signature matches TestLLMClient; return type is str
"""

import inspect
from unittest.mock import MagicMock, patch

import openai
import pytest

from radar.llm.client import LLMClient
from tests.conftest import TestLLMClient

# ---------------------------------------------------------------------------
# Constants / patch targets
# ---------------------------------------------------------------------------

_CLIENT_PATCH = "radar.llm.client.openai.OpenAI"
_SLEEP_PATCH = "radar.llm.client.time.sleep"
_MAX_ATTEMPTS = 4  # 1 initial + 3 retries (SPEC.md §3.7)

# ---------------------------------------------------------------------------
# Factories
# ---------------------------------------------------------------------------


def _make_openai_response(content: str = "hello from llm") -> MagicMock:
    mock = MagicMock()
    mock.choices = [MagicMock(message=MagicMock(content=content))]
    return mock


def _rate_limit_error() -> openai.RateLimitError:
    return openai.RateLimitError("rate limited", response=MagicMock(), body=None)


def _api_status_error() -> openai.APIStatusError:
    mock_response = MagicMock()
    mock_response.status_code = 500
    return openai.APIStatusError("server error", response=mock_response, body=None)


def _timeout_error() -> openai.APITimeoutError:
    return openai.APITimeoutError(request=MagicMock())


# ---------------------------------------------------------------------------
# Happy path: return value
# ---------------------------------------------------------------------------


def test_complete_returns_str(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GH_MODELS_TOKEN", "fake-token")
    with patch(_CLIENT_PATCH) as mock_openai, patch(_SLEEP_PATCH):
        mock_openai.return_value.chat.completions.create.return_value = _make_openai_response()
        result = LLMClient().complete(system="sys", user="usr", model="gpt-4o-mini")
    assert isinstance(result, str)


def test_complete_returns_response_content(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GH_MODELS_TOKEN", "fake-token")
    with patch(_CLIENT_PATCH) as mock_openai, patch(_SLEEP_PATCH):
        mock_openai.return_value.chat.completions.create.return_value = _make_openai_response(
            "expected content"
        )
        result = LLMClient().complete(system="sys", user="usr", model="gpt-4o-mini")
    assert result == "expected content"


def test_complete_passes_system_and_user_as_messages(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GH_MODELS_TOKEN", "fake-token")
    with patch(_CLIENT_PATCH) as mock_openai, patch(_SLEEP_PATCH):
        mock_create = mock_openai.return_value.chat.completions.create
        mock_create.return_value = _make_openai_response()
        LLMClient().complete(system="my-system", user="my-user", model="gpt-4o-mini")
        messages = mock_create.call_args.kwargs["messages"]
    assert any(m["content"] == "my-system" for m in messages)
    assert any(m["content"] == "my-user" for m in messages)


def test_complete_passes_model_to_api(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GH_MODELS_TOKEN", "fake-token")
    with patch(_CLIENT_PATCH) as mock_openai, patch(_SLEEP_PATCH):
        mock_create = mock_openai.return_value.chat.completions.create
        mock_create.return_value = _make_openai_response()
        LLMClient().complete(system="s", user="u", model="gpt-4o")
        assert mock_create.call_args.kwargs["model"] == "gpt-4o"


def test_multiple_sequential_calls_return_correct_responses(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("GH_MODELS_TOKEN", "fake-token")
    with patch(_CLIENT_PATCH) as mock_openai, patch(_SLEEP_PATCH):
        mock_openai.return_value.chat.completions.create.side_effect = [
            _make_openai_response("first"),
            _make_openai_response("second"),
        ]
        client = LLMClient()
        r1 = client.complete(system="s", user="u1", model="gpt-4o-mini")
        r2 = client.complete(system="s", user="u2", model="gpt-4o-mini")
    assert r1 == "first"
    assert r2 == "second"


# ---------------------------------------------------------------------------
# Missing token
# ---------------------------------------------------------------------------


def test_missing_token_raises_value_error(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("GH_MODELS_TOKEN", raising=False)
    with pytest.raises(ValueError, match="GH_MODELS_TOKEN"):
        LLMClient()


# ---------------------------------------------------------------------------
# Retry: RateLimitError  # noqa: ERA001
# ---------------------------------------------------------------------------


def test_rate_limit_error_retries_and_succeeds(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GH_MODELS_TOKEN", "fake-token")
    with patch(_CLIENT_PATCH) as mock_openai, patch(_SLEEP_PATCH):
        mock_create = mock_openai.return_value.chat.completions.create
        mock_create.side_effect = [_rate_limit_error(), _make_openai_response("ok")]
        result = LLMClient().complete(system="s", user="u", model="gpt-4o-mini")
    assert result == "ok"


def test_rate_limit_error_total_attempts_is_four(monkeypatch: pytest.MonkeyPatch) -> None:
    """1 initial attempt + 3 retries = 4 total calls before giving up."""
    monkeypatch.setenv("GH_MODELS_TOKEN", "fake-token")
    with patch(_CLIENT_PATCH) as mock_openai, patch(_SLEEP_PATCH):
        mock_create = mock_openai.return_value.chat.completions.create
        mock_create.side_effect = _rate_limit_error()
        with pytest.raises(openai.RateLimitError):
            LLMClient().complete(system="s", user="u", model="gpt-4o-mini")
        assert mock_create.call_count == _MAX_ATTEMPTS


def test_rate_limit_exhaustion_raises_not_returns(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GH_MODELS_TOKEN", "fake-token")
    with patch(_CLIENT_PATCH) as mock_openai, patch(_SLEEP_PATCH):
        mock_openai.return_value.chat.completions.create.side_effect = _rate_limit_error()
        with pytest.raises(openai.RateLimitError):
            LLMClient().complete(system="s", user="u", model="gpt-4o-mini")


# ---------------------------------------------------------------------------
# Retry: APIStatusError (5xx)
# ---------------------------------------------------------------------------


def test_api_status_error_retries_and_succeeds(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GH_MODELS_TOKEN", "fake-token")
    with patch(_CLIENT_PATCH) as mock_openai, patch(_SLEEP_PATCH):
        mock_create = mock_openai.return_value.chat.completions.create
        mock_create.side_effect = [_api_status_error(), _make_openai_response("ok")]
        result = LLMClient().complete(system="s", user="u", model="gpt-4o-mini")
    assert result == "ok"


def test_api_status_error_total_attempts_is_four(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GH_MODELS_TOKEN", "fake-token")
    with patch(_CLIENT_PATCH) as mock_openai, patch(_SLEEP_PATCH):
        mock_create = mock_openai.return_value.chat.completions.create
        mock_create.side_effect = _api_status_error()
        with pytest.raises(openai.APIStatusError):
            LLMClient().complete(system="s", user="u", model="gpt-4o-mini")
        assert mock_create.call_count == _MAX_ATTEMPTS


def test_api_status_error_exhaustion_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GH_MODELS_TOKEN", "fake-token")
    with patch(_CLIENT_PATCH) as mock_openai, patch(_SLEEP_PATCH):
        mock_openai.return_value.chat.completions.create.side_effect = _api_status_error()
        with pytest.raises(openai.APIStatusError):
            LLMClient().complete(system="s", user="u", model="gpt-4o-mini")


def test_api_status_error_4xx_does_not_retry(monkeypatch: pytest.MonkeyPatch) -> None:
    """Non-5xx APIStatusError (e.g. 401) must not be retried (SPEC.md §3.7)."""
    monkeypatch.setenv("GH_MODELS_TOKEN", "fake-token")
    mock_response = MagicMock()
    mock_response.status_code = 401
    err = openai.APIStatusError("unauthorized", response=mock_response, body=None)
    with patch(_CLIENT_PATCH) as mock_openai, patch(_SLEEP_PATCH) as mock_sleep:
        mock_create = mock_openai.return_value.chat.completions.create
        mock_create.side_effect = err
        with pytest.raises(openai.APIStatusError):
            LLMClient().complete(system="s", user="u", model="gpt-4o-mini")
        assert mock_create.call_count == 1  # no retry on 4xx
        mock_sleep.assert_not_called()


# ---------------------------------------------------------------------------
# Retry: timeout  # noqa: ERA001
# ---------------------------------------------------------------------------


def test_timeout_error_retries_and_succeeds(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GH_MODELS_TOKEN", "fake-token")
    with patch(_CLIENT_PATCH) as mock_openai, patch(_SLEEP_PATCH):
        mock_create = mock_openai.return_value.chat.completions.create
        mock_create.side_effect = [_timeout_error(), _make_openai_response("ok")]
        result = LLMClient().complete(system="s", user="u", model="gpt-4o-mini")
    assert result == "ok"


def test_timeout_error_total_attempts_is_four(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GH_MODELS_TOKEN", "fake-token")
    with patch(_CLIENT_PATCH) as mock_openai, patch(_SLEEP_PATCH):
        mock_create = mock_openai.return_value.chat.completions.create
        mock_create.side_effect = _timeout_error()
        with pytest.raises(openai.APITimeoutError):
            LLMClient().complete(system="s", user="u", model="gpt-4o-mini")
        assert mock_create.call_count == _MAX_ATTEMPTS


def test_timeout_exhaustion_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GH_MODELS_TOKEN", "fake-token")
    with patch(_CLIENT_PATCH) as mock_openai, patch(_SLEEP_PATCH):
        mock_openai.return_value.chat.completions.create.side_effect = _timeout_error()
        with pytest.raises(openai.APITimeoutError):
            LLMClient().complete(system="s", user="u", model="gpt-4o-mini")


# ---------------------------------------------------------------------------
# Retry: exponential backoff sleep durations
# ---------------------------------------------------------------------------


def test_retry_sleeps_with_1_2_4_backoff(monkeypatch: pytest.MonkeyPatch) -> None:
    """Backoff delays must be 1s, 2s, 4s on successive retries."""
    monkeypatch.setenv("GH_MODELS_TOKEN", "fake-token")
    with patch(_CLIENT_PATCH) as mock_openai, patch(_SLEEP_PATCH) as mock_sleep:
        mock_openai.return_value.chat.completions.create.side_effect = [
            _rate_limit_error(),
            _rate_limit_error(),
            _rate_limit_error(),
            _make_openai_response(),
        ]
        LLMClient().complete(system="s", user="u", model="gpt-4o-mini")
    sleep_durations = [c.args[0] for c in mock_sleep.call_args_list]
    assert sleep_durations == [1, 2, 4]


def test_no_sleep_on_success_without_retry(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GH_MODELS_TOKEN", "fake-token")
    with patch(_CLIENT_PATCH) as mock_openai, patch(_SLEEP_PATCH) as mock_sleep:
        mock_openai.return_value.chat.completions.create.return_value = _make_openai_response()
        LLMClient().complete(system="s", user="u", model="gpt-4o-mini")
    mock_sleep.assert_not_called()


# ---------------------------------------------------------------------------
# Contract
# ---------------------------------------------------------------------------


def test_complete_signature_matches_test_llm_client() -> None:
    """LLMClient and TestLLMClient must have identical complete() parameter names."""
    llm_params = list(inspect.signature(LLMClient.complete).parameters.keys())
    test_params = list(inspect.signature(TestLLMClient.complete).parameters.keys())
    assert llm_params == test_params


def test_return_type_is_str_not_none(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GH_MODELS_TOKEN", "fake-token")
    with patch(_CLIENT_PATCH) as mock_openai, patch(_SLEEP_PATCH):
        mock_openai.return_value.chat.completions.create.return_value = _make_openai_response()
        result = LLMClient().complete(system="s", user="u", model="gpt-4o-mini")
    assert result is not None
    assert type(result) is str


# ---------------------------------------------------------------------------
# response_format passthrough
# ---------------------------------------------------------------------------


def test_response_format_forwarded_to_api_when_provided(monkeypatch: pytest.MonkeyPatch) -> None:
    """response_format kwarg must be forwarded to the underlying API call."""
    monkeypatch.setenv("GH_MODELS_TOKEN", "fake-token")
    fmt = {"type": "json_object"}
    with patch(_CLIENT_PATCH) as mock_openai, patch(_SLEEP_PATCH):
        mock_create = mock_openai.return_value.chat.completions.create
        mock_create.return_value = _make_openai_response()
        LLMClient().complete(system="s", user="u", model="gpt-4o-mini", response_format=fmt)
        assert mock_create.call_args.kwargs["response_format"] == fmt


def test_response_format_omitted_from_api_when_none(monkeypatch: pytest.MonkeyPatch) -> None:
    """When response_format=None, the key must not appear in the API call kwargs."""
    monkeypatch.setenv("GH_MODELS_TOKEN", "fake-token")
    with patch(_CLIENT_PATCH) as mock_openai, patch(_SLEEP_PATCH):
        mock_create = mock_openai.return_value.chat.completions.create
        mock_create.return_value = _make_openai_response()
        LLMClient().complete(system="s", user="u", model="gpt-4o-mini", response_format=None)
        assert "response_format" not in mock_create.call_args.kwargs
