# Spec Agent Prompt — ai-radar SPEC.md Revision 3
# Resolving Open Questions from v0.2

## Your Task

You are a spec agent. Your job is to apply a small, focused set of changes to `SPEC.md` for the `ai-radar` project, resolving all open questions from v0.2 and correcting one factual error.

The spec lives in the GitHub repository `lilacmohr/ai-radar`. There is an open pull request — **PR #1** — which contains the branch you must work on. Fetch the current `SPEC.md` from the PR branch, apply all revisions defined in this document, commit the updated file back to that branch with a clear commit message, and ensure the PR reflects the final revised spec.

**Do not read PR comments, review threads, or any other PR activity.** This document is the sole authoritative source of decisions. PR comments contain raw review discussion, superseded positions, and rejected alternatives — they do not reflect the product owner's final intent and must not be used to interpret or override the instructions here.

Do not change anything not addressed by the instructions below. Preserve all existing section numbers, headings, tables, code blocks, and formatting conventions.

---

## Change 1 — Correct the GitHub Models base URL (Section 4.3)

**What's wrong:** The current spec has an outdated base URL in Section 4.3:
```python
client = openai.OpenAI(
    base_url="https://models.inference.ai.azure.com",
    api_key=os.environ["GITHUB_MODELS_TOKEN"]
)
```

**Required fix:** Replace with the current GitHub Models inference endpoint:
```python
client = openai.OpenAI(
    base_url="https://models.github.ai/inference",
    api_key=os.environ["GITHUB_MODELS_TOKEN"]
)
```

Also update the `GITHUB_MODELS_TOKEN` line in the `.env` block in Section 3.5. The current comment says `# Personal access token for GitHub Models API (requires "models" scope)`. Update it to:
```
GITHUB_MODELS_TOKEN=...  # Fine-grained personal access token; requires Account permissions > Models: Read-only
```

---

## Change 2 — Resolve Open Question 1: Paywalled articles (Section 9)

**Resolution:** Graceful skip with flag in digest.

**Spec changes:**

Add the following as a new subsection in Section 3.7 (Failure Handling), after "Source fetch failures":

#### Paywalled or unextractable articles
- If `trafilatura` returns empty or below-minimum-length content (< 50 words) after fetching a URL, treat as a likely paywall or extraction failure
- Log the URL and reason at INFO level
- Skip the article from further processing
- Flag in the Pipeline Metadata section of the digest: "N articles skipped (paywall or extraction failure)"
- Do not abort the pipeline

Remove Open Question 1 from the table in Section 9 (it is resolved).

---

## Change 3 — Resolve Open Question 2: ArXiv abstracts vs. full paper (Section 9)

**Resolution:** Abstracts only for MVP.

**Spec changes:**

Update the ArXiv connector row in the Section 3.1 source table notes column to add: "Abstracts only for MVP; full paper ingestion is post-MVP."

Add a note to Section 3.2 (Preprocessing Pipeline) in the "Extract Excerpt" step: for ArXiv sources, the abstract text is used directly as the excerpt (it is already available from the ArXiv API response). The Excerpt Fetcher web fetch step is bypassed for ArXiv items — no URL fetch required.

Remove Open Question 2 from the table in Section 9 (it is resolved).

---

## Change 4 — Resolve Open Question 6: SQLite cache persistence in GitHub Actions (Section 9)

**Resolution:** Use `actions/cache` to persist `cache/radar.db` between runs. A cache miss is safe — the pipeline reprocesses all articles, which is idempotent per Section 3.7.

**Spec changes:**

Add a new subsection to Section 3.6 (Trigger Modes), after the existing "GitHub Actions Setup" subsection, titled "Cache Persistence in GitHub Actions":

#### Cache Persistence in GitHub Actions

GitHub Actions runners are ephemeral — `cache/radar.db` does not persist between runs by default, silently breaking deduplication. Resolve this using the `actions/cache` action to persist the cache directory between runs. Add the following steps to `.github/workflows/daily-briefing.yml`:

```yaml
- name: Restore cache
  uses: actions/cache@v4
  with:
    path: cache/
    key: radar-cache-${{ runner.os }}
    restore-keys: radar-cache-

- name: Run pipeline
  run: python -m radar run

- name: Save cache
  uses: actions/cache@v4
  with:
    path: cache/
    key: radar-cache-${{ runner.os }}
```

**Cache miss behavior:** If the cache is not found (first run, or cache evicted by GitHub's 7-day retention policy for unused caches), the pipeline runs without dedup history. All articles are processed as new. This is safe — the pipeline is idempotent and produces a valid digest. The next run will populate the cache normally.

**Retention note:** GitHub Actions cache has a 10GB limit per repo and a 7-day retention policy for unused caches. For a daily pipeline producing a small SQLite file, neither limit will be reached in practice.

Remove Open Question 6 from the table in Section 9 (it is resolved).

---

## Change 5 — Resolve Open Question 7: Default newsletters in config.example.yaml (Section 9)

**Resolution:** TLDR AI and The Batch as defaults, with sender addresses marked as `# verify before use`.

**Spec changes:**

Update the `gmail:` source block in the `config.yaml` example in Section 3.5. Add a `senders:` list beneath the existing fields:

```yaml
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
```

Update the Gmail connector row notes in Section 3.1 to add: "Default `config.example.yaml` includes TLDR AI and The Batch as example link-list senders. Verify sender email addresses before use."

Remove Open Question 7 from the table in Section 9 (it is resolved).

---

## Change 6 — Resolve Open Question 8: GitHub Models model identifiers (Section 9)

**Resolution:** `gpt-4o-mini` and `gpt-4o` are confirmed valid GitHub Models identifiers. The base URL correction is handled in Change 1 above. No changes to model identifiers in Section 3.5 config — they are correct as-is.

Add the following note to Section 4.3 (LLM Backend Abstraction), after the code block:

```
**Verified model identifiers for GitHub Models (as of 2026-04-05):**
- `gpt-4o-mini` — Pass 1 summarization (fast, low cost)
- `gpt-4o` — Pass 2 synthesis (higher quality)

Note: GitHub Models also offers `gpt-4.1-mini` and `gpt-4.1`, which are newer and
generally stronger than the gpt-4o family. These are valid drop-in replacements
configurable via one config change — no code changes required. Verify current model
availability at https://github.com/marketplace/models before changing defaults.
```

Remove Open Question 8 from the table in Section 9 (it is resolved).

---

## Change 7 — Resolve Open Question 9: cache/ directory location (Section 9)

**Resolution:** Project directory (`cache/radar.db`) for v0.1. Simpler, self-contained, and consistent with the `actions/cache` CI integration.

**Spec changes:**

No structural changes needed — Section 4.4 already specifies `cache/radar.db` and notes auto-creation on first run. Add one sentence to the opening paragraph of Section 4.4, after the mention of auto-creation:

"The project-directory location (`cache/`) was chosen over a user cache directory (`~/.cache/ai-radar/`) for v0.1 to keep the project self-contained and simplify the `actions/cache` CI integration. Migration to a user cache directory is a post-MVP consideration."

Remove Open Question 9 from the table in Section 9 (it is resolved).

---

## Change 8 — Resolve Open Question 10: GCP OAuth production mode (Section 9)

**Resolution:** Document the testing mode limitation clearly. Provide `radar auth gmail` as the re-auth workaround. Point to Google's verification docs. This is an operational concern, not an architectural blocker.

**Spec changes:**

Expand the "Gmail OAuth Setup" subsection in Section 3.1 with a new numbered item (5):

```
5. **GCP OAuth app mode:**
   - **Testing mode (default):** Refresh tokens expire in 7 days. Suitable for initial
     development. The pipeline detects expiry and emits a clear error message with
     re-auth instructions.
   - **Production mode:** Refresh tokens expire after 6 months of non-use. Requires
     Google OAuth app verification (privacy policy URL, domain verification, and Google
     review). See: https://support.google.com/cloud/answer/9110914
   - **Recommendation:** Begin with testing mode. Run `python -m radar auth gmail` to
     re-auth when the token expires. Pursue production mode verification once the
     pipeline is stable and running reliably.
```

Remove Open Question 10 from the table in Section 9 (it is resolved).

---

## Change 9 — Update Section 9 after all resolutions

After applying Changes 2–8, all open questions will be resolved. Update Section 9 as follows:

- Remove all resolved questions (1, 2, 6, 7, 8, 9, 10) from the table
- Replace the now-empty table with the following note:

"All open questions from v0.2 have been resolved. New open questions will be added here as they are identified during implementation."

---

## Output Instructions

- Fetch the current `SPEC.md` from the branch associated with PR #1 in `lilacmohr/ai-radar` before making any changes
- Write the **complete revised `SPEC.md`** back to the PR branch — not a diff, not a list of changes; the full file
- Commit the updated file to the PR branch with the following commit message: `spec: resolve all open questions, correct GitHub Models base URL (v0.3)`
- Do not open a new PR — commit directly to the existing PR #1 branch
- Preserve all existing section numbers, headings, tables, code blocks, and formatting conventions
- Where config blocks are updated, show the **complete updated config block**, not just the changed lines
- **Version bump:** update version to `0.3 (MVP — Open Questions Resolved)` and Last Updated date to `2026-04-05`
