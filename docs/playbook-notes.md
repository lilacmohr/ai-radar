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

## Use build system targets, not direct tool invocations

`make lint` runs `ruff check` AND `ruff format --check`. Running `ruff check`
alone misses formatting violations — all linting passes but the CI `make lint`
step fails. The same issue applies to any make target that wraps multiple tools:
the target exists precisely because the combination matters.

**The rule:** always use the make target. Never substitute a subset of the tools
it invokes, even if the subset looks sufficient. If a target is too slow for a
quick feedback loop, that's a signal to create a faster target — not to run the
tools piecemeal and skip steps.

**Encode this in CLAUDE.md as a negative:** "Always use `make lint` — never
`ruff check` alone" is more reliable than "use make targets" as a general
principle, because agents follow specific rules better than abstract ones.

---

## Paired [TEST] and [IMPL] issues may disagree on interface shape

Issue templates are authored before the test file exists. When the [IMPL] issue
specifies an interface (e.g., a class with methods) and the [TEST] issue's test
file implements a different interface (e.g., module-level functions), the test
file is the executable spec. The [IMPL] agent follows the tests, not the issue
description.

This is correct behavior — the test file is the authoritative interface contract —
but it creates a recurring friction point: the [IMPL] issue becomes misleading for
anyone reading it later, and PR reviewers may flag the mismatch as a defect.

**The fix:** note the discrepancy explicitly in the [IMPL] PR description. Something
like "impl issue specified a class interface; implemented as module-level functions
to match the test file." This documents the decision, confirms it was intentional,
and gives reviewers the context they need.

**The root cause fix:** [TEST] and [IMPL] issues should be written in sequence, not
in parallel. Once the test file exists and has been reviewed, the [IMPL] issue should
reflect its actual interface. If the issues are templated before any tests are written,
treat the interface specification in both issues as a draft — the test file finalizes it.

---

## Exporting internal helpers for test setup (the url_to_hash pattern)

When a module computes internal state that collaborating code depends on — for
example, a deduplicator that computes a URL hash before checking the cache — tests
that need to pre-populate that state face a dilemma: either replicate the hash
algorithm in the test (fragile, diverges when the algorithm changes) or export
the helper so tests can call it directly.

**Export the helper.** A small, pure function like `url_to_hash(url: str) -> str`
is stable, testable in isolation, and gives tests a single source of truth for
the expected state. Tests that call `cache.mark_seen(url_hash=url_to_hash(url))`
will automatically stay correct if the hash algorithm changes — they don't need
to be updated.

This pattern also provides a secondary benefit: the helper's behavior becomes
independently testable. Tests for `url_to_hash` verify that UTM params are stripped,
that scheme/host are normalized, and that identical inputs produce identical outputs.
These are properties of the helper, not the deduplicator — separating them makes
both easier to reason about.

**The rule for deciding whether to export:** if a test needs to compute the same
value that the module computes internally in order to set up a valid test scenario,
export the computation as a named function. The alternative — duplicating the logic
in the test — is a maintenance hazard that will diverge silently.

---

## Verify mock behavior as part of red-phase confirmation

When test setup involves complex mocks, a broken mock can produce a test that
*appears* to pass or fail for the wrong reason. The `test_max_age_days_included_in_api_query`
test in the Gmail connector had a `capture_list` function that called
`mock_service.users().messages().list()` — which called `capture_list` again,
causing infinite recursion. The test showed as FAILED (expected in red phase),
but for the wrong reason: `RecursionError`, not `NotImplementedError`.

If the recursion bug had survived to the green phase, the test would have continued
failing after a correct implementation — a false red that would have been
hard to diagnose.

**The rule:** after confirming the red phase, scan any test that involves a
multi-step mock setup — especially tests that intercept method calls to capture
arguments. Check that it fails with `AttributeError` or `NotImplementedError`, not
with an infrastructure error like `RecursionError` or `TypeError` in the mock itself.

**Practical check:** `pytest tests/unit/test_X.py -v` and read the failure reason
for every test, not just the count. "33 failed" can hide both correct failures and
broken-mock failures in the same number.

---

## Mock depth is a design signal

When a test requires configuring a mock chain more than 3 levels deep — e.g.,
`service.users().messages().list().execute.return_value` — the module under test
likely doesn't have a good internal seam for testing. The production code calls the
external library directly, so tests must replicate the full call structure.

The design fix: extract the external call into a private helper that accepts the
minimal parameters and returns the data the module needs. Tests can then mock the
helper rather than the full chain. This also makes the production code easier to
read — the call chain appears once, named, rather than repeated across the module.

**The signal in practice:** if you're spending more time configuring a mock than
writing the assertion it supports, the test is telling you something about the
module's dependencies. The Gmail connector's `_fetch_label` and `_process_message`
helpers are a step in this direction — but they still accept the raw `service`
object. A cleaner seam would be a `_list_messages(service, label, query)` helper
that returns a plain list, isolating the API call entirely.

**This is a judgment call, not a rule.** External API clients (Google, Stripe, etc.)
have inherently deep call chains. The goal isn't to eliminate mock depth entirely —
it's to notice when mock complexity is masking a design opportunity.

---

## Run make lint early and often during test-file authoring

In practice, running `make lint` only as a final gate (step 6 of the agent
instructions) produces multiple rounds of lint fixes: nested `with` statements,
non-top-level imports, boolean positional args, magic values, line length — all
discovered at once after the full test file is written.

The fix is simple: run `make lint` after writing the first 3–5 tests, before
finishing the file. Lint errors that appear early are cheap to fix; lint errors
discovered after 30 tests require reviewing the full file for the same pattern.

**This is captured in the [TEST] issue template agent instructions** — step 4
now asks for an early lint check before writing the remaining tests. The
CLAUDE.md §6.5 entry covers the pre-PR gate; the template handles the
task-phase timing.

**The broader principle:** any quality gate that's only run at completion will
produce batched failures. If a check is fast (lint is), run it incrementally.
Reserve the full `make check` (lint + typecheck + full test suite) for the
completion gate where the cost is justified.

---

## [REFACTOR] issues: capture debt without blocking progress

When you notice a structural problem — a violated rule, a testability gap, a
workaround that should be replaced — the worst options are: fix it immediately
(interrupts the current task, bundles unrelated changes in a PR) or leave it as
a TODO comment (invisible to planning, never prioritized, eventually forgotten).

A `[REFACTOR]` issue is the right middle ground. It captures:
- **What** needs to change (concrete enough for an agent to implement without follow-up)
- **Why** it matters (which rule or standard is violated, with a reference)
- **What must not change** (observable behavior, test assertions, public interfaces)

**When to open a `[REFACTOR]` issue instead of fixing inline:**
- The fix touches files not in scope for the current PR
- The fix is mechanical but non-trivial — worth review on its own
- The current task is in a different phase (e.g. noticing a structural problem in `[TEST]` work that belongs in an `[IMPL]` concern)
- The problem is real but non-blocking — deferring it is safe

**When to just fix it inline:**
- The fix is in a file already being changed
- It's a one-line correction with no behavioral risk
- Deferring it would make the current code actively misleading

**The key property of a good `[REFACTOR]` issue:** an agent should be able to
open it, implement the change, run `make check`, and close it — without any
ambiguity about what "done" means or risk of accidentally changing behavior.
The "What Must Not Change" field is what makes this reliable: it forces you to
articulate the behavioral boundary before the work starts, not during.

**Refactor issues are safe to defer, but not safe to ignore.** Review open
`[REFACTOR]` issues at the start of each phase. If a refactor issue touches a
module that's about to be worked on, close it first — doing the refactor and
the feature in the same PR creates noise and makes the PR harder to review.

---

## Prompt/parser drift: test canned responses bypass the template

When a test supplies a canned LLM response, it bypasses the prompt template entirely.
This means a mismatch between what the template instructs the model to produce and what
the parser expects to receive will never be caught by unit tests — the canned response
can be written to match the parser regardless of what the template says.

In the Synthesizer, the `PASS_2_USER_TEMPLATE` instructed the model to emit
`## 🔍 Non-Obvious Insights` but the parser looked for
`## 🔍 Contrarian & Non-Obvious Insights`. Every unit test passed because the canned
responses were written to match the parser constant. In production, the LLM followed
the template — and `Digest.contrarian_insights` was always `""`.

**The fix:** add regression tests that import the parser constants and assert their
verbatim presence in the prompt template. These tests fail immediately if the template
and parser diverge:

```python
from radar.llm.prompts import PASS_2_USER_TEMPLATE
from radar.llm.synthesizer import _SECTION_CONTRARIAN_INSIGHTS

def test_pass2_template_contains_contrarian_insights_heading() -> None:
    assert f"## {_SECTION_CONTRARIAN_INSIGHTS}" in PASS_2_USER_TEMPLATE
```

**The rule:** for any module that parses structured LLM output by matching headings or
markers, add one regression test per marker that cross-validates the prompt template
against the parser constant. These tests cost one line each and catch an entire class
of silent production bugs that unit tests with canned responses cannot detect.

**Where to put them:** in the `[TEST]` file for the synthesizer/parser module, grouped
under a "Regression: prompt headings match parser constants" section. They belong there
rather than in a separate test file because they test the behavioral contract of the
parsing module, not just the prompt content in isolation.

---

## `click.Path(exists=True)` breaks `--help` when the default path doesn't exist

Click validates `Path(exists=True)` parameters eagerly — before `--help` short-circuits.
If a CLI option has a default path that doesn't exist in the test environment, `--help`
will exit with code 2 ("Error: Invalid value for '--config': Path ... does not exist.")
instead of code 0. Tests asserting `exit_code == 0` for `--help` will fail.

The failure is invisible in manual testing if the config path always exists locally. It
surfaces in CI (fresh checkout, no config file) or in unit tests using `CliRunner()`.

**The fix:** remove `exists=True` from `click.Path()` for config file options. Validate
the path manually at the start of the command body, before any other logic:

```python
@cli.command()
@click.option("--config", type=click.Path(dir_okay=False, path_type=Path))
def run(config: Path) -> None:
    if not config.exists():
        raise click.ClickException(f"Config file not found: {config}")
    ...
```

**The rule:** never use `click.Path(exists=True)` for config file options that have
defaults or that are referenced in `--help` tests. Always validate manually at the
start of the command body.

---

## Grep all importers before moving a shared function

When a shared utility function moves between modules, the author naturally updates their
own import sites. But consumers in other modules — especially in test files — are easy
to miss. The result is `attr-defined` or `ImportError` errors that only surface when mypy
or the test suite runs against the full codebase.

In P5.3, `url_to_hash` was moved from `deduplicator.py` to `cache.py`. The imports were
updated in the module doing the moving, but `excerpt_fetcher.py` and `test_deduplicator.py`
still imported from `deduplicator`. Mypy caught both after the fix was committed, not before.

**The rule:** before committing any change that moves or renames a publicly-imported name,
run:

```bash
grep -r "from radar.processing.deduplicator import url_to_hash" .
grep -r "import url_to_hash" .
```

Replace with the specific name being moved. Fix all hits before committing. This is a
30-second step that prevents a mypy failure round-trip.

**Encode this in CLAUDE.md** as: "When renaming or moving a shared function, grep the
full codebase for all import sites before committing. Missing an importer causes a mypy
failure that can't be detected locally until `make typecheck` runs."

---

## Factory function pattern for CLI testability when constructors fail without credentials

When a CLI command constructs an object whose `__init__` raises without credentials
(e.g., `LLMClient` raises `ValueError` if `GITHUB_MODELS_TOKEN` is unset), unit tests
cannot use `patch()` on the class after construction — Python evaluates constructor
arguments before `patch` can intercept them.

The pattern that works: define a **module-level factory function** in `__main__.py`
with the same name as the class it produces. Tests patch the factory function at the
module level, intercepting the call before any credentials are needed:

```python
# In __main__.py
def Pipeline(cfg: Config, config_path: Path) -> PipelineClass:  # noqa: N802
    """Factory: creates Pipeline (named to match class for test patching convenience)."""
    return PipelineClass(cfg, config_path)

# In tests
with patch("radar.__main__.Pipeline", return_value=mock_pipeline):
    runner.invoke(cli, ["run"])
```

The `# noqa: N802` suppresses the "function name should be lowercase" lint rule. The
naming is intentional: it mirrors the class name so the patch target is intuitive.

**Trade-off:** this is non-obvious to a reader encountering it for the first time. The
docstring must explain why the factory has a capitalized name — otherwise it looks like
a mistake. See decision issue #108 for the alternative designs that were considered.

**When to apply this pattern:** any time a CLI layer constructs an object whose init
performs network calls, credential validation, or external I/O that would fail in a test
environment. The factory function is the seam between "object construction" and "object
behavior" — mock the former, test the latter.

---

## Test coverage drives implementation completeness — spec sections without assertions get missed

In P5.1, the `MarkdownRenderer` was implemented correctly for everything the test file
covered. But the test file omitted the Pipeline Metadata block from SPEC.md §3.4 (which
requires a "Sources", "Articles", and "Run time" line). The implementation had a wrong
"Date:" line instead. All tests passed. The gap wasn't caught until post-implementation
PR review.

The root cause: the agent writing tests read the spec but didn't translate every section
into an assertion. The Pipeline Metadata section is a distinct block in the spec, but
the test file had no test for it at all. With no test, the implementation had no signal
that this section was wrong — or even expected.

**The rule:** during `[TEST]` work, read the spec section by section and write at least
one assertion per distinct behavioral unit. A spec section that has no corresponding test
assertion will not be caught during implementation, regardless of how carefully the
implementation is written.

**Practical check:** after finishing the test file, re-read the spec section and ask:
*"If I deleted every line of spec text that corresponds to an existing test assertion,
what's left?"* Anything left is an uncovered spec requirement.

**Add to the `[TEST]` issue template checklist:** *"Every distinct behavioral unit in
the spec has at least one assertion in the test file."*

---

*Part of the AI Engineering Playbook. Reference implementation: ai-radar (Python + Claude Code).*
