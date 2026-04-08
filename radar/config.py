"""Configuration loading and pydantic validation for ai-radar.

Loads config.yaml, validates the full schema on load, and returns a typed Config
object. Any missing required fields, wrong types, or out-of-range values raise
ValidationError before the pipeline starts — never at runtime.

Spec reference: SPEC.md §3.5 (configuration schema).
"""

# Standard library imports
from pathlib import Path
from typing import Annotated, Any, Literal

# Third-party imports
import structlog
import yaml
from pydantic import BaseModel, ConfigDict, Field

logger = structlog.get_logger(__name__)

__all__ = ["Config", "load_config"]


# ---------------------------------------------------------------------------
# Sub-models: profile
# ---------------------------------------------------------------------------


class ProfileConfig(BaseModel):
    """User profile: interests drive Pass 1 scoring and Pass 2 synthesis."""

    model_config = ConfigDict(extra="forbid")

    role: str | None = None
    interests: Annotated[list[str], Field(min_length=1)]
    relevance_threshold: Annotated[int, Field(ge=1, le=10)] = 6


# ---------------------------------------------------------------------------
# Sub-models: sources
# ---------------------------------------------------------------------------


class HackerNewsConfig(BaseModel):
    """Hacker News source connector config."""

    model_config = ConfigDict(extra="forbid")

    enabled: bool = False
    min_score: int  # required — no default; tune after first runs (SPEC.md §3.1)
    keywords: list[str] = []


class ArxivConfig(BaseModel):
    """ArXiv source connector config."""

    model_config = ConfigDict(extra="forbid")

    enabled: bool = False
    categories: list[str] = []


class RssFeedEntryConfig(BaseModel):
    """A single RSS/Atom feed entry."""

    model_config = ConfigDict(extra="forbid")

    name: str
    url: str


class RssFeedsConfig(BaseModel):
    """RSS/Atom feeds source connector config."""

    model_config = ConfigDict(extra="forbid")

    enabled: bool = False
    feeds: list[RssFeedEntryConfig] = []


class GmailSenderConfig(BaseModel):
    """A single Gmail sender filter entry."""

    model_config = ConfigDict(extra="forbid")

    name: str
    email: str


class GmailConfig(BaseModel):
    """Gmail source connector config."""

    model_config = ConfigDict(extra="forbid")

    enabled: bool = False
    labels: list[str] = []
    max_age_days: int = 1
    newsletter_type: str = "link_list"
    senders: list[GmailSenderConfig] = []


class SourcesConfig(BaseModel):
    """All source connector configs. All sources are optional (None = not configured).

    hackernews requires min_score when provided — it has no sensible default
    (SPEC.md §3.1: "tune after first runs"). pipeline.py must check for None
    before accessing any source config.
    """

    model_config = ConfigDict(extra="forbid")

    hackernews: HackerNewsConfig | None = None
    arxiv: ArxivConfig = Field(default_factory=ArxivConfig)
    rss_feeds: RssFeedsConfig = Field(default_factory=RssFeedsConfig)
    gmail: GmailConfig = Field(default_factory=GmailConfig)


# ---------------------------------------------------------------------------
# Sub-models: llm
# ---------------------------------------------------------------------------


class LLMConfig(BaseModel):
    """LLM backend config. Only github_models is supported in v0.1."""

    model_config = ConfigDict(extra="forbid")

    backend: Literal["github_models"] = "github_models"


# ---------------------------------------------------------------------------
# Sub-models: pipeline
# ---------------------------------------------------------------------------


class PipelineConfig(BaseModel):
    """Pipeline tuning parameters."""

    model_config = ConfigDict(extra="forbid")

    max_words_excerpt: int = 200
    max_words_full: int = 800
    max_articles_to_summarize: int = 30
    max_articles_in_digest: int = 15
    batch_size: int = 10
    summarization_model: str = "gpt-4o-mini"
    synthesis_model: str = "gpt-4o"
    user_agent: str = "ai-radar/0.1 (personal digest tool)"
    cache_ttl_days: int = 30
    max_cost_per_run: float = 0.10


# ---------------------------------------------------------------------------
# Sub-models: output
# ---------------------------------------------------------------------------


class OutputConfig(BaseModel):
    """Digest output config."""

    model_config = ConfigDict(extra="forbid")

    format: str = "markdown"
    output_dir: str = "./digests"
    filename_pattern: str = "briefing_{date}.md"
    commit_digests: bool = False


# ---------------------------------------------------------------------------
# Top-level Config
# ---------------------------------------------------------------------------


class Config(BaseModel):
    """Validated top-level configuration object.

    profile and sources are required. llm, pipeline, and output have defaults.
    """

    model_config = ConfigDict(extra="forbid")

    profile: ProfileConfig
    sources: SourcesConfig
    llm: LLMConfig = Field(default_factory=LLMConfig)
    pipeline: PipelineConfig = Field(default_factory=PipelineConfig)
    output: OutputConfig = Field(default_factory=OutputConfig)


# ---------------------------------------------------------------------------
# Public loader
# ---------------------------------------------------------------------------


def load_config(path: Path) -> Config:
    """Load and validate config.yaml from path.

    Raises:
        FileNotFoundError: if path does not exist.
        yaml.YAMLError: if the file is not valid YAML.
        ValidationError: if the config schema is invalid.
    """
    text = path.read_text(encoding="utf-8")
    data: Any = yaml.safe_load(text)
    config = Config.model_validate(data)
    logger.info("config_loaded", path=str(path))
    return config
