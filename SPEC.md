# ai-radar — Product & Technical Specification

**Version:** 0.3 (MVP — Open Questions Resolved)
**Status:** Draft
**Last Updated:** 2026-04-05

---

## 1. Overview

### 1.1 Problem Statement

AI professionals need to stay current on a rapidly evolving landscape spanning research papers, company announcements, tooling releases, and community discourse. Manually reading newsletters, blogs, and social feeds is time-consuming and produces inconsistent signal quality. Most summaries reflect mainstream interpretations, missing non-obvious insights or contrarian perspectives that are often more valuable.

### 1.2 Solution

`ai-radar` is a configurable Python pipeline that ingests AI content from multiple sources daily, filters and ranks it for relevance to the user's role and interests, and produces a richly structured digest. The digest includes not just summaries but contrarian takes, suggested follow-up questions, and cross-source trend detection — designed to surface signal that other tools miss.

### 1.3 Goals

| Goal | Priority |
|---|---|
| Personal daily AI briefing with minimal manual effort | P0 |
| Open-source tool reusable by others via fork + config | P0 |
| Demonstrate agentic development workflow patterns | P0 |
| Pluggable architecture for sources and LLM backends | P1 |
| Blog auto-publish from digest content | Post-MVP |

### 1.4 Non-Goals (MVP)

- Real-time or sub-daily ingestion
- Multi-user SaaS platform
- Blog auto-publish / content syndication
- Fine-tuned models or custom embeddings
- Mobile app or browser extension

---

## 2. User Personas

### Primary: The AI Practitioner
An engineer, researcher, or technical leader building on or with AI systems. Reads across roles: researcher (papers, benchmarks), engineer (tooling, APIs, frameworks), architect (patterns, tradeoffs), and product builder (capabilities, releases). Wants depth, not just headlines. Values non-obvious insights over mainstream takes. Has limited time but high standards for signal quality.

### Secondary: Open-Source Adopter
A developer who discovers `ai-radar` on GitHub and wants to run their own instance. Has some technical ability (can set up API keys, run Python), but needs good documentation. May have different role/interests than the primary user — expects easy configuration without code changes.

---

## 3. Functional Requirements

### 3.1 Source Ingestion

The pipeline must support the following source types. Each source type is a pluggable connector module.

| Source Type | Connector | Notes |
|---|---|---|
| Gmail newsletters | Gmail API (OAuth) | Reads unread emails from configured labels/senders. v0.1 supports link-list newsletters only (extracts URLs from email body). Full-content newsletter processing is post-MVP. Default `config.example.yaml` includes TLDR AI and The Batch as example link-list senders. Verify sender email addresses before use. |
| RSS/Atom feeds | `feedparser` | Company blogs, ArXiv, HN, research labs |
| Web scraping | `trafilatura` + `requests` | For URLs extracted from emails or feeds |
| ArXiv | ArXiv API + RSS | Filter by category (cs.AI, cs.LG, cs.CL, etc.). Abstracts only for MVP; full paper ingestion is post-MVP. |
| Hacker News | HN Algolia API | Filter by keyword, score threshold. Note: scores are time-sensitive — a post 2 hours old with 50 points may reach 200 by end of day. Consider extending lookback to 24–48 hours to let scores stabilize. |
| Podcast transcripts | RSS + transcript fetch | Where transcripts are available in feed (post-MVP, not yet implemented) |

All connectors must implement a common `Source` interface:
```python
class Source:
    def fetch(self) -> list[RawItem]
    def name(self) -> str
    def is_enabled(self) -> bool
```

#### Gmail OAuth Setup

The Gmail connector requires OAuth credentials. For local development, the standard OAuth desktop flow is used. For GitHub Actions (the primary deployment mode), a refresh token is stored as a GitHub Secret:

1. **Initial local auth flow:** Run `python -m radar auth gmail` to open a browser-based OAuth consent flow. The command outputs the refresh token for storage as a GitHub Secret.
2. **Storage:** Store the refresh token as the `GMAIL_REFRESH_TOKEN` GitHub Secret.
3. **Token expiry handling:** The pipeline must detect token expiry and exit with a descriptive error (e.g., `"Gmail refresh token expired. Re-run 'python -m radar auth gmail' and update the GMAIL_REFRESH_TOKEN secret."`), not a generic API failure or silent skip.
4. **GCP OAuth app mode:**
   - **Testing mode (default):** Refresh tokens expire in 7 days. Suitable for initial
     development. The pipeline detects expiry and emits a clear error message with
     re-auth instructions.
   - **Production mode:** Refresh tokens expire after 6 months of non-use. Requires
     Google OAuth app verification (privacy policy URL, domain verification, and Google
     review). See: https://support.google.com/cloud/answer/9110914
   - **Recommendation:** Begin with testing mode. Run `python -m radar auth gmail` to
     re-auth when the token expires. Pursue production mode verification once the
     pipeline is stable and running reliably.

#### Data Models

All shared data models are defined in `models.py`:

```python
@dataclass
class RawItem:
    url: str                  # canonical URL
    title: str                # article or email subject title
    source: str               # connector name (e.g. "gmail", "arxiv")
    published_at: datetime    # publication or receipt timestamp
    raw_content: str          # raw HTML or text as fetched
    content_type: str         # "email" | "web" | "arxiv"

@dataclass
class NormalizedItem:
    url: str
    title: str
    source: str
    published_at: datetime
    clean_text: str           # boilerplate-stripped text
    word_count: int
    url_hash: str             # SHA-256 of normalized URL
    content_hash: str         # SHA-256 of clean_text

# Note: NormalizedItem is used internally by the Excerpt Fetcher and Full Article Fetcher
# as an intermediate processing step (after boilerplate removal, before trimming to excerpt
# or full length). It is not passed between pipeline stages directly.

@dataclass
class ExcerptItem:
    url: str
    title: str
    source: str
    published_at: datetime
    excerpt: str              # title + first ~200 words
    url_hash: str
    content_hash: str         # SHA-256 of excerpt, for Phase 2 dedup

@dataclass
class ScoredItem:
    url: str
    title: str
    source: str
    published_at: datetime
    excerpt: str
    score: int                # 1-10 relevance score from Pass 1
    summary: str              # 2-3 sentence summary from Pass 1

@dataclass
class FullItem:
    url: str
    title: str
    source: str
    published_at: datetime
    full_text: str            # boilerplate-stripped text, capped at max_words_full
    word_count: int
    score: int                # carried over from Pass 1
    summary: str              # carried over from Pass 1

@dataclass
class Digest:
    date: date
    articles: list[ScoredItem]
    executive_summary: str
    contrarian_insights: str
    follow_up_questions: str
    trending_themes: str
    source_stats: dict        # counts per source, filter stats, model names, run duration
```

### 3.2 Preprocessing Pipeline (Python, Deterministic)

All steps before LLM calls must be deterministic Python with no API cost:

1. **Fetch** — pull raw content from each enabled source
2. **Deduplicate (Phase 1 — URL hash)** — normalize URLs (strip tracking parameters, follow redirects to canonical URL), compute SHA-256 of the normalized URL, skip items whose URL hash exists in the cache
3. **Extract URLs** — for Gmail sources, extract linked URLs from the email body (not text extraction from the email itself). Prefer HTML MIME part, fall back to plain text. Emails are marked as read after successful processing. Each extracted URL is treated as an independent article candidate.
4. **Extract Excerpt** — fetch title + first ~200 words per linked URL for Pass 1 input. Boilerplate removal is handled internally by the excerpt fetcher using `trafilatura`. For ArXiv sources, the abstract text is used directly as the excerpt (it is already available from the ArXiv API response). The Excerpt Fetcher web fetch step is bypassed for ArXiv items — no URL fetch required.
5. **Deduplicate (Phase 2 — Content hash)** — compute SHA-256 of `excerpt` text after boilerplate removal. Skip items whose content hash exists in the cache. This catches the same article published at different URLs.
6. **Pre-filter** — case-insensitive substring match against the user's `interests` list. Fields searched: title + excerpt (~200 words). An article passes if ANY keyword from the `interests` list matches. Example: interest `"LLM inference"` matches articles containing `"llm inference"`, `"LLM Inference"`, `"LLM inference and serving"`, etc.

Note: ~750 words ≈ 1,000 tokens at average English text density. All length limits in this spec use words, not tokens.

### 3.3 LLM Processing Pipeline

Two sequential LLM passes, each independently configurable:

**Pass 1: Summarization**
- Input: batch of excerpt items (~200 words each, up to `batch_size` per call, configurable)
- Task: relevance score (1–10 against user role/interests) + 2–3 sentence summary per article
- Output: ranked, summarized article list
- Model: `gpt-4o-mini` (via GitHub Models)
- Articles below relevance threshold (configurable, default: 6) are dropped

**Pass 1 response schema (JSON mode / structured output enforced):**
```json
[
  {
    "url": "string",
    "score": "integer (1-10)",
    "summary": "string (2-3 sentences)"
  }
]
```

**Pass 1 contract:**
- Parsing responsibility is assigned to `Summarizer`, not `LLMClient`
- Pass 1 must use JSON mode / structured output to enforce schema compliance
- On malformed output: retry once with an explicit JSON instruction; on second failure, skip the batch and log a warning
- Pass 1 must validate that every input URL appears in the output; missing URLs are treated as score 0 (dropped) and logged
- Batching tradeoff: `batch_size: 10` is cheaper but LLMs frequently drop items from the middle of large batches — this is a known limitation to monitor

**Pass 2: Synthesis & Insight**
- Input: **full article text** (not summaries) for the top `max_articles_in_digest` articles from Pass 1. Each article is capped at `max_words_full` words before being passed to Pass 2.
- Task: generate all digest sections (see 3.4)
- Output: structured markdown digest
- Model: `gpt-4o` (via GitHub Models)
- This pass receives the user's full role/interest profile as system context
- Context budget: 15 articles × 800 words ≈ 12,000 words ≈ 16,000 tokens — fits within `gpt-4o`'s context window but should be monitored
- If total input approaches the model's context limit: truncate the article list to fit (fewest-scored articles removed first), log a warning

**LLM Data Privacy:**
- Article content extracted from linked URLs is sent to the configured LLM provider for summarization and synthesis
- Default backend (GitHub Models) routes requests through Microsoft Azure infrastructure
- See Section 6 for full data privacy disclosure

**Startup validation:** On launch, the pipeline must verify that the configured model name is valid for the configured backend and fail with a clear error if not.

### 3.4 Digest Output Format

The final digest is a structured markdown file with the following sections, in order:

```markdown
# ai-radar Daily Briefing — {DATE}

## 📡 Executive Summary
3–5 bullet points covering the most important developments of the day.

## 📰 Article Summaries
For each top article:
- **Title** — [Source](url)
- Summary (2–3 sentences)
- Relevance score and why it matters to your role

## 🔍 Contrarian & Non-Obvious Insights
What is the mainstream narrative on today's top stories — and what might people be missing, underweighting, or misinterpreting? 3–5 observations.

## ❓ Follow-Up Questions & Rabbit Holes
5–10 questions or threads worth investigating further, ranked by potential insight value.

## 📈 Trending Themes
Patterns detected across today's sources: emerging topics, recurring themes, trajectory shifts. Distinct from individual article summaries.

## 📊 Pipeline Metadata
- Sources: {n} fetched, {n} after dedup, {n} after filter
- Articles: {n} scored, {n} in digest
- Models: {summarization_model} (Pass 1), {synthesis_model} (Pass 2)
- Run time: {duration}s

---
*Generated by ai-radar on {date}. Content summarized by AI from linked sources — always verify claims against originals.*
```

Note: `output/markdown.py` renders the Pipeline Metadata section and the disclosure footer with correct date substitution.

### 3.5 Configuration

**`config.yaml`** — checked into repo (no secrets):
```yaml
profile:
  role: "AI engineer and technical architect"
  interests:
    - "LLM inference and serving"
    - "agent frameworks and multi-agent systems"
    - "AI safety and alignment research"
    - "open-source models"
    - "developer tooling for AI"
  relevance_threshold: 6  # TBD — tune after first runs; articles below this score are dropped

sources:
  gmail:
    enabled: true
    labels: ["newsletters", "AI"]
    max_age_days: 1
    newsletter_type: "link_list"  # only supported type in v0.1; full_content is post-MVP
    senders:                      # filter to specific newsletter senders; leave empty to process all emails in label
      - name: "TLDR AI"
        email: "dan@tldr.tech"    # verify before use — sender addresses can change
      - name: "The Batch"
        email: "thebatch@deeplearning.ai"  # verify before use — sender addresses can change
  arxiv:
    enabled: true
    categories: ["cs.AI", "cs.LG", "cs.CL", "cs.MA"]
    max_results: 20  # TBD — tune after first runs
  rss_feeds:
    enabled: true
    feeds:
      - name: "Anthropic Blog"
        url: "https://www.anthropic.com/blog/rss"
      - name: "OpenAI Blog"
        url: "https://openai.com/blog/rss"
      - name: "Google DeepMind"
        url: "https://deepmind.google/blog/rss"
  hackernews:
    enabled: true
    min_score: 50  # Domain Expert recommendation — quality posts often score 50-80. Tune after first runs.
    keywords: ["LLM", "AI", "machine learning", "agent"]
  podcasts:
    enabled: false  # post-MVP, not yet implemented

llm:
  backend: "github_models"  # only supported backend in v0.1; openai and anthropic are post-MVP
  # Review your LLM provider's data processing terms before use with sensitive content

pipeline:
  max_words_excerpt: 200      # for Pass 1 input (words, not tokens; ~275 tokens at average density)
  max_words_full: 800         # for Pass 2 input (words, not tokens; ~1100 tokens at average density)
  max_articles_to_summarize: 30  # TBD — tune after first runs; caps Pass 1 input
  max_articles_in_digest: 15     # TBD — tune after first runs; caps Pass 2 input
  batch_size: 10           # TBD — 10 articles/call is cheaper but less reliable than 1/call; tune after first runs
  summarization_model: "gpt-4o-mini"  # GitHub Models identifier
  synthesis_model: "gpt-4o"           # GitHub Models identifier
  user_agent: "ai-radar/0.1 (personal digest tool)"
  cache_ttl_days: 30  # items older than this are removed from cache on each run
  max_cost_per_run: 0.10  # optional hard limit in USD; pipeline aborts if exceeded. Set to 0 to disable.

output:
  format: "markdown"
  output_dir: "./digests"
  filename_pattern: "briefing_{date}.md"
  commit_digests: false  # if true, commit digests to repo; default is false (artifacts only)
```

**`.env`** — secrets only, never committed:
```
GITHUB_MODELS_TOKEN=...       # Fine-grained personal access token; requires Account permissions > Models: Read-only
GMAIL_CLIENT_ID=...           # OAuth client ID from GCP console
GMAIL_CLIENT_SECRET=...       # OAuth client secret from GCP console
GMAIL_REFRESH_TOKEN=...       # Generated via: python -m radar auth gmail
# OPENAI_API_KEY=...          # Post-MVP: direct OpenAI API access
# ANTHROPIC_API_KEY=...       # Post-MVP: Anthropic Claude API access
```

### 3.6 Trigger Modes

The pipeline must support all three trigger modes without code changes. GitHub Actions is the primary trigger mode; manual and cron are alternatives.

| Mode | Mechanism |
|---|---|
| Manual | `python -m radar run` |
| Scheduled local | cron: `0 7 * * * python -m radar run` |
| GitHub Actions (primary) | `.github/workflows/daily-briefing.yml` on schedule |

GitHub Actions mode writes the digest as a workflow artifact and optionally commits it to a `digests/` folder in the repo (controlled by `commit_digests` config). GitHub Actions natively emails the repo owner on workflow failure — no additional notification config required.

#### GitHub Actions Setup

**Required secrets:**

| Secret | Source | Description |
|---|---|---|
| `GITHUB_MODELS_TOKEN` | Manually configured | Personal access token for GitHub Models API. **Not** the Actions-provided `GITHUB_TOKEN`. |
| `GMAIL_CLIENT_ID` | Manually configured | OAuth client ID from GCP console |
| `GMAIL_CLIENT_SECRET` | Manually configured | OAuth client secret from GCP console |
| `GMAIL_REFRESH_TOKEN` | Manually configured | Generated via `python -m radar auth gmail` |

Note: `GITHUB_TOKEN` is auto-injected by GitHub Actions and provides repository access. It must not be confused with `GITHUB_MODELS_TOKEN`, which is a separate personal access token for the GitHub Models LLM API.

**Workflow permissions (principle of least privilege):**
- Default: `contents: read`
- When `commit_digests: true`: `contents: write` (needed to push digest commits)

**Failure notification:** GitHub natively emails the repo owner on workflow failure — no additional config required.

#### Cache Persistence in GitHub Actions

GitHub Actions runners are ephemeral — `cache/radar.db` does not persist between runs by default, silently breaking deduplication. Resolve this using the `actions/cache` action to persist the cache directory between runs. Add the following steps to `.github/workflows/daily-briefing.yml`:

```yaml
- name: Restore cache
  uses: actions/cache@v4
  with:
    path: cache/
    key: radar-cache-${{ runner.os }}-${{ github.run_id }}
    restore-keys: radar-cache-${{ runner.os }}-

- name: Run pipeline
  run: python -m radar run

- name: Save cache
  if: always()
  uses: actions/cache/save@v4
  with:
    path: cache/
    key: radar-cache-${{ runner.os }}-${{ github.run_id }}
```

Note: `actions/cache` treats keys as immutable — a static key would freeze the DB after the first run. The `run_id` suffix ensures each run saves an updated cache. `restore-keys` with the OS prefix ensures the latest prior cache is restored even though keys differ. The save step uses `actions/cache/save` with `if: always()` to persist the cache even if the pipeline step fails.

**Cache miss behavior:** If the cache is not found (first run, or cache evicted by GitHub's 7-day retention policy for unused caches), the pipeline runs without dedup history. All articles are processed as new. This is safe — the pipeline is idempotent and produces a valid digest. The next run will populate the cache normally.

**Retention note:** GitHub Actions cache has a 10GB limit per repo and a 7-day retention policy for unused caches. For a daily pipeline producing a small SQLite file, neither limit will be reached in practice.

#### CLI Reference

| Command | Description |
|---|---|
| `python -m radar run` | Run the full pipeline |
| `python -m radar check` | Validate config, test credentials for each enabled source, fetch one item per source without LLM calls. Exit 0 if all checks pass, non-zero if any fail, with clear per-check output. Critical for first-run experience and post-change verification. |
| `python -m radar auth gmail` | Run the local OAuth flow and output the refresh token for storage as a GitHub Secret |
| `python -m radar cache clear` | Delete all cache entries (safe; causes full reprocess on next run) |
| `python -m radar cache stats` | Show cache size, entry count, oldest/newest entry |
| `python -m radar cache remove <url>` | Remove a specific URL to force reprocessing |

### 3.7 Failure Handling

#### Source fetch failures
- Log and skip the failed source; pipeline continues with remaining sources
- Never abort the full pipeline on a single source failure
- If ALL sources fail: exit code 2 (fatal), write failure-digest file

#### Paywalled or unextractable articles
- If `trafilatura` returns empty or below-minimum-length content (< 50 words) after fetching a URL, treat as a likely paywall or extraction failure
- Log the URL and reason at INFO level
- Skip the article from further processing
- Flag in the Pipeline Metadata section of the digest: "N articles skipped (paywall or extraction failure)"
- Do not abort the pipeline

#### LLM parse failures (Pass 1)
- Validate output against schema
- Retry once with explicit JSON instruction
- On second failure: skip the batch, log warning, continue with remaining batches

#### LLM API errors (429, 5xx, timeout)
- Exponential backoff, max 3 retries
- After exhaustion: log error, fail loudly (not silently)

#### Zero qualifying articles
- Write a minimal digest: "No notable content found today."
- Exit code 0 (not a failure)

#### Fatal conditions (all sources failed OR synthesis model unreachable)
- Exit code 2
- Write failure-digest file
- Clear, descriptive error message in logs

#### Cache behavior on partial failure
- Items are marked "seen" only AFTER successful digest generation, not at fetch time
- This ensures re-running after a failure reprocesses all articles safely
- `python -m radar run` must be safe to re-run after any failure (idempotent)

#### Exit code contract
- `0` = success (including zero-article "no content today" digests)
- `1` = partial failure (some sources failed, digest still generated)
- `2` = fatal (no digest generated)

#### Failure-digest file content
```
# ai-radar — Pipeline Failed {DATE}

The pipeline encountered an error and could not generate today's briefing.
Exit code: {exit_code}
Check GitHub Actions logs (or local logs) for details.
```

---

## 4. Technical Architecture

### 4.1 Repository Structure

```
ai-radar/
├── README.md
├── SPEC.md
├── AGENTS.md                # Documents the agentic development workflow and AI reviewer
│                            # protocol used to build this project. A reusable pattern for
│                            # AI-assisted software development.
├── config.yaml              # user configuration (committed)
├── config.example.yaml      # template for new users
├── .env.example             # secrets template (includes minimum required scopes per secret)
├── pyproject.toml           # primary install method: pip install -e .
├── requirements.txt         # generated from pyproject.toml for environments that require it
├── .github/
│   └── workflows/
│       ├── daily-briefing.yml
│       └── tests.yml        # runs pytest on every push and PR; all external calls mocked
├── radar/
│   ├── __init__.py
│   ├── __main__.py          # entry point: python -m radar run
│   ├── config.py            # config loading and validation
│   ├── models.py            # shared data models (RawItem, ExcerptItem, ScoredItem, FullItem, Digest)
│   ├── cache.py             # URL/content deduplication (SQLite)
│   ├── pipeline.py          # orchestrates all stages
│   ├── sources/
│   │   ├── __init__.py
│   │   ├── base.py          # Source ABC
│   │   ├── gmail.py
│   │   ├── arxiv.py
│   │   ├── rss.py
│   │   ├── hackernews.py
│   │   └── podcasts.py      # post-MVP, not yet implemented
│   ├── processing/
│   │   ├── __init__.py
│   │   ├── extractor.py     # trafilatura wrapper
│   │   ├── deduplicator.py
│   │   ├── prefilter.py     # keyword pre-filter
│   │   ├── truncator.py
│   │   ├── excerpt_fetcher.py  # fetches title + first ~200 words per URL for Pass 1 input
│   │   └── full_fetcher.py     # fetches complete article text for Pass 1 survivors only
│   ├── llm/
│   │   ├── __init__.py
│   │   ├── client.py        # LLM backend abstraction
│   │   ├── summarizer.py    # Pass 1
│   │   ├── synthesizer.py   # Pass 2
│   │   └── prompts.py       # all prompt templates
│   └── output/
│       ├── __init__.py
│       └── markdown.py      # digest renderer (includes pipeline metadata and disclosure footer)
├── digests/                 # generated output (gitignored or committed via commit_digests)
├── cache/                   # SQLite dedup cache (gitignored, auto-created on first run)
├── examples/
│   └── sample-briefing.md   # realistic example digest showing all sections with plausible content
└── tests/
    ├── conftest.py          # shared fixtures: TestLLMClient, temp cache dir, temp output dir
    ├── fixtures/            # one fixture file per source type: Gmail HTML, ArXiv response,
    │                        # HN response, sample web article HTML
    ├── test_sources.py
    ├── test_processing.py
    ├── test_llm.py          # LLM contract tests: schema validation, parse failure handling
    ├── test_pipeline.py     # integration test: full pipeline with all external calls mocked
    └── test_config.py       # config validation tests: confirm bad configs are caught on load
```

### 4.2 Data Flow

```
[Sources] → fetch() → [RawItem list]
    ↓
[Deduplicator] → URL hash check (pre-fetch) → [filtered RawItem list]
    ↓
[URL Extractor] → extract linked URLs from newsletter emails → [URL list]
    ↓
[Excerpt Fetcher] → fetch title + ~200 words per URL → [ExcerptItem list]
    ↓
[Deduplicator] → content hash check (post-fetch) → [deduplicated ExcerptItem list]
    ↓
[PreFilter] → case-insensitive keyword match against interests → [candidate list]
    ↓
[Summarizer - LLM Pass 1] → relevance score on excerpts → [ScoredItem list]
    ↓
[Relevance Filter] → drop below threshold → [top N items]
    ↓
[Full Article Fetcher] → fetch complete text for survivors only → [FullItem list]
    ↓
[Truncator] → cap at max_words_full → [ready for LLM Pass 2]
    ↓
[Synthesizer - LLM Pass 2] → full digest sections → [Digest object]
    ↓
[MarkdownRenderer] → write to file → [briefing_{date}.md]
```

### 4.3 LLM Backend Abstraction

The `llm/client.py` module abstracts the LLM backend so additional providers can be added post-MVP:

```python
class LLMClient:
    def complete(self, system: str, user: str, model: str) -> str
```

**v0.1 backend:**
- **GitHub Models** (default and only supported backend) — OpenAI-compatible API, uses `GITHUB_MODELS_TOKEN`

The `LLMClient` abstraction exists to make adding backends post-MVP straightforward, but only one concrete implementation (GitHub Models) is required in v0.1.

GitHub Models uses the OpenAI-compatible API endpoint:
```python
client = openai.OpenAI(
    base_url="https://models.github.ai/inference",
    api_key=os.environ["GITHUB_MODELS_TOKEN"]
)
```

**Verified model identifiers for GitHub Models (as of 2026-04-05):**
- `gpt-4o-mini` — Pass 1 summarization (fast, low cost)
- `gpt-4o` — Pass 2 synthesis (higher quality)

Note: GitHub Models also offers `gpt-4.1-mini` and `gpt-4.1`, which are newer and
generally stronger than the gpt-4o family. These are valid drop-in replacements
configurable via one config change — no code changes required. Verify current model
availability at https://github.com/marketplace/models before changing defaults.

Backend is selected via `config.yaml`:
```yaml
llm:
  backend: "github_models"  # only supported backend in v0.1; openai and anthropic are post-MVP
```

### 4.4 Caching & Deduplication

SQLite-based cache stored in `cache/radar.db`:
- Table: `seen_items(url_hash, content_hash, seen_at)`
- `seen_items` stores only `url_hash` and `content_hash` — not plaintext URLs or content. Implementers must not add a `raw_content` column.
- Items are considered duplicate if URL hash OR content hash matches
- Cache TTL: configurable (default: 30 days via `cache_ttl_days`); expired entries are purged automatically on each run
- `cache/` directory is created automatically on first run if it does not exist
- The project-directory location (`cache/`) was chosen over a user cache directory (`~/.cache/ai-radar/`) for v0.1 to keep the project self-contained and simplify the `actions/cache` CI integration. Migration to a user cache directory is a post-MVP consideration.
- Deleting `cache/radar.db` is always safe — it is a pure dedup optimization. Re-running after deletion causes all articles to be reprocessed (no data loss, no silent errors).

**Two-phase deduplication:**

**Phase 1 — URL hash check (before content fetch):**
- Normalize URL: strip tracking parameters (`utm_*`, etc.), follow redirects to canonical URL
- Newsletter tracking redirects (e.g., `newsletter.service.com/click?url=...`) must be resolved to canonical URLs before hashing
- Hash normalized URL with SHA-256
- Skip if URL hash exists in cache

**Phase 2 — Content hash check (after excerpt fetch, before LLM):**
- Hash `excerpt` text (after boilerplate removal) with SHA-256
- Skip if content hash exists in cache (catches same article published at different URLs)

**Content fingerprinting:**
- URL hash: SHA-256 of the normalized canonical URL (tracking params stripped, redirects followed)
- Content hash: SHA-256 of `clean_text` after boilerplate removal
- Near-duplicate detection: out of scope for MVP — exact hash match only

**Cache safety:**
- Items are marked "seen" only AFTER successful digest generation (see Section 3.7)
- `python -m radar run` is safe to re-run after any failure

### 4.5 Dependencies

Primary install method: `pyproject.toml` with `pip install -e .`. `requirements.txt` is generated from `pyproject.toml` for environments that require it.

```
# Core
requests
feedparser
trafilatura
openai          # used for GitHub Models (OpenAI-compatible API)
pyyaml
python-dotenv
click           # CLI

# Gmail
google-auth
google-auth-oauthlib
google-api-python-client

# Dev
pytest
ruff
```

### 4.6 Testing Strategy

**Test levels:**
- **Unit tests** (`tests/test_sources.py`, `tests/test_processing.py`): test each module in isolation with fixtures
- **LLM contract tests** (`tests/test_llm.py`): test schema validation and parse failure handling using a mock LLM backend
- **Integration test** (`tests/test_pipeline.py`): run full pipeline end-to-end with all external calls mocked
- **Config validation tests** (`tests/test_config.py`): confirm bad configs are caught on load before pipeline execution

**Required test infrastructure:**
- `TestLLMClient` — mock implementation of `LLMClient` returning canned responses; usable in place of any real backend with no code changes
- `tests/fixtures/` — one fixture file per source type: sample Gmail email HTML (link-list format), sample ArXiv API response, sample HN API response, sample web article HTML
- `conftest.py` — shared fixtures including `TestLLMClient`, temp cache directory, temp output directory
- LLM output schema validation tests — confirm `Summarizer` correctly handles malformed Pass 1 output (missing fields, wrong types, missing URLs)

**CI test workflow:**
- `.github/workflows/tests.yml` runs `pytest` on every push and pull request
- Must pass with no real API keys (all external calls mocked)

### 4.7 Logging

- **Default log level:** INFO
- **Format:** structured (key=value or JSON); include timestamp, level, stage, and key metrics
- **Per-stage breadcrumbs required at INFO level:**
  - Source fetch: items fetched per source
  - Dedup: items skipped (URL hash), items skipped (content hash)
  - PreFilter: items passing keyword filter
  - LLM Pass 1: call count, estimated token count and cost, duration, items scored
  - LLM Pass 2: estimated token count and cost, duration
  - Output: digest path written
- **Security constraints:**
  - DEBUG must never be enabled in CI (set `LOG_LEVEL=INFO` in workflow env)
  - Exception handlers must not log raw HTTP request/response details — auth headers may be exposed by `openai` and `google-api-python-client` in debug output
  - No email content or article text logged above DEBUG level

---

## 5. Non-Functional Requirements

| Requirement | Target | Type |
|---|---|---|
| Total pipeline runtime | < 5 minutes for a typical daily run | Aspirational target |
| LLM API calls per run | < 10 (batching enforced) | Hard constraint |
| Cost per run (GitHub Models) | $0 (rate-limited free tier) | Aspirational target; assumes free tier availability for automated runs |
| Cost per run (OpenAI fallback) | < $0.10 | Aspirational target (post-MVP) |
| Setup time (without Gmail OAuth) | < 15 minutes with documented steps | Aspirational target |
| Setup time (with Gmail OAuth) | < 45 minutes (includes GCP project creation) | Aspirational target |
| Python version | 3.11+ | Hard constraint |
| Platform | macOS, Linux, GitHub Actions (Ubuntu) | Hard constraint |

**Per-stage timeout budgets (aspirational):**
- Source fetch: 60s per source
- LLM Pass 1: 120s total
- LLM Pass 2: 120s total

---

## 6. Security & Privacy

- All secrets in `.env`, never committed
- `.env` and `cache/` in `.gitignore`
- Gmail OAuth uses read-only scope (`gmail.readonly`)
- No user data sent to third parties beyond the configured LLM backend
- Digests may contain article content — user responsible for not committing proprietary content

### Content Rights

- The link-list architecture means newsletter author commentary is never ingested — only hyperlinks are extracted from emails
- URLs are not copyrightable; the pipeline fetches publicly accessible web content, the same as clicking a link in a browser
- This design choice is intentional and is the responsible approach to newsletter content processing
- Users are responsible for ensuring their use case complies with the ToS of newsletters they subscribe to and websites they fetch
- Note that article content is sent to the configured LLM provider (GitHub Models / Microsoft Azure infrastructure by default) — users should review their provider's data processing terms

### Web Content Fetching & robots.txt

Web content fetching uses `trafilatura`, which respects robots.txt by default. Users are responsible for ensuring their use complies with the ToS of websites they fetch.

### LLM Data Privacy

- Article content extracted from linked URLs is sent to the configured LLM provider for summarization and synthesis
- Default backend (GitHub Models) routes requests through Microsoft Azure infrastructure
- GitHub's data processing terms apply; users should review before use with sensitive content
- GitHub Models / Azure OpenAI does not use API data for training by default as of this writing — verify with provider
- A reminder comment is included in `config.example.yaml` to review LLM provider data processing terms

---

## 7. Open-Source Considerations

- `config.example.yaml` ships with sensible defaults and comments explaining every field
- `.env.example` documents every required secret with setup instructions and minimum required scopes
- README includes: quickstart, full config reference, adding a custom source, swapping LLM backends
- Source connectors are self-contained — adding a new source requires only implementing the `Source` ABC and registering it in config
- LLM backend is swappable via one config line — no code changes needed (post-MVP: OpenAI and Anthropic backends)
- Ship a sample digest (`examples/sample-briefing.md`) so GitHub visitors can evaluate output quality before setting up the tool

### Install Process

```bash
python -m venv .venv
source .venv/bin/activate  # or .venv\Scripts\activate on Windows
pip install -e .
cp config.example.yaml config.yaml
cp .env.example .env
```

### Responsible Use

The link-list architecture is an intentional design choice: `ai-radar` extracts only hyperlinks from newsletter emails and fetches the publicly accessible web content they point to. Newsletter author commentary is never ingested or summarized. This is the responsible approach to newsletter content processing and respects the value created by newsletter curators.

### Secret Scanning

Recommend `git-secrets` or GitHub's built-in secret scanning for forks. Consider shipping a `.pre-commit-config.yaml` with secret scanning hooks.

---

## 8. Post-MVP Roadmap

| Feature | Notes |
|---|---|
| Slack/email delivery | Send digest to inbox or channel |
| Blog auto-publish | AI writes article from digest, publishes to GitHub Pages or dev.to |
| Full-content newsletter support | Process Substack-style newsletters with inline content (not just link-lists) |
| OpenAI backend | Direct OpenAI API as alternative LLM backend |
| Anthropic backend | Claude API as alternative LLM backend |
| Podcast transcript ingestion | RSS + whisper transcription |
| Web UI | Simple read-only digest viewer |
| Embedding-based relevance filtering | Replace keyword pre-filter with semantic similarity |
| Weekly synthesis digest | Cross-day trend analysis |
| X/Twitter ingestion | Requires API access |

---

## 9. Open Questions

All open questions from v0.2 have been resolved. New open questions will be added here as they are identified during implementation.

---

## 10. Implementation Gaps to Resolve

The following are non-blocking gaps to resolve during implementation. None require spec changes — they are decisions best made while building.

| # | Gap | Context | Suggested approach |
|---|---|---|---|
| 1 | **LLM prompt templates not defined** | `llm/prompts.py` is in the repo structure but no prompt text is specified for Pass 1 or Pass 2. Prompt quality is the single biggest driver of digest quality. | Design iteratively. Start with a simple system prompt + user prompt per pass, evaluate output, and refine. |
| 2 | **HN lookback period undecided** | Section 3.1 says "consider extending lookback to 24–48 hours" without deciding. | Start with 24 hours to match the daily cadence. Extend to 48 if too many quality posts are missed. |
| 3 | **`max_cost_per_run` implementation unspecified** | No guidance on how to estimate cost — token pricing source, handling of GitHub Models free tier. | Estimate cost from token counts × per-token pricing. On the free tier, skip enforcement or log estimated cost without aborting. |
| 4 | **`daily-briefing.yml` not fully specified** | Only fragments (secrets table, cache steps, permissions) are shown across multiple sections. | Assemble the full workflow from the fragments. Include: checkout, Python setup, dependency install, cache restore, pipeline run, cache save, artifact upload. |
| 5 | **Keyword pre-filter noise with short terms** | Case-insensitive substring match means `"AI"` matches "detail", "maintain", etc. | Accept for MVP — the LLM scoring pass (Pass 1) handles false positives. If noise is excessive, consider word-boundary matching as a quick improvement. |
