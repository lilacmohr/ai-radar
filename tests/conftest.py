"""Shared pytest fixtures for ai-radar tests.

Provides: TestLLMClient mock, temp_cache_dir, temp_output_dir.
"""

from pathlib import Path

import pytest


class TestLLMClient:
    """Mock LLMClient for use in unit and contract tests.

    Returns configurable canned responses without making real API calls.
    Call history is recorded in `.calls` for assertion in tests.

    Usage::

        client = TestLLMClient(responses=["response 1", "response 2"])
        result = client.complete(system="sys", user="usr", model="gpt-4o-mini")
        assert client.call_count == 1
        assert client.calls[0]["model"] == "gpt-4o-mini"
    """

    def __init__(self, responses: list[str] | None = None) -> None:
        self.responses: list[str] = responses or []
        self.call_count: int = 0
        self.calls: list[dict[str, object]] = []

    def complete(
        self,
        system: str,
        user: str,
        model: str,
        response_format: dict[str, str] | None = None,
    ) -> str:
        """Return the next canned response, cycling if exhausted."""
        self.calls.append(
            {"system": system, "user": user, "model": model, "response_format": response_format}
        )
        response = self.responses[self.call_count % len(self.responses)] if self.responses else ""
        self.call_count += 1
        return response


@pytest.fixture
def test_llm_client() -> TestLLMClient:
    """Return a fresh TestLLMClient with no canned responses."""
    return TestLLMClient()


@pytest.fixture
def temp_cache_dir(tmp_path: Path) -> Path:
    """Return a temporary directory for SQLite cache during tests."""
    cache_dir = tmp_path / "cache"
    cache_dir.mkdir()
    return cache_dir


@pytest.fixture
def temp_output_dir(tmp_path: Path) -> Path:
    """Return a temporary directory for digest output during tests."""
    output_dir = tmp_path / "digests"
    output_dir.mkdir()
    return output_dir
