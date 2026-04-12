"""Tests for radar/__main__.py — CLI entry point.

Verifies the CLI layer (issue #98):
- Contract: all subcommands registered; module invocable as `python -m radar`
- Happy path: `run` invokes Pipeline.run() and propagates its exit code
- Happy path: `run --date YYYY-MM-DD` parses and passes the date to the pipeline
- Happy path: `check` exits 0 on valid config
- Happy path: `auth gmail` calls the Gmail auth helper
- Happy path: `cache clear/stats/remove` call the appropriate Cache methods
- Failure modes: missing config, invalid date format, check failure, propagated LLM exit code 2,
  unknown subcommand
- Help: --help on each subcommand exits 0
"""

# 1. Standard library imports
import datetime
from pathlib import Path
from unittest.mock import MagicMock, patch

# 2. Third-party imports
from click.testing import CliRunner

# 3. Internal imports
from radar.__main__ import cli
from radar.pipeline import _EXIT_FATAL, _EXIT_PARTIAL, _EXIT_SUCCESS

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_VALID_CONFIG_YAML = """\
profile:
  role: "AI engineer"
  interests:
    - "AI"
sources:
  hackernews:
    enabled: true
    min_score: 50
"""

# ---------------------------------------------------------------------------
# Factories
# ---------------------------------------------------------------------------


def _config_file(tmp_path: Path) -> Path:
    """Write a minimal valid config.yaml to tmp_path and return its path."""
    f = tmp_path / "config.yaml"
    f.write_text(_VALID_CONFIG_YAML)
    return f


# ---------------------------------------------------------------------------
# Contract: subcommands registered
# ---------------------------------------------------------------------------


def test_cli_module_importable() -> None:
    """cli group is importable from radar.__main__."""
    assert cli is not None


def test_cli_run_subcommand_registered() -> None:
    runner = CliRunner()
    result = runner.invoke(cli, ["run", "--help"])
    assert "Usage" in result.output


def test_cli_check_subcommand_registered() -> None:
    runner = CliRunner()
    result = runner.invoke(cli, ["check", "--help"])
    assert "Usage" in result.output


def test_cli_auth_gmail_subcommand_registered() -> None:
    runner = CliRunner()
    result = runner.invoke(cli, ["auth", "gmail", "--help"])
    assert "Usage" in result.output


def test_cli_cache_clear_subcommand_registered() -> None:
    runner = CliRunner()
    result = runner.invoke(cli, ["cache", "clear", "--help"])
    assert "Usage" in result.output


def test_cli_cache_stats_subcommand_registered() -> None:
    runner = CliRunner()
    result = runner.invoke(cli, ["cache", "stats", "--help"])
    assert "Usage" in result.output


def test_cli_cache_remove_subcommand_registered() -> None:
    runner = CliRunner()
    result = runner.invoke(cli, ["cache", "remove", "--help"])
    assert "Usage" in result.output


# ---------------------------------------------------------------------------
# Happy path: `radar run` — exit code propagation
# ---------------------------------------------------------------------------


def test_cli_run_invokes_pipeline_run(tmp_path: Path) -> None:
    """radar run must call Pipeline.run()."""
    cfg = _config_file(tmp_path)
    mock_pipeline = MagicMock()
    mock_pipeline.run.return_value = _EXIT_SUCCESS
    with patch("radar.__main__.Pipeline", return_value=mock_pipeline):
        runner = CliRunner()
        runner.invoke(cli, ["--config", str(cfg), "run"])
    assert mock_pipeline.run.called


def test_cli_run_propagates_exit_code_0(tmp_path: Path) -> None:
    """radar run exits 0 when Pipeline.run() returns 0."""
    cfg = _config_file(tmp_path)
    mock_pipeline = MagicMock()
    mock_pipeline.run.return_value = _EXIT_SUCCESS
    with patch("radar.__main__.Pipeline", return_value=mock_pipeline):
        runner = CliRunner()
        result = runner.invoke(cli, ["--config", str(cfg), "run"])
    assert result.exit_code == _EXIT_SUCCESS


def test_cli_run_propagates_exit_code_1(tmp_path: Path) -> None:
    """radar run exits 1 when Pipeline.run() returns 1 (partial failure)."""
    cfg = _config_file(tmp_path)
    mock_pipeline = MagicMock()
    mock_pipeline.run.return_value = _EXIT_PARTIAL
    with patch("radar.__main__.Pipeline", return_value=mock_pipeline):
        runner = CliRunner()
        result = runner.invoke(cli, ["--config", str(cfg), "run"])
    assert result.exit_code == _EXIT_PARTIAL


def test_cli_run_propagates_exit_code_2(tmp_path: Path) -> None:
    """radar run exits 2 when Pipeline.run() returns 2 (fatal failure)."""
    cfg = _config_file(tmp_path)
    mock_pipeline = MagicMock()
    mock_pipeline.run.return_value = _EXIT_FATAL
    with patch("radar.__main__.Pipeline", return_value=mock_pipeline):
        runner = CliRunner()
        result = runner.invoke(cli, ["--config", str(cfg), "run"])
    assert result.exit_code == _EXIT_FATAL


# ---------------------------------------------------------------------------
# Happy path: `radar run --date`
# ---------------------------------------------------------------------------


def test_cli_run_with_date_flag_accepted(tmp_path: Path) -> None:
    """radar run --date YYYY-MM-DD is accepted without error."""
    cfg = _config_file(tmp_path)
    mock_pipeline = MagicMock()
    mock_pipeline.run.return_value = _EXIT_SUCCESS
    with patch("radar.__main__.Pipeline", return_value=mock_pipeline):
        runner = CliRunner()
        result = runner.invoke(cli, ["--config", str(cfg), "run", "--date", "2026-04-11"])
    assert result.exit_code == _EXIT_SUCCESS


def test_cli_run_with_date_flag_passes_date_to_pipeline(tmp_path: Path) -> None:
    """radar run --date 2026-04-11 passes datetime.date(2026, 4, 11) to pipeline.run()."""
    cfg = _config_file(tmp_path)
    mock_pipeline = MagicMock()
    mock_pipeline.run.return_value = _EXIT_SUCCESS
    with patch("radar.__main__.Pipeline", return_value=mock_pipeline):
        runner = CliRunner()
        runner.invoke(cli, ["--config", str(cfg), "run", "--date", "2026-04-11"])
    mock_pipeline.run.assert_called_once_with(run_date=datetime.date(2026, 4, 11))


def test_cli_run_without_date_calls_run_with_no_date(tmp_path: Path) -> None:
    """radar run without --date calls pipeline.run() with run_date=None."""
    cfg = _config_file(tmp_path)
    mock_pipeline = MagicMock()
    mock_pipeline.run.return_value = _EXIT_SUCCESS
    with patch("radar.__main__.Pipeline", return_value=mock_pipeline):
        runner = CliRunner()
        runner.invoke(cli, ["--config", str(cfg), "run"])
    mock_pipeline.run.assert_called_once_with(run_date=None)


# ---------------------------------------------------------------------------
# Happy path: `radar check`
# ---------------------------------------------------------------------------


def test_cli_check_valid_config_exits_0(tmp_path: Path) -> None:
    """radar check exits 0 when config is valid."""
    cfg = _config_file(tmp_path)
    runner = CliRunner()
    result = runner.invoke(cli, ["--config", str(cfg), "check"])
    assert result.exit_code == 0


# ---------------------------------------------------------------------------
# Happy path: `radar auth gmail`
# ---------------------------------------------------------------------------


def test_cli_auth_gmail_calls_auth_helper(tmp_path: Path) -> None:
    """radar auth gmail calls the Gmail auth helper function."""
    cfg = _config_file(tmp_path)
    with patch("radar.__main__._run_gmail_auth") as mock_auth:
        runner = CliRunner()
        runner.invoke(cli, ["--config", str(cfg), "auth", "gmail"])
    assert mock_auth.called


def test_cli_auth_gmail_exits_0_on_success(tmp_path: Path) -> None:
    """radar auth gmail exits 0 when auth completes without error."""
    cfg = _config_file(tmp_path)
    with patch("radar.__main__._run_gmail_auth"):
        runner = CliRunner()
        result = runner.invoke(cli, ["--config", str(cfg), "auth", "gmail"])
    assert result.exit_code == 0


# ---------------------------------------------------------------------------
# Happy path: `radar cache clear`
# ---------------------------------------------------------------------------


def test_cli_cache_clear_clears_cache(tmp_path: Path) -> None:
    """radar cache clear calls cache.clear_all()."""
    cfg = _config_file(tmp_path)
    mock_cache = MagicMock()
    with patch("radar.__main__.Cache", return_value=mock_cache):
        runner = CliRunner()
        runner.invoke(cli, ["--config", str(cfg), "cache", "clear"])
    assert mock_cache.clear_all.called


def test_cli_cache_clear_exits_0(tmp_path: Path) -> None:
    """radar cache clear exits 0 on success."""
    cfg = _config_file(tmp_path)
    mock_cache = MagicMock()
    with patch("radar.__main__.Cache", return_value=mock_cache):
        runner = CliRunner()
        result = runner.invoke(cli, ["--config", str(cfg), "cache", "clear"])
    assert result.exit_code == 0


# ---------------------------------------------------------------------------
# Happy path: `radar cache stats`
# ---------------------------------------------------------------------------


def test_cli_cache_stats_exits_0(tmp_path: Path) -> None:
    """radar cache stats exits 0 and prints output."""
    cfg = _config_file(tmp_path)
    mock_cache = MagicMock()
    mock_cache.stats.return_value = {
        "entry_count": 42,
        "oldest": "2026-01-01",
        "newest": "2026-04-11",
    }
    with patch("radar.__main__.Cache", return_value=mock_cache):
        runner = CliRunner()
        result = runner.invoke(cli, ["--config", str(cfg), "cache", "stats"])
    assert result.exit_code == 0


def test_cli_cache_stats_prints_entry_count(tmp_path: Path) -> None:
    """radar cache stats prints entry count to stdout."""
    cfg = _config_file(tmp_path)
    mock_cache = MagicMock()
    mock_cache.stats.return_value = {
        "entry_count": 42,
        "oldest": "2026-01-01",
        "newest": "2026-04-11",
    }
    with patch("radar.__main__.Cache", return_value=mock_cache):
        runner = CliRunner()
        result = runner.invoke(cli, ["--config", str(cfg), "cache", "stats"])
    assert "42" in result.output


# ---------------------------------------------------------------------------
# Happy path: `radar cache remove <url>`
# ---------------------------------------------------------------------------


def test_cli_cache_remove_url_calls_remove(tmp_path: Path) -> None:
    """radar cache remove <url> calls cache.remove_url(url)."""
    cfg = _config_file(tmp_path)
    mock_cache = MagicMock()
    mock_cache.remove_url.return_value = True
    with patch("radar.__main__.Cache", return_value=mock_cache):
        runner = CliRunner()
        runner.invoke(cli, ["--config", str(cfg), "cache", "remove", "https://example.com/article"])
    mock_cache.remove_url.assert_called_once_with("https://example.com/article")


def test_cli_cache_remove_url_exits_0(tmp_path: Path) -> None:
    """radar cache remove exits 0 when URL is found and removed."""
    cfg = _config_file(tmp_path)
    mock_cache = MagicMock()
    mock_cache.remove_url.return_value = True
    with patch("radar.__main__.Cache", return_value=mock_cache):
        runner = CliRunner()
        result = runner.invoke(
            cli, ["--config", str(cfg), "cache", "remove", "https://example.com/article"]
        )
    assert result.exit_code == 0


def test_cli_cache_remove_url_not_in_cache_exits_0(tmp_path: Path) -> None:
    """radar cache remove exits 0 even when the URL is not in the cache."""
    cfg = _config_file(tmp_path)
    mock_cache = MagicMock()
    mock_cache.remove_url.return_value = False  # URL not found
    with patch("radar.__main__.Cache", return_value=mock_cache):
        runner = CliRunner()
        result = runner.invoke(
            cli, ["--config", str(cfg), "cache", "remove", "https://example.com/not-there"]
        )
    assert result.exit_code == 0


# ---------------------------------------------------------------------------
# Failure modes
# ---------------------------------------------------------------------------


def test_cli_run_invalid_date_format_exits_nonzero(tmp_path: Path) -> None:
    """radar run --date with an invalid date string exits non-zero."""
    cfg = _config_file(tmp_path)
    runner = CliRunner()
    result = runner.invoke(cli, ["--config", str(cfg), "run", "--date", "not-a-date"])
    assert result.exit_code != 0


def test_cli_check_exits_nonzero_on_failure(tmp_path: Path) -> None:
    """radar check exits non-zero when any connectivity check fails."""
    cfg = _config_file(tmp_path)
    with patch("radar.__main__._run_check", return_value=1):
        runner = CliRunner()
        result = runner.invoke(cli, ["--config", str(cfg), "check"])
        assert result.exit_code != 0


def test_cli_run_passes_config_to_pipeline(tmp_path: Path) -> None:
    """radar run constructs Pipeline with the loaded config object."""
    cfg = _config_file(tmp_path)
    mock_pipeline = MagicMock()
    mock_pipeline.run.return_value = _EXIT_SUCCESS
    with patch("radar.__main__.Pipeline") as mock_cls:
        mock_cls.return_value = mock_pipeline
        runner = CliRunner()
        runner.invoke(cli, ["--config", str(cfg), "run"])
        mock_cls.assert_called_once()


def test_cli_run_missing_config_exits_nonzero(tmp_path: Path) -> None:
    """radar run with a missing config file exits non-zero."""
    runner = CliRunner()
    result = runner.invoke(cli, ["--config", str(tmp_path / "nonexistent.yaml"), "run"])
    assert result.exit_code != 0


def test_cli_unknown_subcommand_exits_nonzero() -> None:
    """An unrecognised subcommand exits non-zero."""
    runner = CliRunner()
    result = runner.invoke(cli, ["bogus-command"])
    assert result.exit_code != 0


# ---------------------------------------------------------------------------
# Help
# ---------------------------------------------------------------------------


def test_cli_help_exits_0() -> None:
    """radar --help exits 0."""
    runner = CliRunner()
    result = runner.invoke(cli, ["--help"])
    assert result.exit_code == 0


def test_cli_run_help_exits_0() -> None:
    """radar run --help exits 0."""
    runner = CliRunner()
    result = runner.invoke(cli, ["run", "--help"])
    assert result.exit_code == 0


def test_cli_check_help_exits_0() -> None:
    """radar check --help exits 0."""
    runner = CliRunner()
    result = runner.invoke(cli, ["check", "--help"])
    assert result.exit_code == 0


def test_cli_auth_gmail_help_exits_0() -> None:
    """radar auth gmail --help exits 0."""
    runner = CliRunner()
    result = runner.invoke(cli, ["auth", "gmail", "--help"])
    assert result.exit_code == 0


def test_cli_cache_clear_help_exits_0() -> None:
    """radar cache clear --help exits 0."""
    runner = CliRunner()
    result = runner.invoke(cli, ["cache", "clear", "--help"])
    assert result.exit_code == 0


def test_cli_cache_stats_help_exits_0() -> None:
    """radar cache stats --help exits 0."""
    runner = CliRunner()
    result = runner.invoke(cli, ["cache", "stats", "--help"])
    assert result.exit_code == 0


def test_cli_cache_remove_help_exits_0() -> None:
    """radar cache remove --help exits 0."""
    runner = CliRunner()
    result = runner.invoke(cli, ["cache", "remove", "--help"])
    assert result.exit_code == 0
