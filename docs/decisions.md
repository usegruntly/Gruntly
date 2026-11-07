# Decisions

## 2026-11-07 — blocking questions

- **OS/shell:** both. WSL2 Ubuntu is the primary dev and test target. Core code stays portable; native Windows gets a process-tree kill fallback, and sandbox level 1 (bubblewrap) is Linux-only.
- **Local model:** LM Studio or llama.cpp via an OpenAI-compatible endpoint. Model, context length and URL to be confirmed in M0. Dev machine has 15.7 GB RAM and no NVIDIA GPU detected, so expect a small model and long timeouts.
- **Children:** all three eventually. Qwen Code is the M2 target and the only one to install now.
- **Acceptance test owner:** the parent supplies the command. The child may add tests but not edit existing ones.

## Defaults taken (brief defaults, not asked)

Python 3.11+, MIT, claude code as the only parent, worktree plus scrubbed env, sync CLI with `--async`, max_concurrency 1, base working-tree, fresh child per task, file and shell tools only, runs under `.gruntly/`, no usage data leaves the machine, 3 attempts, 120 s no-progress, 900 s budget, 400 changed lines.
