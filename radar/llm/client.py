"""LLM backend abstraction for ai-radar.

Wraps the GitHub Models OpenAI-compatible endpoint with exponential-backoff
retry logic. All outbound LLM calls go through this module.

Stub — implementation tracked in [IMPL] #72.
"""

import os  # noqa: F401
import time  # noqa: F401

import openai  # noqa: F401


class LLMClient:
    """GitHub Models LLM client with exponential-backoff retry.

    Reads GITHUB_MODELS_TOKEN from the environment on construction.
    """

    def __init__(self) -> None:
        raise NotImplementedError

    def complete(self, system: str, user: str, model: str) -> str:
        """Send a chat completion request and return the response text."""
        raise NotImplementedError
