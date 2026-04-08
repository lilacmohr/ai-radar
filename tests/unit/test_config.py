"""Tests for radar/config.py — configuration loading and pydantic validation.

All tests in this file are expected to FAIL (red) until radar/config.py
is implemented. See paired [IMPL] issue #18.

Spec reference: SPEC.md §3.5 (configuration schema), §4.6 (config validation tests).
"""

from pathlib import Path

import pytest
from pydantic import ValidationError

from radar.config import Config, load_config

# ---------------------------------------------------------------------------
# YAML fixtures — written to tmp_path inside each test
# ---------------------------------------------------------------------------

MINIMAL_VALID_CONFIG = """\
profile:
  interests:
    - "LLM"

sources:
  hackernews:
    enabled: true
    min_score: 50
"""

FULL_VALID_CONFIG = """\
profile:
  role: "AI engineer and technical architect"
  interests:
    - "LLM inference and serving"
    - "agent frameworks and multi-agent systems"
  relevance_threshold: 6

sources:
  hackernews:
    enabled: true
    min_score: 50
    keywords:
      - "LLM"
      - "AI"
  arxiv:
    enabled: false
    categories: []
  rss_feeds:
    enabled: false
    feeds: []
  gmail:
    enabled: false
    labels: []
    max_age_days: 1
    newsletter_type: "link_list"
    senders: []

llm:
  backend: "github_models"

pipeline:
  max_words_excerpt: 200
  max_words_full: 800
  max_articles_to_summarize: 30
  max_articles_in_digest: 15
  batch_size: 10
  summarization_model: "gpt-4o-mini"
  synthesis_model: "gpt-4o"
  user_agent: "ai-radar/0.1"
  cache_ttl_days: 30
  max_cost_per_run: 0.10

output:
  format: "markdown"
  output_dir: "./digests"
  filename_pattern: "briefing_{date}.md"
  commit_digests: false
"""

# Expected defaults (defined as constants to avoid magic values in assertions)
DEFAULT_RELEVANCE_THRESHOLD = 6
DEFAULT_LLM_BACKEND = "github_models"


# ---------------------------------------------------------------------------
# Happy path — full config
# ---------------------------------------------------------------------------


def test_load_config_returns_config_object(tmp_path: Path) -> None:
    config_file = tmp_path / "config.yaml"
    config_file.write_text(FULL_VALID_CONFIG)
    config = load_config(config_file)
    assert isinstance(config, Config)


def test_full_valid_config_loads_without_error(tmp_path: Path) -> None:
    config_file = tmp_path / "config.yaml"
    config_file.write_text(FULL_VALID_CONFIG)
    # Should not raise
    load_config(config_file)


def test_profile_interests_is_list_of_str(tmp_path: Path) -> None:
    config_file = tmp_path / "config.yaml"
    config_file.write_text(FULL_VALID_CONFIG)
    config = load_config(config_file)
    assert isinstance(config.profile.interests, list)
    assert all(isinstance(item, str) for item in config.profile.interests)


def test_profile_interests_contains_expected_values(tmp_path: Path) -> None:
    config_file = tmp_path / "config.yaml"
    config_file.write_text(FULL_VALID_CONFIG)
    config = load_config(config_file)
    assert "LLM inference and serving" in config.profile.interests


def test_profile_relevance_threshold_is_int(tmp_path: Path) -> None:
    config_file = tmp_path / "config.yaml"
    config_file.write_text(FULL_VALID_CONFIG)
    config = load_config(config_file)
    assert isinstance(config.profile.relevance_threshold, int)


def test_hackernews_min_score_is_int(tmp_path: Path) -> None:
    config_file = tmp_path / "config.yaml"
    config_file.write_text(FULL_VALID_CONFIG)
    config = load_config(config_file)
    assert isinstance(config.sources.hackernews.min_score, int)


def test_gmail_enabled_is_bool(tmp_path: Path) -> None:
    config_file = tmp_path / "config.yaml"
    config_file.write_text(FULL_VALID_CONFIG)
    config = load_config(config_file)
    assert isinstance(config.sources.gmail.enabled, bool)


def test_pipeline_max_words_excerpt_is_int(tmp_path: Path) -> None:
    config_file = tmp_path / "config.yaml"
    config_file.write_text(FULL_VALID_CONFIG)
    config = load_config(config_file)
    assert isinstance(config.pipeline.max_words_excerpt, int)


def test_pipeline_max_words_full_is_int(tmp_path: Path) -> None:
    config_file = tmp_path / "config.yaml"
    config_file.write_text(FULL_VALID_CONFIG)
    config = load_config(config_file)
    assert isinstance(config.pipeline.max_words_full, int)


def test_pipeline_cache_ttl_days_is_int(tmp_path: Path) -> None:
    config_file = tmp_path / "config.yaml"
    config_file.write_text(FULL_VALID_CONFIG)
    config = load_config(config_file)
    assert isinstance(config.pipeline.cache_ttl_days, int)


def test_output_output_dir_is_str(tmp_path: Path) -> None:
    config_file = tmp_path / "config.yaml"
    config_file.write_text(FULL_VALID_CONFIG)
    config = load_config(config_file)
    assert isinstance(config.output.output_dir, str)


def test_llm_backend_value(tmp_path: Path) -> None:
    config_file = tmp_path / "config.yaml"
    config_file.write_text(FULL_VALID_CONFIG)
    config = load_config(config_file)
    assert config.llm.backend == DEFAULT_LLM_BACKEND


# ---------------------------------------------------------------------------
# Happy path — minimal config and defaults
# ---------------------------------------------------------------------------


def test_minimal_valid_config_loads_without_error(tmp_path: Path) -> None:
    """Config with only required fields must load — optional fields have defaults."""
    config_file = tmp_path / "config.yaml"
    config_file.write_text(MINIMAL_VALID_CONFIG)
    # Should not raise
    load_config(config_file)


def test_profile_relevance_threshold_defaults_to_6_when_not_specified(
    tmp_path: Path,
) -> None:
    """relevance_threshold defaults to 6 per SPEC.md §3.5."""
    config_file = tmp_path / "config.yaml"
    config_file.write_text(MINIMAL_VALID_CONFIG)
    config = load_config(config_file)
    assert config.profile.relevance_threshold == DEFAULT_RELEVANCE_THRESHOLD


def test_llm_backend_defaults_to_github_models_when_not_specified(
    tmp_path: Path,
) -> None:
    """llm.backend defaults to 'github_models' per SPEC.md §3.5."""
    config_file = tmp_path / "config.yaml"
    config_file.write_text(MINIMAL_VALID_CONFIG)
    config = load_config(config_file)
    assert config.llm.backend == DEFAULT_LLM_BACKEND


# ---------------------------------------------------------------------------
# Failure modes — invalid configs caught on load (SPEC.md §4.6)
# ---------------------------------------------------------------------------


def test_hackernews_min_score_is_required(tmp_path: Path) -> None:
    """sources.hackernews.min_score is required, not optional.

    An omitted min_score must raise ValidationError — it has no default because
    the right value is highly context-dependent (SPEC.md §3.1: 'tune after first runs').
    """
    config_file = tmp_path / "config.yaml"
    config_file.write_text(
        "profile:\n  interests:\n    - LLM\nsources:\n  hackernews:\n    enabled: true\n"
    )
    with pytest.raises(ValidationError, match="min_score"):
        load_config(config_file)


def test_load_config_raises_validation_error_on_missing_sources(
    tmp_path: Path,
) -> None:
    """Missing 'sources' key must raise ValidationError before pipeline runs."""
    config_file = tmp_path / "config.yaml"
    config_file.write_text("profile:\n  interests:\n    - LLM\n")
    with pytest.raises(ValidationError, match="sources"):
        load_config(config_file)


def test_load_config_raises_validation_error_on_wrong_type_for_min_score(
    tmp_path: Path,
) -> None:
    """String where int is expected must raise ValidationError on load."""
    config_file = tmp_path / "config.yaml"
    config_file.write_text(
        "profile:\n  interests:\n    - LLM\n"
        "sources:\n  hackernews:\n    enabled: true\n    min_score: fifty\n"
    )
    with pytest.raises(ValidationError, match="min_score"):
        load_config(config_file)


def test_load_config_raises_validation_error_on_threshold_above_range(
    tmp_path: Path,
) -> None:
    """relevance_threshold must be 1-10; value of 15 must raise ValidationError."""
    out_of_range_config = """\
profile:
  interests:
    - "LLM"
  relevance_threshold: 15

sources:
  hackernews:
    enabled: true
    min_score: 50
"""
    config_file = tmp_path / "config.yaml"
    config_file.write_text(out_of_range_config)
    with pytest.raises(ValidationError, match="relevance_threshold"):
        load_config(config_file)


def test_load_config_raises_validation_error_on_threshold_below_range(
    tmp_path: Path,
) -> None:
    """relevance_threshold must be 1-10; value of 0 must raise ValidationError."""
    out_of_range_config = """\
profile:
  interests:
    - "LLM"
  relevance_threshold: 0

sources:
  hackernews:
    enabled: true
    min_score: 50
"""
    config_file = tmp_path / "config.yaml"
    config_file.write_text(out_of_range_config)
    with pytest.raises(ValidationError, match="relevance_threshold"):
        load_config(config_file)


def test_load_config_raises_file_not_found_for_missing_file(
    tmp_path: Path,
) -> None:
    missing = tmp_path / "nonexistent.yaml"
    with pytest.raises(FileNotFoundError):
        load_config(missing)


def test_load_config_raises_on_empty_file(tmp_path: Path) -> None:
    """Empty config file must raise a descriptive error, not an unhandled exception."""
    config_file = tmp_path / "config.yaml"
    config_file.write_text("")
    with pytest.raises(Exception, match=r"."):
        load_config(config_file)


def test_load_config_raises_on_malformed_yaml(tmp_path: Path) -> None:
    """YAML syntax error must surface as a descriptive error."""
    config_file = tmp_path / "config.yaml"
    config_file.write_text("profile: {\n  unclosed brace\n")
    with pytest.raises(Exception, match=r"."):
        load_config(config_file)


def test_load_config_raises_on_empty_interests_list(tmp_path: Path) -> None:
    """interests: [] must raise ValidationError — an empty list makes the config meaningless."""
    config_file = tmp_path / "config.yaml"
    config_file.write_text("""\
profile:
  interests: []

sources:
  hackernews:
    enabled: true
    min_score: 50
""")
    with pytest.raises(ValidationError, match="interests"):
        load_config(config_file)


def test_load_config_raises_validation_error_on_unsupported_llm_backend(
    tmp_path: Path,
) -> None:
    """llm.backend='anthropic' is post-MVP; must raise ValidationError in v0.1."""
    config_file = tmp_path / "config.yaml"
    config_file.write_text(MINIMAL_VALID_CONFIG + "\nllm:\n  backend: anthropic\n")
    with pytest.raises(ValidationError, match="backend"):
        load_config(config_file)


# ---------------------------------------------------------------------------
# Public interface contract
# ---------------------------------------------------------------------------


def test_load_config_signature_accepts_path_object(tmp_path: Path) -> None:
    """load_config must accept a pathlib.Path (not just a string)."""
    config_file = tmp_path / "config.yaml"
    config_file.write_text(FULL_VALID_CONFIG)
    # Passing a Path object — not a string
    config = load_config(Path(config_file))
    assert isinstance(config, Config)


def test_config_is_importable_from_radar_config() -> None:
    """Config must be importable directly from radar.config."""
    # Import already happened at module level — just assert the type exists
    assert Config is not None


def test_load_config_is_importable_from_radar_config() -> None:
    """load_config must be importable from radar.config."""
    assert load_config is not None
