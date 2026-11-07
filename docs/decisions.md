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

## M3-M6 notes

- OpenCode state is isolated per run (XDG dirs under `.gruntly/child-state/`); a foreign OpenCode database made headless runs fail on this machine.
- Hermes could not be verified: it does not build on native Windows (`pywinpty`), and WSL2 cannot reach LM Studio on loopback. Adapter uses the flags from `--help` only.
- Python bytecode: the child and every gate command run with `PYTHONDONTWRITEBYTECODE=1`, and `__pycache__` is purged before gates, because a same-size same-second edit reused a stale `.pyc` (found when the Linux run reproduced a flaky test).
- Apply re-checks path scope but not the main-tree fingerprint: the parent legitimately edits files after a run.
- MCP SDK 2.x renamed `FastMCP` to `MCPServer`; the server imports whichever exists.
- The MCP `.mcp.json` launches the server with `uvx --from "gruntly[mcp] @ git+https://github.com/usegruntly/Gruntly"` until the package is on PyPI.
- Benchmark tasks are synthetic and small (the brief wants tasks from the user's own repos); `bench/validate_tasks.py` proves each starter fails and a reference solution passes the hidden tests.
- Not done in v1: PyPI publish (name re-check needed first), a live sandbox level 1 run, a live Hermes run, ACP adapter (not clearly simpler), research tasks (kind exists, no research path).
