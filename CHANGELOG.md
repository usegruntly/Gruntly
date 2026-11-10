# Changelog

## Unreleased
- Fewer paid turns per delegation: the skill's always-loaded description carries the call, so Claude need not load the skill first; the result block shows changes to real code before test files (a long test file the child wrote no longer pushes the real change past the cut-off); a test that only imports the target now counts as covering it (the cli_json request used to be told "no test covers this", got a child-written test file and a "weak test" flag); the parts of a split request run side by side on a hosted provider and apply one by one afterwards (bugs_batch ran out of time with six parts in a row). Plugin 0.8.1.
- `gruntly agent-run --explore [--check CMD] 'intent'`: the child finds where to change the code itself. Scope is the whole project except the check's own files (tests may change where the task needs it, guarded by the test-weakening gate); the check is the whole suite unless given. For a parent that plans and tracks steps instead of reading code.
- The child always runs as its harness ships (own system prompt and tools); the slim profiles (`typist`, `worker`, `auto`) are removed. Old `profile`, `inline_files`, `web` and `self_check` settings are accepted and ignored. A local model needs a 32k context.
- One entry point for every parent: `gruntly agent-run 'plain words'`. The manual and the CLAUDE.md snippet now teach it; `gruntly run 'plain words'` without a spec does the same; a wrong flag on `run` names the right call; the MCP server's `gruntly_delegate` takes a plain request (a spec stays optional). Measured why: told to use the old spec flow, Claude spent 2 to 3 turns per delegation guessing flags, reading the manual and writing YAML.
- With mode ON, Claude's system prompt carries the whole usage, so it can delegate without loading the skill first. A passed result block ends with `next: nothing to open or rerun`. Plugin 0.8.0.
- Hermes works natively on Windows (0.23.0, with `poolside/laguna-xs-2.1` on NVIDIA): gruntly finds `%LOCALAPPDATA%/hermes/bin/hermes.exe` when `hermes` is not on PATH (Claude Code's shell did not have it), `GRUNTLY_HERMES_HOME` points every project at one prepared Hermes data folder (0.23 builds its own dependency environment per folder and fails on paths over 260 characters), and the proxy drops a duplicate `reasoning` field that made Laguna answer HTTP 400.
- Cost benchmark (`bench/cost_report.py`, `docs/benchmarks/benchmark-cost-laguna-summary.md`): Claude alone against Claude with gruntly on 10 small tasks, matched pairs, child counted as free. Result: delegating costs about 45% more than Claude alone; the plugin without delegation about 4% more.
- Live view: the child and gruntly labels use your Claude Code theme's colours (quiet, and they follow your theme) instead of fixed cyan and yellow, the mode band uses theme colours too, and the extra status-line entry is gone since the same events are already under the command. Plugin 0.7.3.
- The live diff now uses Claude Code's own diff highlighter (line-number gutters, +/- markers, add and remove backgrounds), one block per file, capped at 40 lines with the hunk headers kept valid. Plugin 0.7.2.
- Live diff: while the child works, the Claude Code view shows its changes so far under the command (green additions, red removals, capped), and keeps each attempt's final diff when it ends. gruntly reads the child's worktree, so it works for every harness. `gruntly watch` prints each attempt's final diff. The finished view now shows the child's last steps as well as gruntly's (it used to show only gruntly's, so the child's cyan rows never appeared). Plugin 0.7.1: the first version never drew the block, because it read the call's id and state from the wrong place (they arrive under `e.props`), and consecutive tool calls collapse into one summary line that never draws a separate row; the block now draws under that summary as well.
- `gruntly harness` picks the child agent: lists OpenCode, Qwen Code, Hermes Agent and generic with what each is good at (as gruntly measured it), its weight, install command, docs link and whether it is installed; `--fetch` adds each project's own GitHub description. `gruntly setup` now starts with this step; the choice is saved as `harness` in the project or global settings.
- Hermes Agent is a working child: gruntly writes its per-project `config.yaml` (custom endpoint and model), runs `hermes chat -Q`, reads the session id for `--resume`, maps the permission mode (`--yolo` or file tools only) and sets a UTF-8 locale. Verified live on WSL2 with NVIDIA through gruntly's proxy. Run gruntly inside WSL2 on Windows. No tool trace in quiet mode.
- API keys are cleaned of BOM, zero-width characters and line breaks when saved or read, and refused if they are not plain ASCII (a piped key from Windows PowerShell started with a BOM and every request failed).
- Fixes: the changed-file check used for non-Python requests compared against the staging area and reported a real edit as "not changed"; it now compares against the run's starting commit. Run worktrees are checked out exactly as stored (no LF to CRLF conversion under `core.autocrlf=true`), so the child's edits can find their text.
- `agent-run` now works on projects with no Python files: when the request names tracked non-Python files (a website, docs, config) it targets exactly those, checks that they changed, and tells the child to make real tool calls (a small model narrated its steps instead of running them). `gruntly doctor` checks the project's hosted provider instead of the local server. Plugin 0.6.2.
- Switch: `gruntly mode on|off|auto` and `/gruntly on|off|auto [session]` in Claude Code (project by default, or this session only). Off makes the CLI refuse new work in one line; on tells Claude to delegate eligible changes without asking. Plugin 0.6.0. See docs/mode.md.
- `gruntly setup` (first-run guide, offered when you type `gruntly` in a terminal for the first time), `gruntly use` (provider and model picker, saved to the project or globally) and `gruntly models` (every model an account offers, as the endpoint reports it). Docs links are printed whenever a key or model is set.
- Live view of a run: `.gruntly/runs/<id>/progress.jsonl` (child = the local model, gruntly = its checks and waits), `gruntly watch`, and a Claude Code mod in plugin 0.5.0 that draws it under the running command. See docs/live-view.md.
- `gruntly auth set|list|remove` stores provider API keys in `~/.config/gruntly/keys.toml` (owner-only); the environment variable still wins. `gruntly doctor` reports whether each provider has a key.
- Hosted child endpoints: `provider = "gemini"` runs the child on Gemma 4 through the Gemini API behind a local proxy that keeps the key out of the child, paces requests, retries 429s and counts a daily quota. See docs/providers.md.
- `agent-run --ask` for research: the child answers with its own tools (web, shell, files); no tests or diff, the answer comes back fenced as untrusted. Plugin 0.4.1.
- Fixes: `apply` no longer rewrites a whole LF file as CRLF under `core.autocrlf=true`; a context file missing from the run's snapshot stops the run instead of letting the child invent it; the same tool call repeated 6 times stops the run as a loop; shell commands with a non-zero exit or traceback count as failed in the trace.
- The child now runs its harness as shipped (`profile = "default"`, all its tools, web on) unless a slim profile is asked for; its permission mode follows the parent (`GRUNTLY_PARENT_MODE`, or `permissions` in the spec).

- `harness` now defaults to `auto`: the first of opencode, qwen, hermes found on the machine, and the model defaults to the one loaded on the server. Name either in `.gruntly.toml` to override.
- `web = true` (in `.gruntly.toml` or a spec) lets an OpenCode child use the harness's own `webfetch` tool. Off by default; fetched pages are untrusted text and the gates still judge the result. Not yet wired for Qwen Code or Hermes.
- Plugin 0.4.0: the skill now teaches `agent-run` (Bash timeout 600000, read one result block, follow-up rules). `agent-run` splits a request naming several files into one run per file, runs without a covering test (the child adds one) and on refactors whose tests already pass, gives "everywhere" requests project-wide scope, restarts the main-tree baseline on `--continue`, and `gruntly discard` no longer crashes on Windows when files are still held open. See docs/lean-long-tasks.md.
- `gruntly do "<request>"` and the `/gruntly:gd` slash command: a plain request becomes a verified delegation with no model in the loop (locate the target with `ast`, find the covering test, require it to fail first, delegate, apply on pass). The slash command runs it before Claude is called, so the task costs one model request; refusals are free. Python and pytest projects only.
- `gruntly agent-run "<prompt>"` and `gruntly agent "<task>"`: a lean Claude (one Bash tool, one-line system prompt, ~3k tokens of base context instead of ~25k) directs the local agent and reads one marked result block (status, tests, files, child trace, contract, whole diff). Follow-ups with `--continue RUN`, also after a run was applied. Falls back to a full session when the lean one gives up. Benchmark arm `lean`: ~73% cheaper per small task than Claude alone, but not yet at its pass rate (`docs/benchmarks/benchmark-lean.md`).
- Child trace (`trace.py`): a one-line summary of what the child did, built from OpenCode, Qwen Code and Hermes event output (counts only), with flags for repeated tool calls and mostly-failing calls. A child that repeats the same long output line is stopped as a loop.

## 0.3.0 - 2026-11-08

Slim child profiles, evaluate & fix, and foreground waiting.

- **Profiles** (`profile: auto|typist|worker|default`): the local model no longer pays for its harness's full system prompt and tool set. `typist` (a few small, literally named files) inlines the files in the prompt and offers only file-writing tools; `worker` adds list/search/read for tasks where the files cannot be named; `default` is the old behaviour. `auto` picks from the scope. Measured on OpenCode (`docs/benchmarks/child-bench.md`): ~70% fewer child tokens per run (79% on the small tasks) and ~44% less wall time at equal hidden-test pass rate (68% against 62%). A slim run on Qwen Code used ~2.2k input tokens per request instead of ~14k. Slim profiles need an 8k (typist) or 16k (worker) context window instead of 32k.
- **Evaluate & fix** (`self_check: false`, the default): the child has no shell and is told not to run tests. gruntly runs the acceptance command and every other gate and feeds the failure straight back as the next attempt; the parent never sees intermediate failures. In the benchmark, letting the child run its own tests bought nothing.
- **No shell, no waste:** OpenCode runs a one-line custom agent with only the tools the profile needs and no AGENTS.md, `~/.claude` skills or plugin discovery; Qwen Code runs `--bare`, which also drops its extra ~7k-token memory request. Per-request input tokens are recorded and shown in `gruntly stats`.
- **Foreground waiting:** `gruntly run` now blocks up to `--max-block` seconds (default 240) and returns a ~150-byte `{"status": "running"}` if the run is longer; `gruntly wait <run>` blocks again. The skill says never to use `run_in_background`, which ended the parent's turn and replayed the whole conversation in a second session to read a 300-byte result. A worker that dies without a result is reported instead of hanging.
- **Findings:** no profile fixes false passes (gates green, hidden tests red); they come from briefs and visible tests that omit behaviour the hidden tests check. On vague briefs every arm, including the stock harness, failed, so the parent keeps writing precise briefs. See `docs/benchmarks/child-bench.md`.
- **Fixes found while testing:** OpenCode needs each enabled tool's permission granted explicitly or the model gets no tools and pastes code into its reply; Qwen Code's `edit` needs `read_file` to have been called first.
- **Benchmarks:** Sonnet-parent results added (`docs/benchmarks/benchmark-v2-sonnet.md`). Earlier benchmark floors are not comparable with new runs: the claude.ai connectors (~50 tool schemas per session) were disabled afterwards.
- Not done: a live Qwen Code benchmark (one slim run measured), the last 11 vague-brief runs (the machine ran out of memory), Hermes, sandbox level 1 on Linux.

## 0.2.1 - 2026-11-07

Fixes found by benchmark v2 (see `docs/benchmarks/benchmark-v2.md`).

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
- Benchmark harness (`bench/`) with ten tasks judged by hidden tests, and `docs/benchmarks/benchmark.md`.
- Sandbox level 1 (bubblewrap, Linux): command construction is unit-tested but has not been run against a real bubblewrap yet.

Fixed during development: a stale `.pyc` could hide a same-size edit and make a correct retry look broken; apply no longer treats files the parent edited after the run as a scope violation.
