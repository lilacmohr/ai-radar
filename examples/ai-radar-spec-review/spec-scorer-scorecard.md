# Spec Quality Scorecard — ai-radar

**Spec:** `SPEC.md` (Version 0.1 MVP, Draft)
**Evaluated:** 2026-04-04
**Evaluator:** Spec Quality Evaluator (Claude Opus 4.6)

---

## Summary

| # | Dimension | Weight | Score | Weighted |
|---|---|---|---|---|
| 1 | Unambiguity | 25% | 5.5 | 1.375 |
| 2 | Completeness | 20% | 4.5 | 0.900 |
| 3 | Consistency | 15% | 5.0 | 0.750 |
| 4 | Verifiability | 15% | 4.0 | 0.600 |
| 5 | Implementation Guidance | 10% | 5.5 | 0.550 |
| 6 | Forward Traceability | 5% | 6.5 | 0.325 |
| 7 | Singularity | 5% | 5.0 | 0.250 |
| 8 | Failure Mode Coverage | 3% | 2.5 | 0.075 |
| 9 | Interface Contracts | 2% | 4.0 | 0.080 |
| | **Weighted Total** | **100%** | | **4.91** |

**Overall Assessment:** The spec is a solid concept document and product vision, but it is not yet implementation-ready for AI agents. It would produce a codebase that broadly resembles the right thing but diverges on key behavioral details, contains no testable acceptance criteria, and has no failure handling. Two agents implementing from this spec independently would produce structurally similar but behaviorally incompatible code.

---

## Dimension Details

### 1. Unambiguity — 5.5 / 10 (Weight: 25%)

**Rationale:** Several key behavioral statements have multiple plausible interpretations, and critical implementation details are deferred with vague language that an agent would resolve differently than intended.

**Key Finding:** The pre-filter (Section 3.2, step 5) says "keyword/topic filter against user's interest profile" without specifying the matching algorithm. Does "LLM inference and serving" match an article containing only the word "inference"? Is it substring match, whole-word match, any-keyword-matches, or all-keywords-must-match? Two agents would implement this differently, producing materially different filtering behavior — one might pass 80% of articles through, another might pass 20%.

**Additional ambiguities found:**
- "content fingerprints" (3.2 step 2) — no algorithm specified. SHA-256 of full text? SimHash? First N characters? An agent must choose.
- "strip boilerplate, extract clean article text" (3.2 step 3) — "clean" is undefined. Trafilatura has multiple extraction modes and parameters; the spec doesn't say which.
- "top-ranked articles from Pass 1" (3.3 Pass 2 input) — how many? All articles above the relevance threshold? Capped at `max_articles_in_digest`? The config has both `max_articles_to_summarize` (30) and `max_articles_in_digest` (15) but the spec doesn't say where the 15-cap is applied.
- "optionally commits it to a `digests/` folder" (3.6) — what controls this option? No config key exists for it.
- "sensible defaults" (Section 7) — undefined.
- "Where transcripts are available in feed" (3.1 podcast row) — how is transcript availability detected?
- `prompts.py` is listed in the repo structure but no prompt templates are specified anywhere in the spec. The LLM pass descriptions give intent ("relevance score + 2-3 sentence summary") but not the actual prompt structure, system message content, or output parsing format.

**Improvement to gain +2 points:** Specify the pre-filter matching algorithm, the content fingerprint hash method, the prompt templates (or at least their structure and expected output format), and where the `max_articles_in_digest` cap is applied in the pipeline.

---

### 2. Completeness — 4.5 / 10 (Weight: 20%)

**Rationale:** The spec has good structural coverage — most modules are named and their purpose described — but multiple modules are defined by name only, critical data models are incomplete, and there are zero acceptance criteria anywhere in the document.

**Key Finding:** There are no acceptance criteria for any module. Not a single "this module is correctly implemented when..." statement exists. An implementing agent has no way to know when it's done, and a reviewer has no way to verify correctness beyond "it doesn't crash."

**Specific completeness gaps:**
- **Data models incomplete:**
  - `RawItem` — referenced in Source interface return type but never defined. What fields does it have? At minimum: url, title, source_name, raw_content, published_at? But this is a guess.
  - `NormalizedItem` — partially defined in 3.2 step 6 as `{title, url, source, published_at, clean_text, word_count}` but field types are not specified (is `published_at` a datetime, ISO string, or Unix timestamp?).
  - `ScoredItem` — appears in data flow diagram (4.2) but is never defined. What fields does it add to NormalizedItem? Presumably `relevance_score` and `summary`, but this is inference.
  - `Digest` — listed in `models.py` description (4.1) but never defined. What fields? How do digest sections map to object attributes?
- **Modules described by name only:**
  - `config.py` — "config loading and validation" but no validation rules specified. What constitutes invalid config?
  - `__main__.py` — "entry point" but CLI interface not fully specified. Only `python -m radar run` is shown. Are there other subcommands? Flags? `--dry-run`? `--verbose`?
  - `pipeline.py` — "orchestrates all stages" but orchestration logic not described. Does it return a result? Log progress? Handle partial failures?
  - `prompts.py` — "all prompt templates" but zero prompt templates provided.
  - `markdown.py` — digest format shown (3.4) but no rendering logic. Does it write to disk? Return a string? Both?
- **Behavioral gaps:**
  - Gmail OAuth flow: How does the user obtain initial tokens? Is there a `radar auth` command? The refresh token is in `.env` but how does it get there?
  - ArXiv connector: API vs RSS? The source table says "ArXiv API + RSS" — which is used when? For what?
  - Web scraping source: Listed in source table (3.1) but has no config section and no file in the repo structure. Is it a standalone source or a utility used by other sources?
  - Cache TTL: Mentioned in 4.4 as "configurable (default: 30 days)" but not present in the config.yaml example.

**Improvement to gain +2 points:** Add acceptance criteria for each module (even 1-2 sentences per module stating the testable "done" condition), and fully define all four data models (`RawItem`, `NormalizedItem`, `ScoredItem`, `Digest`) with field names, types, and constraints.

---

### 3. Consistency — 5.0 / 10 (Weight: 15%)

**Rationale:** There is at least one structural contradiction in the pipeline ordering, plus several config schema inconsistencies between sections that would cause agents to implement different behaviors depending on which section they read.

**Key Finding:** The preprocessing pipeline ordering contradicts between Section 3.2 and Section 4.2:

| Step | Section 3.2 Order | Section 4.2 Data Flow Order |
|---|---|---|
| 3 | Extract | Extractor → **NormalizedItem** list |
| 4 | **Truncate** | **PreFilter** |
| 5 | **Pre-filter** | **Truncator** |
| 6 | **Normalize** | *(not present — merged into step 3)* |

Two problems: (1) Truncate and Pre-filter are swapped — this matters because truncating before filtering wastes work on articles that will be filtered out, while filtering before truncating might miss keywords in truncated portions. (2) Normalize is a separate final step in 3.2 but is implicitly merged into the Extractor in 4.2 (which outputs `NormalizedItem list`). There is no `normalizer.py` in the repo structure, confirming this merge, but 3.2 still lists it as a distinct step.

**Additional inconsistencies:**
- **Config schema conflict:** Section 3.5 config.yaml places model selection under `pipeline.summarization_model` and `pipeline.synthesis_model`. Section 4.3 introduces a top-level `llm.backend` key that does not appear in the 3.5 config example. An agent implementing config loading would not know the canonical schema.
- **Env var conflict:** Section 3.5 `.env` lists only `GITHUB_TOKEN`, `GMAIL_CLIENT_ID`, `GMAIL_CLIENT_SECRET`, `GMAIL_REFRESH_TOKEN`. Section 4.3 references `OPENAI_API_KEY` and `ANTHROPIC_API_KEY` as required for those backends. These are absent from the `.env` example.
- **Gmail source config:** Section 3.1 source table says "configured labels/senders" but the config.yaml (3.5) only has `labels` — no sender filtering config exists.
- **Anthropic backend vs dependencies:** Section 4.3 lists Anthropic as a supported backend ("Claude API, uses `ANTHROPIC_API_KEY`"), but Section 4.5 lists `openai` as "used for all backends (OpenAI-compatible)" and does not include the `anthropic` package. The Anthropic API is not OpenAI-compatible. An agent would either skip Anthropic support or add an unlisted dependency.
- **Cache timing:** Section 4.4 says "Cache is checked before any fetch or LLM call" but the data flow (4.2) shows fetch happening first, then deduplication. These describe different architectures — one checks URLs against cache before fetching content; the other fetches all content then deduplicates.
- **Terminology drift:** "article" / "item" / "content" are used interchangeably. The data models use "Item" (RawItem, NormalizedItem) but the prose consistently says "articles". Minor but contributes to ambiguity.

**Improvement to gain +2 points:** Reconcile the pipeline ordering between 3.2 and 4.2 into a single authoritative sequence. Add the `llm.backend` key to the config.yaml example. Resolve the Anthropic dependency question.

---

### 4. Verifiability — 4.0 / 10 (Weight: 15%)

**Rationale:** The spec has zero explicit acceptance criteria. Non-functional requirements are quantified (good), but functional correctness is undefined. LLM output quality — the core value proposition — has no verification strategy whatsoever.

**Key Finding:** The entire value proposition of this tool is LLM-generated content: relevance scores, summaries, contrarian insights, trend detection. The spec provides no strategy for verifying any of this. How do you test that a relevance score of 7 is correct? That a "contrarian insight" is actually contrarian and not just a rephrased summary? That "trending themes" reflect real patterns and not hallucinated ones? Without even a basic verification approach (e.g., "relevance scores for known-relevant test articles must be >= 7; scores for known-irrelevant articles must be <= 4"), the LLM pipeline is unverifiable.

**What is verifiable:**
- NFRs are well-quantified: "< 5 minutes", "< 10 API calls", "< $0.10" — these are testable.
- Digest structure is specified: section headings, ordering, and approximate content counts (3-5 bullets, 2-3 sentences) are countable.
- Source interface contract is partially testable: `fetch()` returns `list[RawItem]`.
- Cache deduplication: "duplicate if URL hash OR content hash matches" is testable.

**What is not verifiable:**
- No module has a "done when..." criterion.
- LLM output quality: no golden-set tests, no assertion strategy, no minimum quality bar.
- Pre-filter effectiveness: no expected precision/recall targets.
- Config validation: no specification of what invalid config looks like.
- "richly structured digest" (1.2) — subjective.
- "high standards for signal quality" (persona) — subjective.
- "sensible defaults" (Section 7) — subjective.

**Improvement to gain +2 points:** Add explicit acceptance criteria for each module — at minimum, one testable assertion per module. For LLM outputs, define a small golden test set (3-5 known articles with expected relevance score ranges and summary characteristics) and specify structural validation rules (e.g., "Pass 1 output must be valid JSON with fields: title, url, relevance_score (int 1-10), summary (string, 20-100 words)").

---

### 5. Implementation Guidance — 5.5 / 10 (Weight: 10%)

**Rationale:** Key technology choices are made (SQLite, trafilatura, click, feedparser) and the file structure is detailed, but cross-cutting concerns — error handling, logging, retry strategies, async vs sync — are entirely absent. Two agents building adjacent modules would produce structurally inconsistent code.

**Key Finding:** There is no error handling convention specified anywhere. When a source connector's API call fails, does it: raise an exception and let the pipeline catch it? Return an empty list? Log and continue? Return a partial result? This is not a minor detail — it determines whether the pipeline is resilient or fragile, and whether errors are visible or silent. Without guidance, each source connector agent will choose differently.

**What guidance exists:**
- Technology choices: SQLite for cache, trafilatura for extraction, click for CLI, feedparser for RSS. These are clear and prevent divergence.
- File structure: Detailed and unambiguous for where code goes.
- Source interface: ABC pattern specified with method signatures.
- LLM abstraction: Simple `complete()` interface defined.
- Config format: YAML with full example.

**What guidance is missing:**
- **Error handling:** No convention. Raise? Return? Log? Which exception types?
- **Logging:** No mention of logging at all. No log levels, no log format, no guidance on what events to log.
- **Retry strategy:** Rate limit handling is listed as an open question (Section 9, #5) with a tentative "exponential backoff" note, but nothing is specified. This is critical for a tool making API calls to 4+ external services.
- **Async vs sync:** Not stated. The absence of any async mention implies synchronous, but an agent might reasonably choose async for parallel source fetching.
- **Testing strategy:** Three test files are listed but no testing approach defined. Unit tests? Integration tests? Mocked APIs? Test fixtures?
- **LLM output parsing:** Pass 1 returns "relevance score + summary" but the parsing strategy is not specified. JSON? Structured output? Regex extraction from free text?
- **Prompt engineering patterns:** `prompts.py` is listed but no templates or structure provided.

**Improvement to gain +2 points:** Add a "Conventions" section specifying: (1) error handling pattern (e.g., "source connectors return empty list on failure and log the error; pipeline always continues"), (2) logging approach (e.g., Python `logging` module, INFO for pipeline progress, WARNING for recoverable errors, ERROR for failures), and (3) LLM output format (e.g., "Pass 1 must return JSON array; each element has `title`, `relevance_score`, `summary` fields").

---

### 6. Forward Traceability — 6.5 / 10 (Weight: 5%)

**Rationale:** The repo structure maps well to functional requirement sections, making it possible to trace most requirements to files. However, the absence of requirement IDs and acceptance criteria weakens traceability significantly — you can map "where" but not "what specifically" or "how to verify."

**Key Finding:** A strong implicit mapping exists: Section 3.1 (Source Ingestion) → `radar/sources/`, Section 3.2 (Preprocessing) → `radar/processing/`, Section 3.3 (LLM Pipeline) → `radar/llm/`, Section 3.4 (Digest Format) → `radar/output/markdown.py`. This mapping is good enough that GitHub Issues could be written at the module level — but not at the requirement level, because individual requirements within each section are not enumerated or identified.

**Orphaned items found:**
- `AGENTS.md` is listed in the repo structure (4.1) but referenced nowhere in any requirement. What does it contain? Who writes it?
- Web scraping source is in the 3.1 source table but has no file in the repo structure and no config section. It's unclear if this is a standalone source or an internal utility.
- `config.example.yaml` and `.env.example` are in the repo structure and mentioned in Section 7 but have no functional requirement driving their content.
- `processing/normalizer.py` does not exist (Normalize is step 6 in 3.2 but has no corresponding file in the repo structure).

**Improvement (score >= 7, so not required, but noted):** Add requirement IDs (e.g., FR-3.1.1, FR-3.2.1) so that issues can reference specific requirements rather than entire sections.

---

### 7. Singularity — 5.0 / 10 (Weight: 5%)

**Rationale:** Requirements are frequently compound, particularly in the pipeline and LLM sections. An agent could implement part of a compound requirement, believe it is complete, and move on.

**Key Finding:** LLM Pass 1 (Section 3.3) bundles two distinct behaviors into one: "relevance score (1-10 against user role/interests) + 2-3 sentence summary per article." An agent might implement scoring without summarization (or vice versa) and consider Pass 1 complete. These should be specified as separate outputs of the same pass, each with its own validation.

**Additional compound requirements:**
- Section 3.2 lists 6 preprocessing steps as a single numbered list under one heading. Each step is a separate module with its own logic, but they're presented as one requirement.
- Section 3.6: "The pipeline must support all three trigger modes without code changes" — this is three requirements (manual, cron, GitHub Actions) bundled as one.
- Section 3.4 digest format: five distinct sections are specified as one output format. An agent might implement three of five sections and consider the digest "done."
- Section 4.4 cache: "duplicate if URL hash OR content hash matches" plus "Cache TTL: configurable" plus "Cache is checked before any fetch or LLM call" — three distinct behaviors in one paragraph.
- Section 7: "README includes: quickstart, full config reference, adding a custom source, swapping LLM backends" — four documentation requirements in one bullet.

**Improvement to gain +2 points:** Decompose LLM Pass 1 into explicit separate output fields. List each digest section as a separate requirement with its own expected content description. Number the preprocessing steps as individual requirements (FR-3.2.1 through FR-3.2.6).

---

### 8. Failure Mode Coverage — 2.5 / 10 (Weight: 3%)

**Rationale:** The spec is designed almost entirely for the happy path. Failure modes are acknowledged in the Open Questions section (Section 9) but left unresolved. No external dependency has a specified failure behavior.

**Key Finding:** The pipeline calls at least 4 external APIs (Gmail, ArXiv, HN Algolia, LLM provider) plus RSS feeds and web scraping targets. Not a single one has a specified failure behavior. When the Gmail API returns a 403 (token expired), does the pipeline skip Gmail and continue, abort entirely, or retry? When the LLM API returns a rate limit error mid-batch, does the pipeline wait and retry, skip the batch, or fail? These are not edge cases — they are normal operating conditions for a daily-run pipeline calling multiple external services.

**Unspecified failure modes:**
- **Source fetch failures:** No behavior specified for any source connector when the API is down, returns errors, or times out.
- **Partial pipeline failures:** If 3 of 5 sources succeed and 2 fail, does the pipeline produce a digest from the 3, or abort? Not specified.
- **LLM API failures:** Rate limits, quota exhaustion, malformed responses, timeout — none addressed.
- **Empty inputs:** What if all sources return zero items? What if the LLM returns empty output? What if the cache is empty on first run?
- **Recovery/idempotency:** If the pipeline fails after Pass 1 but before writing the digest, can it be re-run? Will it re-process everything or resume? The dedup cache partially addresses this, but the behavior isn't specified.
- **Malformed external data:** What if an RSS feed returns invalid XML? What if an HN API response is missing expected fields?
- **Paywalled content:** Acknowledged as open question #1 but not resolved — "Graceful skip + flag in digest" is a tentative note, not a specification.
- **Rate limits:** Acknowledged as open question #5 but not resolved.

**Improvement to gain +2 points:** Add a "Failure Handling" section specifying: (1) the default behavior for source fetch failures (skip source, log warning, continue pipeline), (2) LLM API failure behavior (retry with exponential backoff up to N times, then skip/abort), (3) empty pipeline behavior (if zero articles remain after filtering, write a digest with a "no significant developments" message), and (4) re-run safety guarantees.

---

### 9. Interface Contracts — 4.0 / 10 (Weight: 2%)

**Rationale:** Two interface signatures are provided (`Source` ABC and `LLMClient`), which is better than nothing, but the data model types they reference are not fully defined, error conventions are absent, and empty-input behavior is unspecified at every boundary.

**Key Finding:** The `Source.fetch()` method returns `list[RawItem]`, but `RawItem` is never defined. The `Extractor` outputs `NormalizedItem list` (per data flow 4.2), but `NormalizedItem` is only partially defined (field names without types). The `Summarizer` outputs `ScoredItem list`, but `ScoredItem` doesn't exist in the spec. Two agents implementing adjacent pipeline stages would have to independently invent compatible data structures — and would likely get them wrong.

**Interface analysis:**
| Interface | Input Spec | Output Spec | Error Convention | Empty Behavior |
|---|---|---|---|---|
| `Source.fetch()` | *(implicit: self + config)* | `list[RawItem]` — **undefined type** | Not specified | Not specified |
| `Source.is_enabled()` | *(none)* | `bool` | N/A | N/A |
| `Deduplicator` | `list[RawItem]` | `list[RawItem]` *(filtered)* | Not specified | Not specified |
| `Extractor` | `list[RawItem]` | `list[NormalizedItem]` — **partial type** | Not specified | Not specified |
| `PreFilter` | `list[NormalizedItem]` | `list[NormalizedItem]` *(filtered)* | Not specified | Not specified |
| `Truncator` | `list[NormalizedItem]` | `list[NormalizedItem]` *(truncated)* | Not specified | Not specified |
| `LLMClient.complete()` | `system: str, user: str, model: str` | `str` | Not specified | Not specified |
| `Summarizer` | `list[NormalizedItem]` | `list[ScoredItem]` — **undefined type** | Not specified | Not specified |
| `Synthesizer` | `list[ScoredItem]` | `Digest` — **undefined type** | Not specified | Not specified |
| `MarkdownRenderer` | `Digest` | file on disk | Not specified | Not specified |

**Improvement to gain +2 points:** Define all four data model classes (`RawItem`, `NormalizedItem`, `ScoredItem`, `Digest`) with complete field names, types, and optionality. Specify a consistent error convention (e.g., "all pipeline stages raise `PipelineError` on unrecoverable failure; filtering stages return empty list when all items filtered out").

---

## Weighted Score Calculation

| Dimension | Weight | Score | Calculation | Weighted Score |
|---|---|---|---|---|
| Unambiguity | 0.25 | 5.5 | 0.25 x 5.5 | 1.375 |
| Completeness | 0.20 | 4.5 | 0.20 x 4.5 | 0.900 |
| Consistency | 0.15 | 5.0 | 0.15 x 5.0 | 0.750 |
| Verifiability | 0.15 | 4.0 | 0.15 x 4.0 | 0.600 |
| Implementation Guidance | 0.10 | 5.5 | 0.10 x 5.5 | 0.550 |
| Forward Traceability | 0.05 | 6.5 | 0.05 x 6.5 | 0.325 |
| Singularity | 0.05 | 5.0 | 0.05 x 5.0 | 0.250 |
| Failure Mode Coverage | 0.03 | 2.5 | 0.03 x 2.5 | 0.075 |
| Interface Contracts | 0.02 | 4.0 | 0.02 x 4.0 | 0.080 |
| **Total** | **1.00** | | | **4.905** |

---

## Top 3 Improvements by Impact

These are the changes that would most improve the weighted score, ordered by impact:

1. **Define all data models and specify prompt output formats (+1.0–1.5 weighted points).** Fully define `RawItem`, `NormalizedItem`, `ScoredItem`, and `Digest` with field names, types, and constraints. Specify the expected LLM output format for Pass 1 (JSON schema) and Pass 2 (markdown structure). This directly improves Unambiguity, Completeness, Verifiability, and Interface Contracts.

2. **Add acceptance criteria for every module (+0.8–1.2 weighted points).** Even one testable assertion per module ("Gmail source returns a list of RawItems from unread emails in configured labels within the last `max_age_days` days") dramatically improves Completeness, Verifiability, and Forward Traceability.

3. **Reconcile pipeline ordering and config schema (+0.5–0.8 weighted points).** Fix the Truncate/Pre-filter ordering contradiction between 3.2 and 4.2. Add `llm.backend` and `cache.ttl_days` to the config.yaml example. Add missing env vars. This directly fixes Consistency and reduces Unambiguity.

---

## Verdict

**Not ready for AI agent implementation.** An agent given this spec would produce code that has the right file structure and general shape, but would make divergent choices on behavioral details (filtering logic, error handling, LLM output parsing, pipeline ordering) that would require significant rework. The spec is a strong product vision document that needs one more pass focused on: data model definitions, acceptance criteria, failure handling, and internal consistency.

**Recommended next step:** Address improvements #1 and #2 above, then re-score. The spec could realistically reach 7.0+ (implementation-ready with minor clarification needed) with those two changes alone.
