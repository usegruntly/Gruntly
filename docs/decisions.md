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
