# ai-radar

A configurable Python pipeline that ingests AI content from multiple sources daily,
filters for relevance, and generates a structured digest with summaries, contrarian
insights, and trend detection. Fork and configure for your own daily AI briefing.

---

## How it works

```
Sources → Dedup → Excerpt Fetch → Pre-Filter → Pass 1 (LLM) →
Full Fetch → Truncate → Pass 2 (LLM) → Markdown → Email
```

**Pass 1** scores articles on excerpts (~200 words) using a fast/cheap model. Low-scoring
articles are dropped before any full-text fetching happens.

**Pass 2** synthesizes surviving articles into a structured digest using a higher-quality
model. Runs headlessly as a GitHub Actions cron job.

---

## Setup

### 1. Install dependencies

```bash
pip install uv   # or: brew install uv
uv sync
```

### 2. Choose your LLM provider(s)

ai-radar routes all LLM calls through **[LiteLLM](https://github.com/BerriAI/litellm)**,
which supports 100+ providers with a unified interface. You configure model aliases in
`config.yaml` — the pipeline only ever calls `"fast"` or `"quality"`, so you can swap
providers without touching code.

**Supported providers (out of the box):**

| Provider | Env var | Get a key |
|---|---|---|
| GitHub Models (default) | `GH_MODELS_TOKEN` | [github.com/settings/tokens](https://github.com/settings/tokens) — classic token, no scopes |
| Anthropic | `ANTHROPIC_API_KEY` | [console.anthropic.com](https://console.anthropic.com) |
| OpenAI | `OPENAI_API_KEY` | [platform.openai.com](https://platform.openai.com) |

Any [LiteLLM-supported provider](https://docs.litellm.ai/docs/providers) works — just
add its env var and use its prefix in `config.yaml`.

### 3. Configure

```bash
cp .env.example .env
cp config.example.yaml config.yaml
```

Fill in `.env` with your API keys. The minimum required key is `GH_MODELS_TOKEN` if
you're using the default GitHub Models setup.

Edit `config.yaml`:

```yaml
profile:
  role: "AI engineer"
  interests:
    - "LLM inference and serving"
    - "agent frameworks"
  relevance_threshold: 6   # articles below this score (1–10) are dropped

sources:
  rss_feeds:
    enabled: true
    feeds:
      - name: "Anthropic Blog"
        url: "https://www.anthropic.com/blog/rss"

llm:
  backend: "litellm"
  models:
    fast: "github/gpt-4o-mini"          # Pass 1 — optimise for cost
    quality: "github/gpt-4o"            # Pass 2 — optimise for quality
    fast_fallback: "anthropic/claude-haiku-4-5-20251001"
    quality_fallback: "anthropic/claude-haiku-4-5-20251001"
```

**Model alias rules:**
- `fast` / `quality` — primary models for Pass 1 and Pass 2
- `fast_fallback` / `quality_fallback` — used automatically if the primary returns a
  service error (429, 5xx). No code change required to switch providers.

### 4. Run

```bash
# Validate config and credentials before your first real run
python -m radar check

# Run the pipeline
python -m radar run
```

Digests are written to `./digests/briefing_{date}.md` by default.

---

## Observability with Langfuse (optional)

**[Langfuse](https://langfuse.com)** traces every LLM call — inputs, outputs, latency,
token counts — so you can debug prompt quality and catch regressions when you change
prompts.

### Setup

1. Create a free account at [cloud.langfuse.com](https://cloud.langfuse.com)
2. Create a project (e.g. `ai-radar`)
3. Go to **Settings → API Keys** and copy your public and secret keys
4. Add to `.env`:

```bash
LANGFUSE_PUBLIC_KEY=pk-lf-...
LANGFUSE_SECRET_KEY=sk-lf-...
LANGFUSE_HOST=https://cloud.langfuse.com  # omit if using cloud; override for self-hosted
```

Tracing activates automatically when both keys are present. If the keys are absent,
the pipeline runs normally with no tracing — there's no config toggle required to
disable it.

### What gets traced

Each pipeline run records two generations:

| Trace tag | What it covers |
|---|---|
| `pipeline_stage: pass_1` | Every Pass 1 (summarizer) LLM call — one per batch |
| `pipeline_stage: pass_2` | The Pass 2 (synthesizer) LLM call |

Traces also include `prompt_version` (from `config.yaml`) so you can filter by version
and detect quality changes after prompt edits.

### Self-hosted Langfuse

Set `LANGFUSE_HOST` in `.env` to your instance URL (e.g. `http://localhost:3000`).
Everything else works the same.

---

## Changing providers

No code changes are needed. Edit `config.yaml` and set the appropriate env var:

```yaml
# Switch Pass 2 to Anthropic
llm:
  models:
    quality: "anthropic/claude-opus-4-7"
    quality_fallback: "anthropic/claude-haiku-4-5-20251001"
```

```bash
# .env
ANTHROPIC_API_KEY=sk-ant-...
```

LiteLLM provider prefixes: `github/`, `anthropic/`, `openai/`, `azure/`,
`cohere/`, `together_ai/`, and [many more](https://docs.litellm.ai/docs/providers).

---

## GitHub Actions (daily cron)

The included `.github/workflows/daily-briefing.yml` runs the pipeline on a schedule
and uploads the digest as a workflow artifact.

Add your secrets to **Settings → Secrets and variables → Actions**:

```
GH_MODELS_TOKEN
ANTHROPIC_API_KEY      (if using Anthropic fallbacks)
LANGFUSE_PUBLIC_KEY    (if using Langfuse)
LANGFUSE_SECRET_KEY    (if using Langfuse)
GMAIL_CLIENT_ID        (if sources.gmail.enabled = true)
GMAIL_CLIENT_SECRET
GMAIL_REFRESH_TOKEN
```

Trigger a manual run first via **Actions → daily-briefing → Run workflow** to confirm
everything works before the cron fires.

---

## Development

```bash
make check     # lint + typecheck + full test suite (required before PR)
make test      # tests only
make lint      # ruff check + format check
make typecheck # mypy --strict
```
