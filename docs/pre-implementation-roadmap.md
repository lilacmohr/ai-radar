# ai-radar — Pre-Implementation Roadmap

> **Project:** ai-radar (daily briefing pipeline)
> **Meta-goal:** AI Engineering Playbook — ai-radar is the reference implementation.
> **Agent:** Claude Code | **Issues:** GitHub Issues | **Priority:** Process first, then ship.
> **Last updated:** 2026-04-09 (P3 complete — all sources and processing modules done)

---

## Status Legend

| Symbol | Meaning |
|---|---|
| ✅ | Complete |
| 🔄 | In progress |
| ⬜ | Not started |
| 🔒 | Blocked by dependency |

---

## Spec Quality

| Version | Score | Date | Status |
|---|---|---|---|
| v0.1 | 4.91 / 10 | 2026-04-04 | Too ambiguous to implement |
| v0.3 | 7.34 / 10 | 2026-04-05 | ✅ Implementation-ready |

**Remaining spec gaps (deferred, not blocking):**
- Per-module acceptance criteria (emerging from TDD test files — P2 test files now serve this purpose)
- Processing module method signatures (agents will raise DECISION NEEDED as needed)

---

## Pre-Implementation Phases

### Phase P0 — Agent Infrastructure
*What the agent needs to be effective from the very first session.*
*Produces config and tooling files, not application code.*

| # | Artifact | Status | Notes |
|---|---|---|---|
| P0.1 | `CLAUDE.md` | ✅ | Agent briefing + engineering standards. 11 sections covering autonomy, conventions, TDD protocol, failure handling, quality gates, and playbook rationale. |
| P0.2 | GitHub Issue Templates | ✅ | 4 templates: `[TEST]`, `[IMPL]`, `[SCAFFOLD]`, `[DECISION]`. TDD pairing enforced by template structure. `[DECISION]` issues track spec gaps as they surface. |
| P0.3 | Claude Hooks | ✅ | 4 hooks wired in `.claude/settings.json`: SessionStart (context injection), PreToolUse (prevention gate), PostToolUse (lint + mypy per file), Stop (test suite completion gate). |
| P0.4 | Phase 0 Ticket Set | ✅ | GitHub Issues for all scaffolding work, written in `[SCAFFOLD]` template format, ready to hand to Claude Code. Issues #3–#11. |
| P0.5 | Prompt Templates | ✅ | Pass 1 + Pass 2 prompts in `radar/llm/prompts.py`. Configurable via profile injection. Closes spec gap #1. |

---

### Phase P1 — Repo Scaffolding
*Executed via `[SCAFFOLD]` GitHub Issues. No application code.*
*All work is configuration, tooling, and project structure.*

| # | Deliverable | Status | Issue | Blocks |
|---|---|---|---|---|
| P1.1 | Repo structure | ✅ | [#3](https://github.com/lilacmohr/ai-radar/issues/3) | Everything |
| P1.2 | `pyproject.toml` + `uv` | ✅ | [#4](https://github.com/lilacmohr/ai-radar/issues/4) | All Python work |
| P1.3 | `ruff` + `mypy` config | ✅ | [#5](https://github.com/lilacmohr/ai-radar/issues/5) | Hooks (post_edit_lint.sh) |
| P1.4 | `Makefile` | ✅ | [#6](https://github.com/lilacmohr/ai-radar/issues/6) | Hooks (stop_run_tests.sh), CI |
| P1.5 | `.env.example` + `config.example.yaml` | ✅ | [#7](https://github.com/lilacmohr/ai-radar/issues/7) | Source connectors |
| P1.6 | `tests/conftest.py` + `TestLLMClient` mock | ✅ | [#8](https://github.com/lilacmohr/ai-radar/issues/8) | All LLM-dependent tests |
| P1.7 | Test fixture directory + sample fixtures | ✅ | [#9](https://github.com/lilacmohr/ai-radar/issues/9) | Source connector tests |
| P1.8 | `AGENTS.md` | ✅ | [#10](https://github.com/lilacmohr/ai-radar/issues/10) | Documentation |
| P1.9 | GitHub Actions workflow skeleton | ✅ | [#11](https://github.com/lilacmohr/ai-radar/issues/11) | CI/CD |

*Done when: `make check` runs clean on an empty `radar/__init__.py`.* ✅ Complete — PR merged 2026-04-07.

---

### Phase P2 — Foundation (TDD)
*First `[TEST]` / `[IMPL]` pairs. Pure logic, no external I/O.*
*Everything downstream depends on these types and interfaces.*

| # | Test Issue | Impl Issue | Module | Status | Spec Ref |
|---|---|---|---|---|---|
| P2.1 | [#14](https://github.com/lilacmohr/ai-radar/issues/14) ✅ | [#17](https://github.com/lilacmohr/ai-radar/issues/17) ✅ | `radar/models.py` | ✅ | §3.1, §4.2 |
| P2.2 | [#15](https://github.com/lilacmohr/ai-radar/issues/15) ✅ | [#18](https://github.com/lilacmohr/ai-radar/issues/18) ✅ | `radar/config.py` | ✅ | §3.5 |
| P2.3 | [#16](https://github.com/lilacmohr/ai-radar/issues/16) ✅ | [#19](https://github.com/lilacmohr/ai-radar/issues/19) ✅ | `radar/cache.py` | ✅ | §4.4 |

*Done when: all dataclasses defined, config loads and validates, cache reads/writes correctly.* ✅ Complete — PR #27 merged 2026-04-08.

---

### Phase P3 — Sources & Processing (TDD)
*Deterministic modules. No LLM cost. Full TDD possible.*
*Build one source end-to-end before building the rest.*

| # | Test Issue | Impl Issue | Module | Status | Spec Ref |
|---|---|---|---|---|---|
| P3.1 | [#29](https://github.com/lilacmohr/ai-radar/issues/29) ✅ | [#30](https://github.com/lilacmohr/ai-radar/issues/30) ✅ | `Source` ABC (`radar/sources/base.py`) | ✅ | §3.1 |
| P3.2 | [#31](https://github.com/lilacmohr/ai-radar/issues/31) ✅ | [#32](https://github.com/lilacmohr/ai-radar/issues/32) ✅ | RSS connector (`radar/sources/rss.py`) | ✅ | §3.1 |
| P3.3 | [#43](https://github.com/lilacmohr/ai-radar/issues/43) ✅ | [#44](https://github.com/lilacmohr/ai-radar/issues/44) ✅ | HN connector (`radar/sources/hn.py`) | ✅ | §3.1 |
| P3.4 | [#56](https://github.com/lilacmohr/ai-radar/issues/56) ✅ | [#57](https://github.com/lilacmohr/ai-radar/issues/57) ✅ | ArXiv connector (`radar/sources/arxiv.py`) | ✅ | §3.1 |
| P3.5 | [#58](https://github.com/lilacmohr/ai-radar/issues/58) ✅ | [#59](https://github.com/lilacmohr/ai-radar/issues/59) ✅ | Gmail connector (`radar/sources/gmail.py`) | ✅ | §3.1 (OAuth) |
| P3.6 | [#39](https://github.com/lilacmohr/ai-radar/issues/39) ✅ | [#40](https://github.com/lilacmohr/ai-radar/issues/40) ✅ | `deduplicator.py` (Phase 1 + 2) | ✅ | §3.2 steps 2, 5 |
| P3.7 | [#54](https://github.com/lilacmohr/ai-radar/issues/54) ✅ | [#55](https://github.com/lilacmohr/ai-radar/issues/55) ✅ | `excerpt_fetcher.py` | ✅ | §3.2 step 4 |
| P3.8 | [#41](https://github.com/lilacmohr/ai-radar/issues/41) ✅ | [#42](https://github.com/lilacmohr/ai-radar/issues/42) ✅ | `pre_filter.py` | ✅ | §3.2 step 6 |

*Done when: pipeline runs from source fetch through pre-filter with no LLM calls, producing a `list[ExcerptItem]`.* ✅ Complete — all P3 modules merged 2026-04-09. 284 tests passing.

---

### Phase P4 — LLM Pipeline (TDD)
*Depends on real preprocessing output from Phase P3.*
*Prompt templates (P0.5) must exist before these tickets are written.*

| # | Test Issue | Impl Issue | Module | Status | Spec Ref |
|---|---|---|---|---|---|
| P4.1 | `[TEST]` | `[IMPL]` | `LLMClient` (GitHub Models) | ⬜ | §4.3 |
| P4.2 | `[TEST]` | `[IMPL]` | `summarizer.py` (Pass 1) | ⬜ | §3.3 |
| P4.3 | `[TEST]` | `[IMPL]` | `full_fetcher.py` | ⬜ | §3.2 step 7 |
| P4.4 | `[TEST]` | `[IMPL]` | `truncator.py` | ⬜ | §3.3 |
| P4.5 | `[TEST]` | `[IMPL]` | `synthesizer.py` (Pass 2) | ⬜ | §3.3 |

*Done when: pipeline runs end-to-end from `ExcerptItem` list through `Digest`, using `TestLLMClient` mock for unit tests.*

---

### Phase P5 — Output & Wiring (TDD)
*Connects everything. CLI + pipeline orchestration + email delivery.*

| # | Test Issue | Impl Issue | Module | Status | Spec Ref |
|---|---|---|---|---|---|
| P5.1 | `[TEST]` | `[IMPL]` | `markdown.py` | ⬜ | §3.4 |
| P5.2 | `[TEST]` | `[IMPL]` | `pipeline.py` | ⬜ | §4.2 |
| P5.3 | `[TEST]` | `[IMPL]` | `__main__.py` (CLI) | ⬜ | §3.6 |
| P5.4 | `[SCAFFOLD]` | — | GitHub Actions workflow (full) | ⬜ | §3.6 |
| P5.5 | `[SCAFFOLD]` | — | `examples/sample-briefing.md` | ⬜ | §7 |

*Done when: `python -m radar run` produces a digest file end-to-end. `radar check` validates config and credentials.*

---

## Dependency Graph

```
Spec v0.3 (✅)
    │
    ├── P0: Agent Infrastructure
    │       ├── CLAUDE.md (✅)
    │       ├── Issue Templates (✅)
    │       ├── Claude Hooks (✅)
    │       ├── Phase 0 Ticket Set (✅)
    │       └── Prompt Templates (✅)
    │
    └── P1: Repo Scaffolding (✅)
            │
            └── P2: Foundation — models, config, cache (✅)
                    │
                    └── P3: Sources & Processing (✅ — all complete)
                            │
                            ├── [Prompt Templates required here]
                            │
                            └── P4: LLM Pipeline (⬜)
                                    │
                                    └── P5: Output & Wiring (⬜)
                                                │
                                                └── 🚀 First end-to-end run
```

---

## Playbook Artifacts Produced So Far

These are the reusable assets being built for the AI Engineering Playbook,
using ai-radar as the reference implementation.

| Artifact | Purpose in Playbook | Status |
|---|---|---|
| Spec quality scorecard (v0.1 → v0.3) | How to evaluate and improve a spec before handing to agents | ✅ |
| `CLAUDE.md` | Template for briefing AI agents on a codebase; scales to team standard | ✅ |
| GitHub Issue templates (`[TEST]`, `[IMPL]`, `[SCAFFOLD]`, `[DECISION]`) | Standardized agent task format enforcing TDD pairing | ✅ |
| Claude hooks suite | Enforcement layer separating advisory (CLAUDE.md) from deterministic (hooks) | ✅ |
| This roadmap | Pre-implementation phase structure for AI-first projects | ✅ |
| Phase 0 ticket set | Example `[SCAFFOLD]` issues, fully filled out | ✅ |
| Prompt template pattern | How to treat prompts as code (versionable, reviewable) | ⬜ (prompts.py ✅; playbook-notes entry still needed) |
| TDD workflow with AI agents | `[TEST]` → `[IMPL]` pairing in practice, with hook enforcement | 🔄 (10 pairs complete: P2.1–P2.3, P3.1–P3.8) |
| ADR / decision log | How `[DECISION]` issues capture architectural decisions as permanent record | ⬜ |

---

## Key Decisions Made

| Decision | Rationale | Where documented |
|---|---|---|
| Process-first (playbook over ship speed) | ai-radar is a case study; the process artifacts are the primary output | This doc |
| Claude Code as agent | Best CLAUDE.md + hooks integration; terminal-native | `CLAUDE.md` |
| GitHub Issues for tickets | Native `gh` CLI integration with Claude Code; issues are permanent record | Issue templates |
| TDD: `[TEST]` before `[IMPL]` | Test file = executable acceptance criteria; prevents spec drift | `CLAUDE.md §6`, issue templates |
| `[DECISION]` issues for ambiguity | Surfaces spec gaps as trackable artifacts, not silent agent choices | Issue template |
| Python 3.12 + strict mypy | Stage-boundary type safety; dataclasses for all pipeline models | `CLAUDE.md §4` |
| Hooks = enforcement, CLAUDE.md = advisory | Separates "must happen" from "should happen"; hooks are deterministic | `CLAUDE.md`, hooks |
| `settings.local.json` as escape valve | Hooks must be sustainable; engineers need a bypass for spikes | Hook docs |
| Prompt templates as constants in `prompts.py` | Prompts are code — versionable, reviewable, independently testable | `CLAUDE.md §8` |

---

## Next Actions

1. **✅ Phase 0 ticket set** — `[SCAFFOLD]` GitHub Issues #3–#11 created for P1.1–P1.9
2. **✅ Prompt templates** — Pass 1 + Pass 2 prompts in `radar/llm/prompts.py` (P0.5)
3. **✅ P1 complete** — Scaffolding merged 2026-04-07
4. **✅ P2 complete** — [IMPL] issues #17, #18, #19 merged in PR #27 (2026-04-08); 87 tests passing
5. **✅ P3 issue creation** — Issues #29–#32 created for P3.1 + P3.2 (2026-04-08)
6. **✅ P3.1 complete** — Source ABC (issues #29, #30; PRs #33, #35) merged 2026-04-08; 111 tests passing
7. **✅ P3.2 complete** — RSS connector (issues #31, #32; PRs #36, #37) merged 2026-04-08; 111 tests passing
8. **✅ P3.8 complete** — `pre_filter.py` (issues #41, #42; PRs #45, #46) merged 2026-04-08
9. **✅ P3.6 complete** — `deduplicator.py` (issues #39, #40; PRs #48, #49) merged 2026-04-08
10. **✅ P3.3 complete** — HN connector (issues #43, #44; PRs #51, #52) merged 2026-04-08
11. **✅ P3.7 complete** — `excerpt_fetcher.py` (issues #54, #55; PRs #60, #61) merged 2026-04-09
12. **✅ P3.4 complete** — ArXiv connector (issues #56, #57; PRs #62, #63) merged 2026-04-09
13. **✅ P3.5 complete** — Gmail connector (issues #58, #59; PRs #66, #67) merged 2026-04-09; decision issues #64, #65 opened
14. **⬜ P4** — LLM pipeline; P3 is the prerequisite, now unblocked
