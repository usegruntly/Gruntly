# Changelog

## 0.2.0 - 2026-11-07

Rework after a cost audit of the 0.1.0 benchmark (delegating cost 70% more than doing the work alone; most of it was fixed overhead in the parent's turns, not escalations).

- One-call flow: `gruntly run --apply-on-pass` applies a passing patch, re-verifies in your tree only if it changed, reverses the patch if that check fails, and cleans up the worktree.
- Result schema 2: a pass is ~300 bytes (was ~1 KB). All child-written text (summary, test output, handoff) is under one `untrusted` key and only on non-passes; `child_summary`, `timing` and `child_usage` are gone from the parent's view.
- New gates and signals: `holdout` (parent-written tests the child never sees), `regression` (run the wider suite), red-before-green warning when acceptance already passes at the base, `review_hint`.
- Preflight refuses a model context under 32k tokens (`allow_small_ctx` overrides); queue waits are capped at the run budget and say who holds the slot.
- Plugin: skill cut from ~1,200 to ~230 words (full manual via `gruntly guide`), MCP tools cut from 7 to 2, MCP install pinned to a release tag.
- `gruntly stats` keys by harness/model/context and recommends `delegate`, `avoid` or `unknown`.

## 0.1.0 - 2026-11-07

First release.

- Core CLI: `run` (sync and `--async`), `status`, `result`, `diff`, `log`, `continue`, `apply`, `discard`, `doctor`, `init` (`--snippet`), `stats`, `gc`, `mcp`.
- Isolated runs: git worktree per task, scrubbed child environment, wall-clock and no-progress limits, process-tree kill, before/after fingerprint of the main tree, one-slot queue.
- Gates run by gruntly itself: acceptance, scope, diff size, test weakening, new dependencies, optional lint and typecheck.
- Retry loop with stuck detection, malformed-tool-call detection, infrastructure errors that cost no attempt, and escalation with a compact failure bundle. Results are capped near 6000 characters.
- Context relays: a child that runs out of context leaves `.gruntly-handoff.md`; `gruntly continue` starts a fresh child with those notes plus the parent's guidance.
- Adapters: Qwen Code 0.26.9 and OpenCode 1.19.5 (verified against real output), generic command template, Hermes Agent (flags only, not verified end to end).
- Claude Code plugin (skill and MCP server) with a marketplace file; MCP tools mirror the CLI.
- Benchmark harness (`bench/`) with ten tasks judged by hidden tests, and `docs/benchmark.md`.
- Sandbox level 1 (bubblewrap, Linux): command construction is unit-tested but has not been run against a real bubblewrap yet.

Fixed during development: a stale `.pyc` could hide a same-size edit and make a correct retry look broken; apply no longer treats files the parent edited after the run as a scope violation.
