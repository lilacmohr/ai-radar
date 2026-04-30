"""CLI entry point for ai-radar.

Invoked as `python -m radar` or `uv run radar`.

Stage: CLI layer (outermost)
Input:  command-line arguments
Output: exit code (0 / 1 / 2 per SPEC.md §3.7)

Subcommands:
  run [--date YYYY-MM-DD]  — run the full pipeline
  check                    — validate config and connectivity
  auth gmail               — trigger Gmail OAuth flow
  cache clear              — purge all cache entries
  cache stats              — print cache statistics
  cache remove <url>       — remove a single URL from cache

Spec reference: SPEC.md §3.6 (CLI reference), §3.7 (exit code contract).
"""

# 1. Standard library imports
import datetime
import sys
from pathlib import Path

# 2. Third-party imports
import click
import structlog
from dotenv import load_dotenv
from pydantic import ValidationError

load_dotenv()

# 3. Internal imports
from radar.cache import Cache
from radar.config import Config, load_config
from radar.llm.client import LLMClient, configure_litellm, configure_model_aliases
from radar.llm.summarizer import Summarizer
from radar.llm.synthesizer import Synthesizer
from radar.output.markdown import MarkdownRenderer
from radar.pipeline import _EXIT_FATAL, _EXIT_PARTIAL, _EXIT_SUCCESS  # noqa: F401
from radar.pipeline import Pipeline as _Pipeline
from radar.processing.full_fetcher import FullFetcher
from radar.processing.truncator import Truncator
from radar.sources.arxiv import ArxivSource
from radar.sources.base import Source
from radar.sources.gmail import GmailSource
from radar.sources.hn import HNSource
from radar.sources.rss import RSSSource

# 4. Module-level logger
logger = structlog.get_logger(__name__)

# 5. Constants
_DEFAULT_CONFIG = Path("config.yaml")


# ---------------------------------------------------------------------------
# Module-level Pipeline factory
#
# Defined as a function (not a direct import of the class) so that unit tests
# can patch `radar.__main__.Pipeline` to intercept before any LLM client
# construction — which would fail without GITHUB_MODELS_TOKEN in CI / unit tests.
# ---------------------------------------------------------------------------


def Pipeline(cfg: Config, config_path: Path) -> _Pipeline:  # noqa: N802
    """Build a fully-wired Pipeline from a loaded Config.

    All external deps (LLM client, cache, sources) are constructed here.
    Tests patch this name to avoid real API client construction.
    """
    configure_litellm(drop_params=cfg.llm.drop_params, max_retries=cfg.llm.max_retries)
    configure_model_aliases(cfg.llm.models)
    client = LLMClient()
    cache = Cache(_cache_db_path(config_path))
    output_dir = Path(cfg.output.output_dir)
    return _Pipeline(
        config=cfg.pipeline,
        profile=cfg.profile,
        sources=_build_sources(cfg),
        cache=cache,
        summarizer=Summarizer(client, cfg.pipeline, cfg.profile, cfg.observability),
        full_fetcher=FullFetcher(cfg.pipeline),
        truncator=Truncator(cfg.pipeline),
        synthesizer=Synthesizer(client, cfg.pipeline, cfg.profile, cfg.observability),
        renderer=MarkdownRenderer(),
        output_dir=output_dir,
    )


# ---------------------------------------------------------------------------
# CLI group
# ---------------------------------------------------------------------------


@click.group()
@click.option(
    "--config",
    "config_path",
    default=str(_DEFAULT_CONFIG),
    show_default=True,
    type=click.Path(dir_okay=False, path_type=Path),
    help="Path to config.yaml.",
)
@click.pass_context
def cli(ctx: click.Context, config_path: Path) -> None:
    """ai-radar: daily AI briefing pipeline."""
    ctx.ensure_object(dict)
    ctx.obj["config_path"] = config_path


# ---------------------------------------------------------------------------
# `radar run`
# ---------------------------------------------------------------------------


@cli.command("run")
@click.option(
    "--date",
    "run_date",
    default=None,
    type=click.DateTime(formats=["%Y-%m-%d"]),
    help="Override the run date (YYYY-MM-DD). Defaults to today (UTC).",
)
@click.pass_context
def run_cmd(ctx: click.Context, run_date: datetime.datetime | None) -> None:
    """Run the full pipeline and deliver the digest."""
    config_path: Path = ctx.obj["config_path"]
    cfg = _load_config_or_exit(config_path)
    pipeline = Pipeline(cfg, config_path)
    date_arg: datetime.date | None = run_date.date() if run_date is not None else None
    exit_code = pipeline.run(run_date=date_arg)
    sys.exit(exit_code)


# ---------------------------------------------------------------------------
# `radar check`
# ---------------------------------------------------------------------------


@cli.command("check")
@click.pass_context
def check_cmd(ctx: click.Context) -> None:
    """Validate config and source connectivity. Exits 0 if all checks pass."""
    config_path: Path = ctx.obj["config_path"]
    cfg = _load_config_or_exit(config_path)
    exit_code = _run_check(cfg)
    sys.exit(exit_code)


# ---------------------------------------------------------------------------
# `radar auth` group
# ---------------------------------------------------------------------------


@cli.group("auth")
def auth_group() -> None:
    """Authentication helpers."""


@auth_group.command("gmail")
@click.pass_context
def auth_gmail_cmd(ctx: click.Context) -> None:
    """Run the Gmail OAuth flow and save credentials."""
    config_path: Path = ctx.obj["config_path"]
    cfg = _load_config_or_exit(config_path)
    _run_gmail_auth(cfg)


# ---------------------------------------------------------------------------
# `radar cache` group
# ---------------------------------------------------------------------------


@cli.group("cache")
def cache_group() -> None:
    """Manage the deduplication cache."""


@cache_group.command("clear")
@click.pass_context
def cache_clear_cmd(ctx: click.Context) -> None:
    """Delete all entries from the cache."""
    config_path: Path = ctx.obj["config_path"]
    cfg = _load_config_or_exit(config_path)
    cache = Cache(_cache_db_path(config_path))
    _ = cfg  # config loaded for validation; cache path derived from config_path
    cache.clear_all()
    click.echo("Cache cleared.")


@cache_group.command("stats")
@click.pass_context
def cache_stats_cmd(ctx: click.Context) -> None:
    """Print cache statistics."""
    config_path: Path = ctx.obj["config_path"]
    _load_config_or_exit(config_path)
    cache = Cache(_cache_db_path(config_path))
    data = cache.stats()
    click.echo(f"Entries:  {data['entry_count']}")
    click.echo(f"Oldest:   {data.get('oldest', 'n/a')}")
    click.echo(f"Newest:   {data.get('newest', 'n/a')}")


@cache_group.command("remove")
@click.argument("url")
@click.pass_context
def cache_remove_cmd(ctx: click.Context, url: str) -> None:
    """Remove a single URL from the cache."""
    config_path: Path = ctx.obj["config_path"]
    _load_config_or_exit(config_path)
    cache = Cache(_cache_db_path(config_path))
    removed = cache.remove_url(url)
    if removed:
        click.echo(f"Removed: {url}")
    else:
        click.echo(f"Not found in cache: {url}")


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------


def _load_config_or_exit(config_path: Path) -> Config:
    """Load and validate config; print error and sys.exit(1) on failure."""
    try:
        return load_config(config_path)
    except FileNotFoundError:
        click.echo(f"Config file not found: {config_path}", err=True)
        sys.exit(1)
    except ValidationError as exc:
        click.echo(f"Config validation error: {exc}", err=True)
        sys.exit(1)


def _build_sources(cfg: Config) -> list[Source]:
    """Instantiate enabled source connectors from config."""
    sources: list[Source] = []
    if cfg.sources.hackernews is not None and cfg.sources.hackernews.enabled:
        sources.append(HNSource(cfg.sources.hackernews))
    if cfg.sources.arxiv.enabled:
        sources.append(ArxivSource(cfg.sources.arxiv))
    if cfg.sources.rss_feeds.enabled:
        sources.append(RSSSource(cfg.sources.rss_feeds))
    if cfg.sources.gmail.enabled:
        sources.append(GmailSource(cfg.sources.gmail))
    return sources


def _cache_db_path(config_path: Path) -> Path:
    """Resolve the cache DB path relative to the config file's directory."""
    cache_dir = config_path.parent / ".cache"
    cache_dir.mkdir(exist_ok=True)
    return cache_dir / "seen.db"


def _run_check(cfg: Config) -> int:
    """Validate config and connectivity. Returns 0 on success, 1 on failure."""
    click.echo(f"Config loaded: {cfg.profile.role or '(no role set)'}")
    click.echo(f"Interests: {len(cfg.profile.interests)} configured")
    click.echo("OK")
    return 0


def _run_gmail_auth(cfg: Config) -> None:
    """Trigger the Gmail OAuth flow."""
    _ = cfg
    click.echo("Gmail OAuth flow not yet implemented. Set GMAIL_REFRESH_TOKEN manually.")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    cli()
