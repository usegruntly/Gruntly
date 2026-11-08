# gruntly benchmark (v2)

Local child: `opencode` / `qwen/qwen3.5-9b` at 32k context. Parent: Claude Code (sonnet). Run 2026-11-08. Pass = hidden tests (never shown to the parent or the child) pass afterwards. S = ten small tasks the parent solves in ~4 turns; L = three larger tasks (six bugs, a 15-file rename, a CLI feature). Arms: `alone`; `forced` (told to delegate through the one-call flow); `policy` (may delegate if the skill's triage rule says so).

## Totals by bucket (means over tasks and repetitions)

| bucket | arm | runs | pass rate | cost $/run | vs alone | turns | session splits | wall s | parent output tok | tool-output KB in context | delegated | child tok |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| S | lean | 12 | 83% | 0.016 | - | 3.3 | 0.0 | 112 | 627 | 1.2 | 12/12 | 39590 |
| L | lean | 2 | 0% | 0.033 | - | 6.5 | 0.0 | 112 | 1207 | 3.0 | 1/2 | 22349 |

## Per task (mean over repetitions)

| task | arm | pass | cost $ | turns | wall s | gruntly (status, attempts) | false pass |
|---|---|---|---|---|---|---|---|
| bugs_batch | lean | 0/1 | 0.044 | 10.0 | 213 | passed+applied (1); passed+applied (1); passed+applied (1); error (0); passed+applied (1); passed+applied (1) | 1 |
| cli_json | lean | 0/1 | 0.023 | 3.0 | 11 | - | - |
| flatten | lean | 1/2 | 0.017 | 4.0 | 140 | error (0); passed+applied (1) | - |
| merge_intervals | lean | 2/2 | 0.014 | 2.0 | 69 | passed+applied (2); passed+applied (1) | - |
| paginate | lean | 2/2 | 0.010 | 2.0 | 31 | passed+applied (1); passed+applied (1) | - |
| parse_duration | lean | 1/2 | 0.025 | 6.5 | 325 | error (0); error (0) | - |
| retry | lean | 2/2 | 0.018 | 3.5 | 64 | error (0); passed+applied (1) | - |
| slugify | lean | 2/2 | 0.011 | 2.0 | 44 | passed+applied (1); passed+applied (1) | - |

Accounting: parent cost is Claude Code's own `total_cost_usd` for the whole session (cache reads included), so any takeover after an escalation is counted. Local child tokens are free of paid cost but cost wall time. False pass = gruntly reported `passed` but the hidden tests failed. Transcripts are in `bench/runs/`.
