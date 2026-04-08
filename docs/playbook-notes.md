# CLAUDE.md — Playbook Notes

> **Audience:** Engineering leaders and AI enablement roles.
> **What this is:** The rationale behind decisions in `CLAUDE.md` and guidance
> on maintaining it at team scale. This file is for humans, not agents.
> It is intentionally kept separate from `CLAUDE.md` to avoid consuming
> agent instruction budget with content the agent doesn't need.

---

## Why CLAUDE.md exists as a file (not just prompt instructions)

Prompt instructions are ephemeral — they live in a session and disappear. `CLAUDE.md`
is version-controlled alongside the code it governs. When your standards evolve, the
history of *why* they changed is preserved in git. Every agent session starts from
the same baseline regardless of who initiates it.

At team scale, this matters more: ten engineers running ten agent sessions will
produce consistent behavior if they all start from the same `CLAUDE.md`. Without it,
each session inherits only whatever context the engineer happened to include in their
prompt — which varies significantly between people and across time.

---

## Why decisions and rationale are included (not just rules)

A rule without rationale gets cargo-culted or silently violated when an agent or
engineer can't see why it matters. Rationale enables judgment: "the reason for this
rule doesn't apply in this situation" is a valid, surfaceable observation. "I didn't
know why the rule existed so I ignored it" is not.

This is the key distinction between a briefing document and a style guide. A style
guide says what. A briefing document says what and why — which is what enables the
agent to handle edge cases the rules don't explicitly cover.

---

## How to maintain this file at team scale

- `CLAUDE.md` is owned by the team lead or AI enablement role, not individual engineers
- Changes require the same review process as architecture changes
- Add a section when a new cross-cutting concern is introduced (new external service,
  new failure mode, new testing pattern)
- **Remove** rules that are *only* enforced by linters (ruff, mypy) and have no
  behavioral rationale the agent needs to understand — pure formatting rules,
  import ordering, etc. These are noise the agent doesn't need in its context window.
- **Keep** rules that are also enforced by hooks (Stop gate, PreToolUse guards,
  PostToolUse lint). The agent should understand *why* a rule exists even when a hook
  guarantees it. Hook enforcement provides the guarantee; the CLAUDE.md entry provides
  the judgment context that lets the agent handle edge cases correctly.
- Keep it under ~2,500 words. Beyond that, instruction quality degrades as the agent
  prioritizes recent context over earlier content in long sessions

---

## The CLAUDE.md → onboarding pipeline

New engineer onboarding = README (what) + SPEC.md (why/what in detail) + CLAUDE.md
(how we work). An engineer who has read all three should be able to open a GitHub
Issue and implement a module without a synchronous conversation. That's the bar.

This also means `CLAUDE.md` is the right place to capture things that would otherwise
live only in onboarding conversations, PR review comments, or a senior engineer's
memory — conventions that are real but unwritten.

---

## Signals this file needs updating

- An agent makes the same "wrong" decision twice → the convention isn't clear enough
- A PR review comment appears more than once → encode it as a rule
- A new engineer asks a question that isn't answered here → add it
- A rule is being systematically ignored → either enforce it with tooling or remove it
- The file grows past ~2,500 words → audit for content that can move to tooling or
  be referenced rather than included inline

---

## The relationship between CLAUDE.md and hooks

These two artifacts enforce standards at different layers and serve different purposes.
Understanding the distinction prevents both under-engineering (relying on CLAUDE.md
alone) and over-engineering (duplicating everything in hooks).

| | CLAUDE.md | Hooks |
|---|---|---|
| **Nature** | Advisory — agent reads and generally follows | Deterministic — runs regardless of what agent decides |
| **Purpose** | Context, rationale, standards the agent internalizes | Enforcement of non-negotiable quality gates |
| **Failure mode** | Agent may deprioritize in long sessions | Hook mis-configuration can block or loop |
| **Right for** | Conventions, judgment calls, architectural context | Binary pass/fail checks, completion gates |

Overlap between the two is expected and healthy for the most critical rules — the agent
should both understand why a rule exists (CLAUDE.md) and be unable to accidentally
violate it (hooks). For purely mechanical rules (formatting, import order), prefer
tooling enforcement and remove the CLAUDE.md entry — it's noise the agent doesn't need.

---

---

## TDD and the enforcement layer: teach your hooks the TDD lifecycle

The "test suite must pass before committing" quality gate directly conflicts with TDD
red-phase commits, where failing tests are the *output*, not a problem. This collision
is predictable but easy to miss when designing hooks — most hook designs are written
during green-phase work and don't account for the red phase at all.

**The fix is simple:** branches matching a naming convention (`test/*`, or whatever you
establish) are TDD red-phase branches where failing tests are expected. Your commit gate
and completion gate should both recognize this pattern and adjust accordingly: lint and
typecheck still apply everywhere, but the test gate is waived on red-phase branches.

**Do this before the first red-phase PR, not after.** Discovering the conflict mid-work
means hook infrastructure changes get bundled with feature PRs, which obscures the
history of both. The right sequence is: establish the TDD branch convention → update
hooks to recognize it → then create your first `test/*` branch.

**Playbook rule:** Add a checklist item to your pre-TDD setup: *"Do the commit gate and
completion gate understand red-phase branches?"*

---

## Hook design: make every exit path visible

Claude Code surfaces hook stderr to the user as feedback. Stdout is not surfaced. This
means any hook that only writes to stdout is invisible from the user's perspective — they
will always see "No stderr output" regardless of what the hook actually did.

**Every exit path in a hook should write one line to stderr.** This includes the
"skipped" paths (anti-loop guards, wrong directory checks, no test files found). A silent
exit is indistinguishable from a hook that failed to run at all.

Practical rules for hook authors:
- Status summary → stderr (`echo "..." >&2`)
- Full diagnostic output (test results, lint output) → stdout
- Every `exit 0`, `exit 1`, `exit 2` should have a preceding stderr line
- Test your hooks on a clean branch *before* any feature work — silent failures in hooks
  create debugging sessions that look like project failures

A related gotcha: know your tool's exit codes. `pytest` exits with code 5 when no tests
are collected — not 0. A hook that treats any non-zero exit as failure will block on
branches with no test files yet. Check what exit codes your tools produce for
"nothing to do" vs "something failed" and handle them explicitly.

---

## The [TEST] phase makes the spec executable

When an agent writes tests before implementation, every assertion is a falsifiable claim
about the system. Ambiguities that survived spec review will surface during [TEST] work
— because writing `assert cache.is_seen(url_hash=A, content_hash=B) is True` forces you
to decide whether the semantics are OR or AND, in a way that reading the spec never does.

This means the [TEST] phase is not just test authoring — it is spec validation. The
agent is finding the spec gaps that matter.

The failure mode: agents resolve ambiguities silently to keep moving, bake the choice
into test code, and the reviewer never knows a decision was made. The test *looks* like
spec. Six months later, when someone asks "why does this use OR semantics?", there is
no record.

**The right response when an agent hits an ambiguity during [TEST] work:** open a
`[DECISION]` issue, not a silent choice. The test file can wait. This is especially
important because [DECISION] issues opened at this stage are cheap — they surface before
any implementation is written, when changing the answer costs nothing.

**Encode this in your `[TEST]` issue template as a Done When checklist item:** *"All
spec ambiguities encountered while writing tests are documented as [DECISION] issues."*
A checklist item in the issue the agent is working from fires at the right moment; a
rule in CLAUDE.md does not reliably survive a long session.

---

## Stub pattern: tests that can't import show as ERROR, not FAIL

In Python, if a test file imports a module that doesn't exist, pytest cannot collect the
file — it shows as a collection **ERROR**, not a test **FAIL**. This distinction matters
for TDD discipline: ERROR means "the test infrastructure is broken"; FAIL means "the
behavior doesn't exist yet." You want the latter.

**The stub pattern:** before running tests for the first time, create a minimal stub for
the module under test — empty classes and functions with correct signatures but no logic.
The stub is infrastructure, not implementation. It gives pytest enough to collect the
tests, and the tests fail because the behavior doesn't exist.

A related trap: a stub can accidentally satisfy tests. If your stub's `is_seen()` returns
`False` and your test asserts `is_seen() is False` for unknown hashes, the test passes
against the stub — for the wrong reason. Check not just that tests *fail*, but that they
fail *because the behavior doesn't exist*, not because the stub happens to implement it.
A test that passes against a stub that doesn't implement the behavior is a **false green**
in the red phase, and false greens are the most expensive kind of bug to find later.

**To detect false greens:** after writing tests, check the passing count. If more tests
pass than you expect (interface contract checks, obvious no-op behaviors), investigate
each one. Any test that passes because the stub accidentally implements the correct
behavior should be redesigned so it would fail against a naive stub.

---

## Interface decisions in tests are invisible without explicit documentation

When a test encodes an interface decision — the OR/AND semantics of a function,
whether a field is required or optional, whether validation is runtime or type-checked
only — it *looks like spec* to a reviewer. The reviewer reads what was decided, not that
a decision was made. This makes PR review an unreliable catch mechanism for undocumented
decisions.

The convention that fixes this: **the PR description for a [TEST] PR should include an
"Interface decisions made" section** listing every interpretive call, even obvious ones.
Format: what was decided, where it's encoded in the tests, and what the spec says (or
doesn't say). This gives the reviewer a directed reading list and creates a durable
record of the decision in the PR history.

Decisions that are genuinely ambiguous — where two reasonable engineers might choose
differently — should be `[DECISION]` issues, not PR description entries. The distinction:
- Obvious in context, just underdocumented → PR description entry
- Genuinely debatable, would produce different implementations → `[DECISION]` issue

---

## Where to put task-phase behavioral guidance

CLAUDE.md applies globally and is read at session start. Issue templates are injected at
task time and apply to a specific type of work. These serve different purposes and content
should be routed accordingly.

**Put guidance in CLAUDE.md when** it applies across all phases of work — error handling
conventions, logging format, module structure, quality gates. This is the layer for
"always do X."

**Put guidance in the issue template when** it needs to fire during a specific phase —
"document [DECISION] issues during [TEST] work," "don't modify test files during [IMPL]
work." By the time an agent is deep in writing test assertions, it will not re-read §6.1
of CLAUDE.md to check whether the DECISION NEEDED protocol applies. A checklist item in
the issue it's working from will fire. A paragraph in the global briefing likely won't.

The practical test: *if this guidance needs to fire at a specific moment in a task, it
belongs in the artifact for that task.* If it applies everywhere, CLAUDE.md. If it
applies to a type of issue, that issue's template. If it applies at completion time,
a hook.

This routing decision also keeps CLAUDE.md from growing unwieldy. Guidance that migrates
into templates can be removed from CLAUDE.md — reducing the instruction budget the agent
consumes on content that's already being injected at the right moment via templates.

---

## Enforcement layer changes have their own merge cadence

Changes to hooks are infrastructure changes. They should land on `main` independently,
before the feature work that depends on them — not bundled into feature PRs.

The concrete failure mode: a [TEST] PR adds TDD-aware hook changes alongside test files.
The hook changes are necessary for the branch to work correctly, but they're now gated
behind PR review of the test suite. If the PR isn't merged promptly, the next `test/*`
branch inherits the broken hook behavior and hits the same problem again.

**The right sequence:** identify the hook change needed → open a small dedicated PR →
merge to main → then create the feature branch that depends on it.

This also keeps your git history clean: hook changes are auditable separately from the
features they enable, and the "why" of each change is in its own commit message rather
than buried in a multi-file feature PR.

---

## Implementation decisions worth preserving beyond the PR

PR descriptions and commit messages are durable, but they're not read proactively.
Decisions that affect future implementation agents should also be recorded here if
they're non-obvious or could be silently undone by a future change.

Three categories worth capturing from the P2 foundation implementation (PR #27):

**1. `purge_expired` uses date-granular comparison, not datetime.**

The test requires that an entry timestamped exactly `TTL_DAYS` ago is NOT purged.
With a datetime comparison (`seen_at < now - timedelta(days=ttl_days)`), the cutoff
is recomputed at call time — always a few microseconds later than the boundary
timestamp — so the boundary item is always marginally older than the cutoff and gets
purged. This is a race condition baked into the test setup.

The fix: truncate both sides to `YYYY-MM-DD` before comparing. Items are purged only
when their *date* is strictly before `(now - ttl_days).date()`. An item created at
any time on day X is safe until the cutoff date passes X.

If a future agent changes the TTL comparison to use datetime precision, the boundary
test will start failing intermittently — likely to be misdiagnosed as flakiness.

**2. `is_seen` uses hardcoded SQL branches instead of dynamic query construction.**

The natural implementation builds the WHERE clause dynamically from whatever
hashes are provided. Ruff's `S608` rule flags this as a potential SQL injection
vector, even though the column names are hardcoded strings — it can't statically
verify that. Since the input space is small (url_hash only, content_hash only, or
both), three explicit hardcoded queries eliminate the false positive cleanly.

If a future agent refactors to dynamic query construction, `S608` will fire. The
fix is `# noqa: S608` with a comment explaining why it's safe, or keep the
explicit branches.

**3. `yaml` is in `mypy ignore_missing_imports`, not `types-PyYAML` in dev deps.**

`pyyaml` ships without type stubs. Adding `types-PyYAML` to dev dependencies would
fix `mypy --strict` correctly, but adding a new dependency requires a DECISION per
CLAUDE.md §3. The minimum-surface fix was to add `yaml` to the existing
`ignore_missing_imports` override in `pyproject.toml`.

This is a debt item: `types-PyYAML` should be added to dev deps at the next
planned dependency review. A future agent adding any module that imports `yaml` will
inherit the same `ignore_missing_imports` workaround silently — the right fix is
the stubs package.

---

## Fixture shape is a spec claim, not just scaffolding

Test fixtures encode two kinds of information: the assertions encode *behavioral*
decisions (OR vs AND semantics, required vs optional fields). But the fixture's
*shape* encodes *structural* decisions — what fields must be present for the config
to be valid, what a "minimal" valid instance looks like.

The concrete failure: `MINIMAL_VALID_CONFIG` in the test suite included `hackernews`
because several tests needed to exercise HackerNews fields. The [IMPL] agent saw
`hackernews` in the minimal fixture and inferred it was required — and made it so.
The implementation was internally consistent and passed all 87 tests. But it rejected
configs the spec never said were invalid (RSS-only, ArXiv-only). The constraint was
too strict and came entirely from the fixture shape, not the spec.

**The rule:** `MINIMAL_VALID_CONFIG` should be the absolute minimum the spec requires
— nothing else. If a field isn't spec-required, it doesn't belong in the minimal
fixture, even if it makes other tests easier to write. Put extra fields in named
fixtures that are explicit about what they're testing.

This is a harder version of the "interface decisions in tests" problem: at least an
assertion is visible at review time. A fixture's shape — what it *omits* — is nearly
invisible. The only reliable catch is comparing the minimal fixture directly against
the spec's "required fields" list before the [TEST] PR is approved.

**Add to your [TEST] PR checklist:** *"Does MINIMAL_VALID_CONFIG contain only what
the spec actually requires? Could a valid real-world config omit anything in it?"*

---

## `Literal[...]` for spec-constrained string fields — automated tools won't catch the gap

When a spec defines a fixed set of valid values for a string field (e.g.,
`content_type: "email" | "web" | "arxiv"`), using `str` as the type annotation
passes mypy strict, ruff, and every test — as long as no test passes an invalid
value. All three automated layers are satisfied by `str`. Only a reviewer comparing
the type annotation against the spec notices the gap.

The consequences of using `str` instead of `Literal[...]`:
- A future connector passing `"html"` or `"rss"` is silently accepted at the model
  layer and only fails when downstream code tries to handle it
- mypy loses the ability to exhaustiveness-check `match content_type:` branches
  in stage code

**The rule:** if the spec lists valid values for a field, use `Literal[...]`. This
is especially important for stage-boundary types (`RawItem`, `ExcerptItem`, etc.)
where the type is the interface contract between modules written by different agents.

**This is a review concern, not a linter concern.** Add it to your [TEST] PR
checklist: *"For any string field with a constrained value set in the spec, is the
type `Literal[...]` rather than `str`?"*

---

## Import ordering regressions between [TEST] and [IMPL] phases

When a test file imports a module that doesn't exist yet (TDD red phase), formatters
like ruff can't resolve the import, so they may classify it differently than they will
once the module exists and is recognized as first-party. This produces a predictable,
repeating failure: the test file passes `make lint` in the [TEST] PR, then fails lint
in the [IMPL] PR because the new module changes how the formatter groups imports.

This isn't a one-time edge case — it will recur for every [TEST]/[IMPL] pair where the
module is new. In a project with many modules, you'll see this failure in most [IMPL] PRs.

**The fix:** as part of [IMPL] work, run `make lint` against the full test suite — not
just the new module. Expect to need a mechanical import-reorder in the test file. This
is not a test logic change and doesn't violate the "don't modify test files" rule. The
[IMPL] PR description should explicitly note when this fix is included so reviewers can
confirm it's mechanical only (import order, not assertions or behavior).

**The root cause fix:** configure your formatter to treat all first-party packages
explicitly rather than relying on auto-detection. In ruff, this is `known-first-party`
in `[tool.ruff.lint.isort]`. Once set, the sort order is stable whether or not the
module being imported has been created yet.

**The "don't modify test files" rule has a scope:** it means "don't change what
behavior the tests verify." Mechanical lint fixes — import ordering, removing imports
that are now unused because a stub was deleted — are infrastructure, not test logic.
The rule exists to prevent an [IMPL] agent from weakening assertions to make tests pass;
it shouldn't block obvious maintenance. When in doubt: if the change would make a
currently-passing test fail or a currently-failing test pass, it's a logic change.
If it wouldn't, it's maintenance.

---

*Part of the AI Engineering Playbook. Reference implementation: ai-radar (Python + Claude Code).*
