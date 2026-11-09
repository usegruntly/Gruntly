# gruntly benchmark (v2)

Local child: `opencode` / `qwen/qwen3.5-9b` at 32k context. Parent: Claude Code (sonnet). Run 2026-11-08. Pass = hidden tests (never shown to the parent or the child) pass afterwards. S = ten small tasks the parent solves in ~4 turns; L = three larger tasks (six bugs, a 15-file rename, a CLI feature). Arms: `alone`; `forced` (told to delegate through the one-call flow); `policy` (may delegate if the skill's triage rule says so).

## Totals by bucket (means over tasks and repetitions)

| bucket | arm | runs | pass rate | cost $/run | vs alone | turns | session splits | wall s | parent output tok | tool-output KB in context | delegated | child tok |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| S | gdA | 12 | 100% | 0.059 | - | 2.7 | 0.0 | 43 | 536 | 0.6 | 11/12 | 47799 |
| S | gdAB | 12 | 100% | 0.059 | - | 2.4 | 0.0 | 51 | 534 | 0.9 | 11/12 | 53672 |
| L | gdA | 4 | 100% | 0.074 | - | 4.2 | 0.0 | 17 | 1158 | 2.0 | 0/4 | - |
| L | gdAB | 4 | 100% | 0.075 | - | 5.0 | 0.0 | 17 | 1128 | 2.1 | 0/4 | - |

## Per task (mean over repetitions)

| task | arm | pass | cost $ | turns | wall s | gruntly (status, attempts) | false pass |
|---|---|---|---|---|---|---|---|
| bugs_batch | gdA | 2/2 | 0.078 | 3.5 | 19 | - | - |
| bugs_batch | gdAB | 2/2 | 0.078 | 4.0 | 19 | - | - |
| cli_json | gdA | 2/2 | 0.070 | 5.0 | 15 | - | - |
| cli_json | gdAB | 2/2 | 0.073 | 6.0 | 16 | - | - |
| flatten | gdA | 2/2 | 0.049 | 1.0 | 32 | passed+applied (1); passed+applied (1) | - |
| flatten | gdAB | 2/2 | 0.049 | 1.0 | 41 | passed+applied (1); passed+applied (1) | - |
| merge_intervals | gdA | 2/2 | 0.055 | 2.0 | 40 | passed+applied (1); passed+applied (1) | - |
| merge_intervals | gdAB | 2/2 | 0.052 | 1.5 | 38 | passed+applied (1); passed+applied (1) | - |
| paginate | gdA | 2/2 | 0.065 | 4.0 | 36 | passed+applied (1); passed+applied (1) | - |
| paginate | gdAB | 2/2 | 0.059 | 3.0 | 34 | passed+applied (1); passed+applied (1) | - |
| parse_duration | gdA | 2/2 | 0.074 | 4.0 | 76 | passed+applied (1) | - |
| parse_duration | gdAB | 2/2 | 0.079 | 4.5 | 96 | passed+applied (1) | - |
| retry | gdA | 2/2 | 0.064 | 4.0 | 44 | passed+applied (1); passed+applied (1) | - |
| retry | gdAB | 2/2 | 0.068 | 3.5 | 60 | passed+applied (1); passed+applied (1) | - |
| slugify | gdA | 2/2 | 0.049 | 1.0 | 32 | passed+applied (1); passed+applied (1) | - |
| slugify | gdAB | 2/2 | 0.050 | 1.0 | 36 | passed+applied (1); passed+applied (1) | - |

Accounting: parent cost is Claude Code's own `total_cost_usd` for the whole session (cache reads included), so any takeover after an escalation is counted. Local child tokens are free of paid cost but cost wall time. False pass = gruntly reported `passed` but the hidden tests failed. Transcripts are in `bench/runs/`.
