# Changelog

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
