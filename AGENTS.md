# AGENTS.md — ai-radar Agentic Development Guide

> **Who this file is for:** Engineers (human and AI) joining this project.
> **What it covers:** The agentic development workflow used to build ai-radar,
> including issue formats, TDD protocol, hook enforcement, and review expectations.
>
> *ai-radar is the reference implementation for the AI Engineering Playbook —
> a reusable pattern for AI-assisted software development at team scale.*

---

## Overview

ai-radar is built using a structured agentic development workflow where Claude Code
acts as the primary implementation agent. Every contribution — scaffolding, tests,
and implementation — flows through a consistent process designed to produce
reviewable, verifiable work product.

The goal is not to move faster than a human engineer in a single session. It is to
build a system where any agent or engineer, joining at any point, can pick up a task,
execute it correctly, and hand it off cleanly — with no institutional memory required.

---

## Starting a Claude Code Session

1. **Read `CLAUDE.md` first.** It is the encoded contract between this codebase and
   every contributor. It covers autonomy rules, coding standards, failure handling
   conventions, testing standards, and quality gates.

2. **Pick up a GitHub Issue.** Issues are written in one of four templates:
   - `[SCAFFOLD]` — repo structure, tooling, CI, configuration (no paired test)
   - `[TEST]` — write the test file first; all tests must be red before implementation begins
   - `[IMPL]` — implement until the paired `[TEST]` issue's tests are green
   - `[DECISION]` — surface a spec ambiguity as a trackable artifact; do not silently choose

3. **Run `make check` before declaring a task complete.** The Stop hook enforces this.

---

## TDD Workflow

Every application module is delivered as a `[TEST]` / `[IMPL]` pair:

```
[TEST] radar/models.py   →   write tests, all red (no implementation yet)
        ↓
[IMPL] radar/models.py   →   implement until all tests are green
```

**Do not write implementation code until the test file exists and is failing.**
The Pre-Tool-Use hook will warn if an implementation file is created before its
corresponding test file.

Tests define the acceptance criteria. If the spec is ambiguous, the test file is
the place where that ambiguity is resolved — not silently inside the implementation.

### Test structure

```
tests/
  unit/          # pure logic, no I/O, no network calls
  contract/      # interface compliance (Source ABC, LLMClient)
  integration/   # multi-stage pipeline with all external calls mocked
  fixtures/      # static sample data files (one per source type)
```

Use `TestLLMClient` (defined in `tests/conftest.py`) for all LLM calls in unit and
contract tests. Never make real API calls in automated tests.

---

## Hook Enforcement

Four hooks run automatically in every Claude Code session, configured in
`.claude/settings.json`. These are deterministic enforcement — not advisory.

| Hook | Trigger | What it does |
|---|---|---|
| **SessionStart** | Beginning of every session | Injects project context: current branch, open issues, last `make check` result |
| **PreToolUse** | Before any file write or bash command | Prevention gate: blocks creating implementation files before test files exist; warns on direct `pip install` (use `uv`) |
| **PostToolUse** | After any Python file edit | Runs `ruff check` and `mypy` on the edited file immediately; surfaces errors inline before the agent moves on |
| **Stop** | When the agent signals task completion | Runs `make check`; blocks the session from ending if lint, typecheck, or tests are failing |

The Stop hook is the primary quality gate. An agent cannot mark a task complete
if `make check` is failing. This makes it impossible to leave the repo in a broken
state between sessions.

If you need to bypass hooks during a spike or local experiment, create
`.claude/settings.local.json` with `{"hooks": {}}`. This file is gitignored.
Do not disable hooks in the committed `settings.json`.

---

## Decision Protocol

When you encounter a spec ambiguity that would lead to structurally different code
depending on interpretation, do not silently choose. Instead:

1. Open a `[DECISION]` GitHub Issue using the decision template
2. Format the decision as:
   ```
   DECISION NEEDED: [one-line description]
   Options:
     A) [option] — [consequence]
     B) [option] — [consequence]
   Spec reference: [section]
   Recommendation: [your recommendation and why]
   ```
3. Block on the decision. Do not implement both options speculatively.

You may proceed autonomously for: variable names, private helper signatures,
additional test cases beyond those specified, type aliases, and constants.

---

## Quality Gates

A task is **done** when all of the following are true:

- [ ] `make check` passes with zero errors (lint + typecheck + tests)
- [ ] All tests specified in the paired `[TEST]` issue pass
- [ ] All failure modes for this module are covered by tests (see `CLAUDE.md §5`)
- [ ] All new functions have explicit return type annotations
- [ ] All new log calls use structured `key=value` format (no f-strings in log calls)
- [ ] No new bare `except` clauses introduced
- [ ] No new untyped dicts used as data carriers between pipeline stages

These gates are enforced by the Stop hook. They are not negotiable.

---

## Reviewing Agent-Authored PRs

AI-generated PRs are reviewed the same way as human-authored PRs. The issue templates
provide a guaranteed minimum: every `[IMPL]` PR arrives with a passing test suite,
clean lint, and passing type checks. Reviewers should focus on:

**What to check:**
- Does the implementation match the spec reference in the issue?
- Are the tests testing the right things, or just testing that the code runs?
- Are all failure modes from `CLAUDE.md §5` covered by tests?
- Is the public interface (method signatures, model fields) consistent with adjacent stages?

**What to trust:**
- `make check` passed — the CI confirms lint, typecheck, and tests are green
- No bare excepts — the PostToolUse hook flagged and the agent fixed any that appeared
- Structured logging — the ruff `LOG` rules catch f-strings in log calls

**`[DECISION]` issues in the PR:** If the agent opened a `[DECISION]` issue during
implementation, that issue represents a genuine ambiguity that needs human resolution.
Review it as a first-class part of the PR review.

---

## For the AI Engineering Playbook

ai-radar exists as a case study. The process artifacts are the primary output:

| Artifact | Playbook purpose |
|---|---|
| `CLAUDE.md` | Template for briefing AI agents on a codebase |
| Issue templates (`[TEST]`, `[IMPL]`, `[SCAFFOLD]`, `[DECISION]`) | Standardized agentic task format |
| Hook suite (`.claude/settings.json`) | Enforcement layer separating advisory from deterministic |
| This file | Onboarding guide for new agents and engineers |
| `docs/roadmap.md` | Full project phase structure and completion status |

The pattern is designed to scale: the same workflow that works for one agent works
for a team of agents and engineers, because every session starts from the same
verified baseline.
