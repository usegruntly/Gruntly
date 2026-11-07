# Changelog

## Unreleased

- `gruntly do "<request>"` and the `/gruntly:gd` slash command: a plain request becomes a verified delegation with no model in the loop (locate the target with `ast`, find the covering test, require it to fail first, delegate, apply on pass). The slash command runs it before Claude is called, so the task costs one model request; refusals are free. Python and pytest projects only.

## 0.3.0 - 2026-11-08

Slim child profiles, evaluate & fix, and foreground waiting.

- **Profiles** (`profile: auto|typist|worker|default`): the local model no longer pays for its harness's full system prompt and tool set. `typist` (a few small, literally named files) inlines the files in the prompt and offers only file-writing tools; `worker` adds list/search/read for tasks where the files cannot be named; `default` is the old behaviour. `auto` picks from the scope. Measured on OpenCode (`docs/child-bench.md`): ~70% fewer child tokens per run (79% on the small tasks) and ~44% less wall time at equal hidden-test pass rate (68% against 62%). A slim run on Qwen Code used ~2.2k input tokens per request instead of ~14k. Slim profiles need an 8k (typist) or 16k (worker) context window instead of 32k.
- **Evaluate & fix** (`self_check: false`, the default): the child has no shell and is told not to run tests. gruntly runs the acceptance command and every other gate and feeds the failure straight back as the next attempt; the parent never sees intermediate failures. In the benchmark, letting the child run its own tests bought nothing.
- **No shell, no waste:** OpenCode runs a one-line custom agent with only the tools the profile needs and no AGENTS.md, `~/.claude` skills or plugin discovery; Qwen Code runs `--bare`, which also drops its extra ~7k-token memory request. Per-request input tokens are recorded and shown in `gruntly stats`.
- **Foreground waiting:** `gruntly run` now blocks up to `--max-block` seconds (default 240) and returns a ~150-byte `{"status": "running"}` if the run is longer; `gruntly wait <run>` blocks again. The skill says never to use `run_in_background`, which ended the parent's turn and replayed the whole conversation in a second session to read a 300-byte result. A worker that dies without a result is reported instead of hanging.
- **Findings:** no profile fixes false passes (gates green, hidden tests red); they come from briefs and visible tests that omit behaviour the hidden tests check. On vague briefs every arm, including the stock harness, failed, so the parent keeps writing precise briefs. See `docs/child-bench.md`.
- **Fixes found while testing:** OpenCode needs each enabled tool's permission granted explicitly or the model gets no tools and pastes code into its reply; Qwen Code's `edit` needs `read_file` to have been called first.
- **Benchmarks:** Sonnet-parent results added (`docs/benchmark-v2-sonnet.md`). Earlier benchmark floors are not comparable with new runs: the claude.ai connectors (~50 tool schemas per session) were disabled afterwards.
- Not done: a live Qwen Code benchmark (one slim run measured), the last 11 vague-brief runs (the machine ran out of memory), Hermes, sandbox level 1 on Linux.

## 0.2.1 - 2026-11-07

Fixes found by benchmark v2 (see `docs/benchmark-v2.md`).

- A holdout file outside the repo, or missing, now fails at spec time with a clear message instead of a raw git error after the child's work.
- Skill: holdout files must be inside the repo; set `tests_writable: true` when the task edits existing tests; do not delegate what one shell command (sed, a codemod) can do.
- `gruntly` now saves the exact prompt and command sent to the child for every attempt (`attempts/N/prompt.txt`, `command.json`), and `bench/trace.py` merges that with Claude's transcript into one verbatim log. Passing gates no longer write their own name into the gate files.

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
