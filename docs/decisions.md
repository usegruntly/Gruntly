# Decisions

## 2026-11-07 — blocking questions

- **OS/shell:** both. WSL2 Ubuntu is the primary dev and test target. Core code stays portable; native Windows gets a process-tree kill fallback, and sandbox level 1 (bubblewrap) is Linux-only.
- **Local model:** LM Studio or llama.cpp via an OpenAI-compatible endpoint. Model, context length and URL to be confirmed in M0. Dev machine has 15.7 GB RAM and no NVIDIA GPU detected, so expect a small model and long timeouts.
- **Children:** all three eventually. Qwen Code is the M2 target and the only one to install now.
- **Acceptance test owner:** the parent supplies the command. The child may add tests but not edit existing ones.

## Defaults taken (brief defaults, not asked)

Python 3.11+, MIT, claude code as the only parent, worktree plus scrubbed env, sync CLI with `--async`, max_concurrency 1, base working-tree, fresh child per task, file and shell tools only, runs under `.gruntly/`, no usage data leaves the machine, 3 attempts, 120 s no-progress, 900 s budget, 400 changed lines.

## 2026-11-07 — context relay (added at the user's request)

Small local models may not fit a whole task in one context window. A child that runs out writes `.gruntly-handoff.md` (files read, what it understood, done, remaining). gruntly keeps that file out of the diff, feeds it into in-run retries, and returns it in `failure_bundle.handoff` (capped at 1500 chars, with `context_exhausted: true` when the context-overflow error was seen). The parent adds guidance and runs `gruntly continue <run> --guidance "..."`: a fresh child starts in the same worktree with the brief, the notes and the guidance. The attempt counter carries across relays. The parent stays in the loop on purpose, so it can steer each hop; automatic multi-hop without the parent is not built.

## M1 notes

- Gates (all five) landed in M1 rather than M4 because they are small; sandbox level 1, queue and async are also in place but only unit-tested here (bubblewrap needs Linux).
- Main-tree check uses a temp-index `write-tree` fingerprint taken before and after, so any change through an absolute path fails the scope gate.
- Stuck detection normalizes numbers in the failing output, otherwise timing lines make identical failures look different.
- Status `failed` from the brief is unused: gate failures after the last attempt are `escalate`.
- The Qwen prompt goes on stdin because the npm `.cmd` shim on Windows mangles multi-line arguments.

## Benchmark v2 outcome (2026-11-07)

Delegation does not save money on tasks the parent finishes in 3 to 5 turns: the flow is near parity on clean runs, and every parent session has a ~$0.15 floor from its cached context. Policy arm declines to delegate on such tasks, which is the right behaviour. The hypothesis that delegation wins on 15+ turn tasks is untested; the next experiment needs real-repo tasks of that size. Not built: cloud child ladder (would end "nothing leaves your machine"; needs opt-in), scout mode (wait for the long-session result), batching.

## M3-M6 notes

- OpenCode state is isolated per run (XDG dirs under `.gruntly/child-state/`); a foreign OpenCode database made headless runs fail on this machine.
- Hermes could not be verified: it does not build on native Windows (`pywinpty`), and WSL2 cannot reach LM Studio on loopback. Adapter uses the flags from `--help` only.
- Python bytecode: the child and every gate command run with `PYTHONDONTWRITEBYTECODE=1`, and `__pycache__` is purged before gates, because a same-size same-second edit reused a stale `.pyc` (found when the Linux run reproduced a flaky test).
- Apply re-checks path scope but not the main-tree fingerprint: the parent legitimately edits files after a run.
- MCP SDK 2.x renamed `FastMCP` to `MCPServer`; the server imports whichever exists.
- The MCP `.mcp.json` launches the server with `uvx --from "gruntly[mcp] @ git+https://github.com/usegruntly/Gruntly"` until the package is on PyPI.
- Benchmark tasks are synthetic and small (the brief wants tasks from the user's own repos); `bench/validate_tasks.py` proves each starter fails and a reference solution passes the hidden tests.
- Not done in v1: PyPI publish (name re-check needed first), a live sandbox level 1 run, a live Hermes run, ACP adapter (not clearly simpler), research tasks (kind exists, no research path).

## Supervised runs and the person's rules (2026-11-10)

- User design: small models fail at long plans and do not know when they are wrong. So the child plans, the parent's model approves, a fresh child does each small step, and the parent's model reviews every step from the diff and the child's report, telling it what it missed instead of doing the work.
- The reviews run outside the parent's session: each turn there re-reads its whole context (25k to 150k tokens), while a reviewer call carries about 1k tokens of base context plus the rules, the task, the plan and one step. The parent's session gets one block.
- What the parent knows from the chat reaches the reviewer through `.gruntly/rules.md` (rules the person stated, kept by Claude) and the project's CLAUDE.md / AGENTS.md. Softer context still travels only in the task text.

## The child runs as its harness ships; slim profiles removed (2026-11-10)

- User decision: a parent agent (Claude now, others through MCP later) runs any child agent through that child's own harness, as shipped. gruntly does not replace the harness's system prompt or trim its tools; it adds one task message and judges the result.
- Why the profiles went: slimming saved free child tokens but hid what each harness is good at, and the cost that matters is the parent's. The cost benchmark (2026-11-10) found the parent's extra turns, not the child, decide whether delegating pays.
- One entry point everywhere: `gruntly agent-run 'request in plain words'` (skill, manual, CLAUDE.md snippet, MCP `gruntly_delegate`, and `gruntly run 'words'`). A spec stays available for exact control.

## Slim child profiles and evaluate & fix (2026-11-07)
Superseded on 2026-11-10 (see above).


- The child's cost is dominated by its harness, not the task: ~11k input tokens per request for a one-line fix. Profiles (`typist`, `worker`, `default`, `auto`) replace the harness prompt and tool set per task; which profile wins is decided by `bench/run_child_bench.py` (free: no Claude involved), not by argument.
- User decision: the local model gets **no shell**. It is told not to run tests; gruntly runs the acceptance command and all other gates and feeds any failure back as the next attempt, so the parent never sees intermediate failures. `self_check: true` (acceptance command only) stays available as a benchmark arm.
- A native minimal agent loop in gruntly was considered and not built: the slimmed harnesses reach ~1.2k tokens per request, which is the target the native loop was meant to hit.
- `auto` only applies to harnesses that declare `Caps.profiles`; generic and Hermes keep `default` unless a profile is named.

## claude.ai connectors disabled for coding sessions (2026-11-07)

`"disableClaudeAiConnectors": true` was set in the user-level `~/.claude/settings.json` (backup: `settings.json.bak-before-connectors`; remove the key to re-enable). The Gmail, Drive, Docs and Calendar connectors added ~50 tool schemas to every Claude Code session. Verified with a trivial `claude -p --model sonnet` prompt: 53 connector tools before, 0 after; cost $0.0554 -> $0.0347.

Consequence for the benchmarks: **runs made before this change are not comparable with runs made after it.** The per-session cost floor (~$0.15 on Opus, ~$0.07 on Sonnet in benchmark v2) included these schemas, so both the `alone` and `gruntly` arms get cheaper. Any claim about delegation overhead has to be re-measured on the same footing.

## Child trace from stream-json; ACP considered and not built (2026-11-08)

- **Built:** `trace.py` turns the structured events OpenCode, Qwen Code and Hermes already print into one summary (`child: 6 tool calls (read x2, edit x1, run x3), 0 failed, 1 test run`). Counts only; nothing the child wrote is copied, so it is safe unfenced. Behaviour flags (one call repeated 3+ times, half the calls failing) go into `review_hint`. The diff is still taken from the worktree: events are agent-reported.
- **ACP (Agent Client Protocol) read and not built.** `opencode acp`, `qwen --acp` and `hermes acp` share one protocol with tool-call events, permission requests and `session/load`. What it would add over the existing subprocess + stream-json route is a persistent child session for follow-ups. That saves local seconds, not paid tokens (the child's tokens are free), and the three tools already resume sessions from the CLI. Its usage reporting is weaker than their native output, and how OpenCode and Hermes behave over ACP is undocumented. Follow-ups happened in 5 of 14 lean-agent runs, mostly after worker-died errors that are fixed. Revisit if follow-up latency becomes the bottleneck.
- **Fixed in the lean agent:** runs now finish inside one Bash call (a call that ends early takes the detached worker with it); a follow-up after an applied run starts a new run on the current tree; a child that repeats the same long output line is stopped as a loop.

## ACP decision rule applied (2026-11-08)

Rule fixed before the rerun (`bench/persistence_check.py`): build ACP only if at least 25% of lean runs send a real steering follow-up (after a run that passed) AND those follow-ups take at least 30% of the agent-run time. Result on the 10 saved runs of `docs/benchmarks/benchmark-lean2.json` (6 small tasks, all passed, mean $0.019 per run): 1 run in 10 (10%) sent a real follow-up. The time share could not be measured (the transcripts carry no per-call timing for foreground calls), but the rule needs both conditions, so ACP is **not built**. The remaining 2 runs (`parse_duration`, both reps) were not completed: Claude Code stopped the job twice for low system memory.
