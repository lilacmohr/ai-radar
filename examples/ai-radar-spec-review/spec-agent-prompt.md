# Spec Agent Prompt — ai-radar SPEC.md Revision

## Your Task

You are a spec agent. Your job is to revise `SPEC.md` for the `ai-radar` project based on a set of decisions made by the product owner after a 9-reviewer AI agent review process. The current `SPEC.md` is provided below your instructions.

Revise the spec to reflect all decisions and required actions listed in this document. Do not resolve open questions not listed here — leave remaining open questions intact. Where a change affects multiple sections, update all affected sections consistently.

---

## Part 1: Product Owner Decisions

These decisions were made explicitly by the product owner and must be applied exactly as specified.

---

### Decision 1 — MVP Scope: Gmail in v0.1
**Resolution:** Gmail is included in v0.1. The primary purpose of v0.1 is to deliver a working personal AI briefing sourced from Gmail newsletters.

**Spec changes:**
- Confirm Gmail as a v0.1 source throughout the spec
- No changes needed to Section 3.1 source table — Gmail is already listed

---

### Decision 2 — GitHub Actions: Keep in v0.1
**Resolution:** GitHub Actions is included in v0.1. The learning value of operationalizing a local tool to run autonomously on a schedule justifies the additional complexity. Manual and cron remain as supported trigger modes. GitHub Actions is the *primary* trigger mode; manual and cron are alternatives.

**Gmail OAuth in GitHub Actions:** Use Option (b) — refresh token stored as GitHub Secret. The spec must document:
1. Initial local auth flow to generate refresh token
2. Storage as a GitHub Secret (`GMAIL_REFRESH_TOKEN`)
3. Clear error message (not silent failure) when token expires — pipeline must detect token expiry and exit with a descriptive error, not a generic API failure
4. A `python -m radar auth gmail` CLI helper command that runs the local OAuth flow and outputs the refresh token for storage as a Secret
5. A note that GCP "testing" mode tokens expire in 7 days; recommend moving the OAuth app to production mode for a 6-month expiry window

**Spec changes:**
- Remove any language suggesting Actions should be deferred to post-MVP
- In Section 3.6, mark GitHub Actions as the primary v0.1 trigger
- Add a "GitHub Actions Setup" subsection to Section 3.6 specifying:
  - All required secrets (`GITHUB_MODELS_TOKEN`, `GMAIL_CLIENT_ID`, `GMAIL_CLIENT_SECRET`, `GMAIL_REFRESH_TOKEN`)
  - Whether each secret is auto-injected by GitHub or manually configured
  - Minimum workflow permissions using principle of least privilege — `contents: write` only needed when `commit_digests: true`; otherwise `contents: read`
  - Note that `GITHUB_TOKEN` (the Actions-provided token) must not be confused with `GITHUB_MODELS_TOKEN` (the personal access token for GitHub Models)
  - Failure notification: GitHub natively emails the repo owner on workflow failure — no additional config required
- Add the Gmail OAuth flow documentation to Section 7 (Open-Source Considerations) or as a subsection of Section 3.1

---

### Decision 3 — LLM Backend: GitHub Models Only in v0.1
**Resolution:** GitHub Models is the only supported LLM backend in v0.1. OpenAI and Anthropic backends are post-MVP.

**Important note:** GitHub Models uses an OpenAI-compatible API endpoint. The `openai` Python SDK is used with a custom `base_url` and `GITHUB_MODELS_TOKEN` as the API key:

```python
client = openai.OpenAI(
    base_url="https://models.inference.ai.azure.com",
    api_key=os.environ["GITHUB_MODELS_TOKEN"]
)
```

**Spec changes:**
- Update Section 4.3 to reflect GitHub Models as the only v0.1 backend
- The `LLMClient` abstraction must still exist to make adding backends post-MVP straightforward, but only one concrete implementation is required in v0.1
- Keep the `llm.backend` config field even though only `github_models` is valid in v0.1
- Rename `GITHUB_TOKEN` to `GITHUB_MODELS_TOKEN` everywhere in the spec to avoid collision with the Actions-provided `GITHUB_TOKEN`
- Update `.env.example` to require only `GITHUB_MODELS_TOKEN` for LLM access — add `OPENAI_API_KEY` and `ANTHROPIC_API_KEY` as commented-out entries with a note that they are for post-MVP backends
- Document minimum required scopes for each secret in `.env.example`
- Move OpenAI and Anthropic backends to Section 8 (Post-MVP Roadmap)
- Update Section 3.5 config: `summarization_model: "gpt-4o-mini"` and `synthesis_model: "gpt-4o"` — these are valid GitHub Models identifiers
- Add startup validation: on launch, the pipeline must verify that the configured model name is valid for the configured backend and fail with a clear error if not

---

### Decision 3 Addendum — LLM Input Strategy: Excerpt-First
**Resolution:** Pass 1 operates on article excerpts (~200 words: title + lede + opening paragraphs), not full truncated articles. Full article text is only fetched for articles that clear the relevance threshold in Pass 1.

**Spec changes:**
- Update Section 3.2 to add an **Extract Excerpt** step: after initial URL extraction from email, fetch only title + first ~200 words per linked article for Pass 1 input
- Update Section 3.3 (LLM Pass 1): input is excerpts (~200 words), not full articles
- Update Section 3.3 (LLM Pass 2): receives full article text (capped at `max_words_full`) for articles that cleared the Pass 1 relevance threshold — not summaries
- Update Section 4.2 data flow to:
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
- Update Section 3.5 config: replace `max_words_per_article: 800` with:
  ```yaml
  pipeline:
    max_words_excerpt: 200      # for Pass 1 input (words, not tokens)
    max_words_full: 800         # for Pass 2 input (words, not tokens)
  ```

---

### Decision 4 — Content Rights: Document in Section 6
**Resolution:** Document the content rights position in Section 6. The link-list architecture is the primary mitigation.

**Spec changes:**
- Add a **Content Rights** subsection to Section 6:
  - The link-list architecture means newsletter author commentary is never ingested — only hyperlinks are extracted from emails
  - URLs are not copyrightable; the pipeline fetches publicly accessible web content, the same as clicking a link in a browser
  - This design choice is intentional and is the responsible approach to newsletter content processing
  - Users are responsible for ensuring their use case complies with the ToS of newsletters they subscribe to and websites they fetch
  - Note that article content is sent to the configured LLM provider (GitHub Models / Microsoft Azure infrastructure by default) — users should review their provider's data processing terms
- Add `commit_digests: false` as the default in the `output:` config block in Section 3.5
- Add a "Responsible Use" note to Section 7 explaining the link-list design intent

---

### Decision 5 — Preprocessing Step Order
**Resolution:** PreFilter before Truncate. Canonical order: Fetch → Deduplicate → Extract Excerpt → PreFilter → Fetch Full Article → Truncate → LLM.

**Spec changes:**
- Reconcile Section 3.2 and Section 4.2 — they currently contradict each other
- Section 3.2 numbered list and Section 4.2 data flow must use the same order
- Add the Normalize step (currently in 3.2 but absent from 4.2) to the 4.2 data flow

---

### Decision 6 — Newsletter Formats: Link-List Only in v0.1
**Resolution:** v0.1 supports link-list newsletters only (e.g. TLDR AI, The Batch). Full-content newsletters (Substack-style) are explicitly deferred to post-MVP.

**Spec changes:**
- Add a `newsletter_type` field to the Gmail source config in Section 3.5:
  ```yaml
  sources:
    gmail:
      enabled: true
      labels: ["newsletters", "AI"]
      max_age_days: 1
      newsletter_type: "link_list"  # only supported type in v0.1; full_content is post-MVP
  ```
- Update Section 3.1 Gmail connector notes: "v0.1 supports link-list newsletters only (extracts URLs from email body). Full-content newsletter processing is post-MVP."
- Add a note in Section 3.2 that the Extract step for Gmail sources means URL extraction from email body, not text extraction from the email itself
- Specify Gmail email processing behavior: (a) prefer HTML MIME part, fall back to plain text; (b) emails are marked as read after successful processing; (c) each extracted URL is treated as an independent article candidate
- Add full-content newsletter support to Section 8 (Post-MVP Roadmap)

---

### Decision 7 — trafilatura for Email Content: Resolved by Decision 6
**Resolution:** No additional spec change. trafilatura is only used for web URL fetching, which is its correct use case. Email HTML is never passed to trafilatura in v0.1.

---

### Decision 8 — Failure Notification
**Resolution:** GitHub Actions native failure emails (primary) + failure-digest file (secondary). No SMTP required.

**Spec changes:**
- Add a **Failure Handling** section — see Part 2, Required Action 3 for the full contract
- On any pipeline failure: write `briefing_{date}.md` to `output_dir` containing a clear failure message and pointer to logs
- Exit code must be non-zero on failure so GitHub Actions marks the run as failed
- Note in Section 3.6 that GitHub Actions failure emails are the primary notification mechanism — no additional config required

---

### Decision 9 — robots.txt Compliance
**Resolution:** Rely on trafilatura's built-in robots.txt handling. Add a configurable user-agent string.

**Spec changes:**
- Add to Section 6: "Web content fetching uses trafilatura, which respects robots.txt by default. Users are responsible for ensuring their use complies with the ToS of websites they fetch."
- Add `user_agent` to the pipeline config block in Section 3.5:
  ```yaml
  pipeline:
    user_agent: "ai-radar/0.1 (personal digest tool)"
  ```
- Remove robots.txt from Open Questions if present — it is resolved

---

### Decision 10 — AI-Generated Content Disclosure Footer
**Resolution:** Add a standard disclosure footer to every digest.

**Spec changes:**
- Update Section 3.4 to include this footer as the final element of every digest:
  ```
  ---
  *Generated by ai-radar on {date}. Content summarized by AI from linked sources — always verify claims against originals.*
  ```
- Note in Section 4.1 that `output/markdown.py` renders the footer with correct date substitution

---

### Decision 11 — HN min_score
**Resolution:** Change from 100 to 50.

**Spec changes:**
- Update Section 3.5 config: `min_score: 50`
- Add comment: `# Domain Expert recommendation — quality posts often score 50-80; 100 over-filters. Tune after first runs.`
- Add a note in Section 3.1 HN connector row that scores are time-sensitive; a post 2 hours old with 50 points may reach 200 by end of day; consider extending lookback to 24-48 hours to let scores stabilize

---

### Decision 12 — AGENTS.md
**Resolution:** Document the agentic development workflow used to build ai-radar — the 9-reviewer protocol, decisions made, and how the spec was revised. Framed as a reusable pattern for AI-assisted software development.

**Spec changes:**
- Update Section 4.1 repo structure: add description for `AGENTS.md` — "Documents the agentic development workflow and AI reviewer protocol used to build this project. A reusable pattern for AI-assisted software development."

---

## Part 2: Required Actions from Synthesis Review

These are non-negotiable changes identified by the 9-reviewer synthesis as blocking or ambiguous. Apply all of them.

---

### Required Action 1 — Config Numeric Values: Add Rationale or TBD Markers
**Section 3.5, Section 5**

For every numeric value in `config.yaml`, either confirm it is a real decision (add a one-line rationale comment) or mark it as `# TBD — tune after first runs`. Apply the following:

```yaml
profile:
  relevance_threshold: 6  # TBD — tune after first runs; articles below this score are dropped

sources:
  arxiv:
    max_results: 20  # TBD — tune after first runs
  hackernews:
    min_score: 50  # Domain Expert recommendation — quality posts often score 50-80. Tune after first runs.

pipeline:
  max_words_excerpt: 200   # for Pass 1 input (words, not tokens; ~275 tokens at average density)
  max_words_full: 800      # for Pass 2 input (words, not tokens; ~1100 tokens at average density)
  max_articles_to_summarize: 30  # TBD — tune after first runs; caps Pass 1 input
  max_articles_in_digest: 15     # TBD — tune after first runs; caps Pass 2 input
  batch_size: 10           # TBD — 10 articles/call is cheaper but less reliable than 1/call; tune after first runs
```

Also update Section 5 (Non-Functional Requirements):
- Split setup time NFR: "< 15 min without Gmail OAuth, < 45 min with Gmail OAuth (includes GCP project creation)"
- Label each NFR target as either "hard constraint" or "aspirational target":
  - `< 5 min runtime` — aspirational target
  - `< 10 LLM API calls` — hard constraint (enforced by batching)
  - `$0 cost (GitHub Models)` — aspirational target; assumes free tier availability for automated runs
  - `< $0.10 cost (OpenAI fallback)` — aspirational target
- Add per-stage timeout budgets (aspirational):
  - Source fetch: 60s per source
  - LLM Pass 1: 120s total
  - LLM Pass 2: 120s total

---

### Required Action 2 — LLM Pass 1 Structured Output Contract
**Section 3.3**

The current spec has `LLMClient.complete()` returning `str` with no schema, no parsing spec, and no failure behavior. Add the following to Section 3.3:

**Pass 1 response schema:**
```json
[
  {
    "url": "string",
    "score": "integer (1-10)",
    "summary": "string (2-3 sentences)"
  }
]
```

**Required spec additions:**
- Pass 1 must use JSON mode / structured output to enforce schema compliance
- Parsing responsibility is assigned to `Summarizer`, not `LLMClient`
- On malformed output: retry once with an explicit JSON instruction; on second failure, skip the batch and log a warning
- Document the batching tradeoff: `batch_size: 10` is cheaper but LLMs frequently drop items from the middle of large batches; this is a known limitation to monitor
- Pass 1 must validate that every input URL appears in the output; missing URLs are treated as score 0 (dropped) and logged

---

### Required Action 3 — Full Failure Handling Contract
**Sections 3.1, 3.2, 3.3, 3.6**

Add a new "Failure Handling" section (3.7) specifying behavior at every pipeline stage:

**Source fetch failures:**
- Log and skip the failed source; pipeline continues with remaining sources
- Never abort the full pipeline on a single source failure
- If ALL sources fail: exit code 2 (fatal), write failure-digest file

**LLM parse failures (Pass 1):**
- Validate output against schema
- Retry once with explicit JSON instruction
- On second failure: skip the batch, log warning, continue with remaining batches

**LLM API errors (429, 5xx, timeout):**
- Exponential backoff, max 3 retries
- After exhaustion: log error, fail loudly (not silently)

**Zero qualifying articles:**
- Write a minimal digest: "No notable content found today."
- Exit code 0 (not a failure)

**Fatal conditions (all sources failed OR synthesis model unreachable):**
- Exit code 2
- Write failure-digest file
- Clear, descriptive error message in logs

**Cache behavior on partial failure:**
- Items are marked "seen" only AFTER successful digest generation, not at fetch time
- This ensures re-running after a failure reprocesses all articles safely
- `python -m radar run` must be safe to re-run after any failure (idempotent)

**Exit code contract:**
- `0` = success (including zero-article "no content today" digests)
- `1` = partial failure (some sources failed, digest still generated)
- `2` = fatal (no digest generated)

**Failure-digest file content:**
```
# ai-radar — Pipeline Failed {DATE}

The pipeline encountered an error and could not generate today's briefing.
Exit code: {exit_code}
Check GitHub Actions logs (or local logs) for details.
```

---

### Required Action 4 — Pass 2 Input Structure and Context Budget
**Section 3.3**

Explicitly specify Pass 2 input in Section 3.3:
- Pass 2 receives **full article text** (not summaries) for the top `max_articles_in_digest` articles from Pass 1
- Each article is capped at `max_words_full` words before being passed to Pass 2
- Add a context budget note: `15 articles × 800 words ≈ 12,000 words ≈ 16,000 tokens` — this fits within `gpt-4o`'s context window but should be monitored
- Specify behavior if total input approaches the model's context limit: truncate the article list to fit, log a warning

---

### Required Action 5 — Data Models: Define All Schemas
**Section 3.1, 4.1**

Add a new "Data Models" subsection to Section 3.1 or 4.1 specifying required fields for all shared models in `models.py`:

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

@dataclass
class ExcerptItem:
    url: str
    title: str
    source: str
    published_at: datetime
    excerpt: str              # title + first ~200 words
    url_hash: str

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
class Digest:
    date: date
    articles: list[ScoredItem]
    executive_summary: str
    contrarian_insights: str
    follow_up_questions: str
    trending_themes: str
    source_stats: dict        # counts per source, filter stats, model names, run duration
```

---

### Required Action 6 — Two-Phase Deduplication and URL Normalization
**Section 4.4**

The current spec states "cache is checked before any fetch or LLM call" which is internally inconsistent (content hashing requires fetched content). Replace with a two-phase dedup spec:

**Phase 1 — URL hash check (before content fetch):**
- Normalize URL: strip tracking parameters, follow redirects to canonical URL
- Hash normalized URL with SHA-256
- Skip if URL hash exists in cache

**Phase 2 — Content hash check (after excerpt fetch, before LLM):**
- Hash `clean_text` with SHA-256
- Skip if content hash exists in cache (catches same article published at different URLs)

**Additional requirements:**
- Newsletter tracking redirects (e.g., `newsletter.service.com/click?url=...`) must be resolved to canonical URLs before hashing
- Specify that `seen_items` stores hashes only — not plaintext URLs or content

---

### Required Action 7 — Logging Strategy
**Sections 3.2, 3.3, 6**

Add a "Logging" subsection specifying:

- **Default log level:** INFO
- **Format:** structured (key=value or JSON); include timestamp, level, stage, and key metrics
- **Per-stage breadcrumbs required at INFO level:**
  - Source fetch: items fetched per source
  - Dedup: items skipped (URL hash), items skipped (content hash)
  - PreFilter: items passing keyword filter
  - LLM Pass 1: call count, estimated token count, duration, items scored
  - LLM Pass 2: estimated token count, duration
  - Output: digest path written
- **Security constraints:**
  - DEBUG must never be enabled in CI (set `LOG_LEVEL=INFO` in workflow env)
  - Exception handlers must not log raw HTTP request/response details — auth headers may be exposed by `openai` and `google-api-python-client` in debug output
  - No email content or article text logged above DEBUG level

---

### Required Action 8 — Pre-Filter Algorithm Specification
**Section 3.2, Step 5**

Replace "keyword/topic filter against user's interest profile" with:
- **Matching strategy:** case-insensitive substring match
- **Fields searched:** title + first 200 words of excerpt
- **Match logic:** pass if ANY keyword from the `interests` list matches
- **Example:** interest `"LLM inference"` matches articles containing `"llm inference"`, `"LLM Inference"`, `"LLM inference and serving"`, etc.

---

### Required Action 9 — Words vs. Tokens: Use Words Consistently
**Sections 3.2, 3.3, 3.5**

Standardize on **words** as the unit throughout the spec:
- All config values and pipeline descriptions use words
- Add a note where relevant: "~750 words ≈ 1,000 tokens at average English text density"
- Update Step 4 in Section 3.2: change "max token length" to "word count"
- Update all prose references from "tokens" to "words" where the context is truncation/length limits

---

### Required Action 10 — Install Process
**Sections 4.5, 5, 7**

Resolve the `pyproject.toml` vs `requirements.txt` ambiguity:
- **Primary install method:** `pyproject.toml` with `pip install -e .`
- **`requirements.txt`:** generated from `pyproject.toml` for environments that require it; note this in Section 4.5
- Add exact install commands to Section 7 (Open-Source Considerations):
  ```bash
  python -m venv .venv
  source .venv/bin/activate  # or .venv\Scripts\activate on Windows
  pip install -e .
  cp config.example.yaml config.yaml
  cp .env.example .env
  ```

---

### Required Action 11 — Testing Strategy
**Section 4.1**

Add a new "Testing Strategy" section (4.6 or similar) specifying:

**Test levels:**
- **Unit tests** (`tests/test_sources.py`, `tests/test_processing.py`): test each module in isolation with fixtures
- **LLM contract tests** (`tests/test_llm.py`): test schema validation and parse failure handling using a mock LLM backend
- **Integration test** (`tests/test_pipeline.py`): run full pipeline end-to-end with all external calls mocked

**Required test infrastructure:**
- `TestLLMClient` — mock implementation of `LLMClient` returning canned responses; usable in place of any real backend with no code changes
- `tests/fixtures/` — one fixture file per source type: sample Gmail email HTML (link-list format), sample ArXiv API response, sample HN API response, sample web article HTML
- `conftest.py` — shared fixtures including `TestLLMClient`, temp cache directory, temp output directory
- LLM output schema validation tests — confirm `Summarizer` correctly handles malformed Pass 1 output (missing fields, wrong types, missing URLs)
- `tests/test_config.py` — config validation tests; confirm bad configs are caught on load before pipeline execution

**CI test workflow:**
- Add `.github/workflows/tests.yml` to repo structure in Section 4.1
- Runs `pytest` on every push and pull request
- Must pass with no real API keys (all external calls mocked)

**Repo structure additions (Section 4.1):**
- `tests/fixtures/` directory
- `tests/conftest.py`
- `tests/test_pipeline.py`
- `tests/test_config.py`
- `.github/workflows/tests.yml`

---

### Required Action 12 — Cache Maintenance and Safety
**Section 4.4**

Add the following to Section 4.4:
- Deleting `cache/radar.db` is always safe — it is a pure dedup optimization. Re-running after deletion causes all articles to be reprocessed (no data loss, no silent errors). Document this explicitly.
- Expired entries (beyond `cache_ttl_days`) are purged automatically on each run
- Add `cache_ttl_days` to Section 3.5 config block:
  ```yaml
  pipeline:
    cache_ttl_days: 30  # items older than this are removed from cache on each run
  ```
- Specify that `cache/` directory is created automatically on first run if it does not exist
- Add CLI commands to Section 3.6 or a CLI reference section:
  - `python -m radar cache clear` — delete all cache entries (safe; causes full reprocess on next run)
  - `python -m radar cache stats` — show cache size, entry count, oldest/newest entry
  - `python -m radar cache remove <url>` — remove a specific URL to force reprocessing

---

### Required Action 13 — Content Fingerprinting Strategy
**Sections 3.2, 4.4**

Specify the hashing approach:
- **URL hash:** SHA-256 of the normalized canonical URL (tracking params stripped, redirects followed)
- **Content hash:** SHA-256 of `clean_text` after boilerplate removal
- **Near-duplicate detection:** out of scope for MVP — exact hash match only
- Add this to Section 3.2 (Deduplication step) and Section 4.4

---

### Required Action 14 — LLM Data Privacy Disclosure
**Sections 3.3, 6**

Add to Section 6 (Security & Privacy):
- Article content extracted from linked URLs is sent to the configured LLM provider for summarization and synthesis
- Default backend (GitHub Models) routes requests through Microsoft Azure infrastructure
- GitHub's data processing terms apply; users should review before use with sensitive content
- Note which providers use API data for training by default (GitHub Models / Azure OpenAI: no training on API data by default as of this writing — verify with provider)
- Add a reminder comment to `config.example.yaml` to review LLM provider data processing terms

---

## Part 3: Suggestions to Include

Non-blocking recommendations from the synthesis review worth including. Apply all of them.

---

### Suggestion 1 — `python -m radar check` Subcommand
Add to Section 3.6 (Trigger Modes) or a CLI reference section:
- `python -m radar check` — validates config, tests credentials for each enabled source, fetches one item per source without LLM calls
- Must exit 0 if all checks pass, non-zero if any fail, with clear per-check output
- Critical for first-run experience and post-change verification

### Suggestion 2 — Sample Digest in `examples/`
Add to Section 4.1 repo structure:
- `examples/sample-briefing.md` — a realistic example digest showing all sections populated with plausible content
- Add to Section 7: ship a sample digest so GitHub visitors can evaluate output quality before setting up the tool

### Suggestion 3 — Pipeline Metadata Section in Digest
Add to Section 3.4 (Digest Output Format), as a section immediately above the disclosure footer:
```markdown
## 📊 Pipeline Metadata
- Sources: {n} fetched, {n} after dedup, {n} after filter
- Articles: {n} scored, {n} in digest
- Models: {summarization_model} (Pass 1), {synthesis_model} (Pass 2)
- Run time: {duration}s
```
This allows the reader to distinguish "slow news day" from "sources failed."

### Suggestion 4 — Secret Scanning Recommendation
Add to Section 7 (Open-Source Considerations):
- Recommend `git-secrets` or GitHub's built-in secret scanning for forks
- Consider shipping a `.pre-commit-config.yaml` with secret scanning hooks

### Suggestion 5 — Data Residency Disclosure for GitHub Models
Add to Section 6 and as a comment in `config.example.yaml`:
- Using the default GitHub Models backend sends article content to Microsoft/OpenAI infrastructure
- Users processing sensitive content should review GitHub's data processing terms

### Suggestion 6 — Cost Tracking in Logs
Add to the logging spec (Required Action 7) and Section 3.5 config:
- Log estimated token count and cost per LLM call at INFO level
- Add optional config:
  ```yaml
  pipeline:
    max_cost_per_run: 0.10  # optional hard limit in USD; pipeline aborts if exceeded. Set to 0 to disable.
  ```

---

## Part 4: Nits to Apply

Minor changes requiring no judgment.

- **`podcasts.py` stub:** Add comment in Section 4.1 repo structure: `# post-MVP, not yet implemented`; add `# post-MVP` comment to podcasts entry in `config.yaml`
- **Cache stores hashes only:** Add explicit note to Section 4.4: "`seen_items` stores only `url_hash` and `content_hash` — not plaintext URLs or content. Implementers must not add a `raw_content` column."
- **`cache/` auto-creation:** Specify in Section 4.4 that the pipeline creates `cache/` on first run if it does not exist
- **`conftest.py` and `tests/fixtures/`:** Add both to repo structure in Section 4.1 (also covered in Required Action 11)
- **`.env.example` token scopes:** Add minimum required scopes for each secret as inline comments
- **`commit_digests` config:** Add `commit_digests: false` to `output:` config block (also covered in Decision 4 — confirm applied)
- **Post-MVP roadmap:** Reorder Section 8 so Slack/email delivery appears before Web UI — more immediately useful for a personal pipeline tool
- **`examples/` directory:** Add to Section 4.1 repo structure (also covered in Suggestion 2)

---

## Part 5: Open Questions

### Close These (resolved by decisions above):
- **Open Question #3** (Gmail OAuth in Actions) — resolved: Option (b), refresh token as GitHub Secret, with `python -m radar auth gmail` helper
- **Open Question #5** (Rate limit handling for GitHub Models) — resolved: exponential backoff, max 3 retries (covered in Required Action 3)

### Add These New Open Questions to Section 9:

| # | Question | Notes |
|---|---|---|
| New | How should the SQLite dedup cache persist across ephemeral GitHub Actions runners? | Options: use `actions/cache` to persist `cache/radar.db` between runs; commit cache to repo; document that CI mode relies on `published_at` recency filtering instead of hash-based dedup. Must be resolved before GitHub Actions trigger is fully functional. |
| New | Which specific link-list newsletters will be included in `config.example.yaml`? | TLDR AI and The Batch are confirmed. Need sender email addresses and Gmail label names for default config. |
| New | Are `gpt-4o-mini` and `gpt-4o` the correct model identifiers for GitHub Models? | Verify exact strings before finalizing config defaults. Base URL assumed: `https://models.inference.ai.azure.com`. |
| New | Should `cache/` live in the project directory or `~/.cache/ai-radar/`? | Project directory is simpler; user cache dir is cleaner for OSS installs. |
| New | What is the GCP OAuth app verification path for production-mode tokens? | Testing mode tokens expire in 7 days. Production mode requires Google verification (privacy policy, domain). Document the verification process or recommend an alternative long-lived credential approach. |

---

## Part 6: Sections to Leave Unchanged

Do not modify the following unless directly required by an action above:
- Section 1 (Overview) — goals, non-goals, problem statement
- Section 2 (User Personas)
- Section 4.5 (Dependencies) — except to note `pyproject.toml` as primary per Required Action 10
- Section 8 (Post-MVP Roadmap) — except to add items explicitly deferred above (full-content newsletters, OpenAI backend, Anthropic backend)

---

## Output Instructions

- Produce a **complete revised `SPEC.md`** — not a diff, not a list of changes
- Preserve all existing section numbers and headings unless an action requires adding a new section
- Preserve all existing tables, code blocks, and formatting conventions
- Where config blocks are updated, show the **complete updated config block**, not just the changed lines
- Where new sections are added, insert them at a logical position and update the document structure accordingly
- **Version bump:** update version to `0.2 (MVP — Post-Review Revision)` and Last Updated date to `2026-04-04`
