#!/usr/bin/env bash
# .claude/hooks/stop_run_tests.sh
#
# PURPOSE: Run the full test suite when Claude signals it has finished a task.
#          If tests fail, Claude is forced to continue working rather than
#          marking the task complete.
# TRIGGER: Stop — fires when Claude finishes responding.
# EFFECT:  BLOCKING. Exit 2 forces Claude to continue. Exit 0 allows stop.
#
# PLAYBOOK NOTE:
#   This is the enforcement layer for the TDD contract in CLAUDE.md §6.
#   "All tests must pass before a task is considered complete" is a rule.
#   This hook makes it a guarantee.
#
#   This hook runs the FULL test suite (unit + integration), unlike session_start.sh
#   which runs unit tests only for a fast startup check. The Stop hook is a
#   completion gate — it must catch all failures, not just fast ones.

set -euo pipefail

INPUT=$(cat)

# CRITICAL: Prevent infinite loop.
# If Stop hook already fired this turn, allow Claude to stop.
STOP_HOOK_ACTIVE=$(echo "$INPUT" | jq -r '.stop_hook_active // false')
if [[ "$STOP_HOOK_ACTIVE" == "true" ]]; then
  echo "[stop-gate] skipped — already ran this turn (anti-loop guard)" >&2
  exit 0
fi

# Only run tests if we're in the project root (guard against wrong-dir invocations)
if [[ ! -f "pyproject.toml" ]]; then
  echo "[stop-gate] skipped — pyproject.toml not found (wrong directory?)" >&2
  exit 0
fi

# Only run tests if there are Python files in the working tree
if ! find tests -name "*.py" -maxdepth 4 2>/dev/null | grep -q .; then
  echo "[stop-gate] skipped — no test files found" >&2
  exit 0
fi

# TDD red-phase exception: test/* branches carry intentionally failing tests.
# Run tests for visibility but do not block stopping.
CURRENT_BRANCH=$(git branch --show-current 2>/dev/null || echo "")
if [[ "$CURRENT_BRANCH" == test/* ]]; then
  echo "━━━ Stop Gate: TDD red-phase branch ($CURRENT_BRANCH) — running for visibility ━━━"
  echo "[test] uv run pytest tests/ -x -q --tb=short"
  timeout 120 uv run pytest tests/ -x -q --tb=short 2>&1 || true
  echo "[stop-gate] passed — TDD red-phase branch, failures expected" >&2
  exit 0
fi

# TDD red-phase exception: test/* branches carry intentionally failing tests.
# The Stop gate still runs tests for visibility, but does not block stopping.
CURRENT_BRANCH=$(git branch --show-current 2>/dev/null || echo "")
TDD_RED_PHASE=false
if [[ "$CURRENT_BRANCH" == test/* ]]; then
  TDD_RED_PHASE=true
  echo "━━━ Stop Gate: TDD red-phase branch ($CURRENT_BRANCH) ━━━"
  echo "    Tests may fail — this is expected. Running for visibility only."
else
  echo "━━━ Stop Gate: Running test suite ━━━"
fi
echo "[test] uv run pytest tests/ -x -q --tb=short"

timeout 120 uv run pytest tests/ -x -q --tb=short 2>&1
PYTEST_EXIT=$?

# Exit 5 = no tests collected (e.g. scaffolding-only branch). Treat as pass.
if [[ $PYTEST_EXIT -eq 0 ]] || [[ $PYTEST_EXIT -eq 5 ]]; then
  echo "[stop-gate] passed — all tests green" >&2
  exit 0
else
  if [[ "$TDD_RED_PHASE" == "true" ]]; then
    echo ""
    echo "[~] Tests failed on TDD red-phase branch — expected. Task complete."
    exit 0
  fi
  echo ""
  echo "[✗] Tests failed. Task is NOT complete."
  echo "    Fix the failing tests before finishing."
  echo "    (Claude will continue working.)"
  echo "[stop-gate] blocked — tests failing" >&2
  # Exit 2 = blocking: Claude is forced to continue rather than stop
  exit 2
fi
