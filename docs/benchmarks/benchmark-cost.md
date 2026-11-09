# gruntly benchmark (v2)

Local child: `opencode` / `nvidia/nemotron-3.5-bolt-e4b` at 32k context. Parent: Claude Code (sonnet). Run 2026-11-10. Pass = hidden tests (never shown to the parent or the child) pass afterwards. S = ten small tasks the parent solves in ~4 turns; L = three larger tasks (six bugs, a 15-file rename, a CLI feature). Arms: `alone`; `forced` (told to delegate through the one-call flow); `policy` (may delegate if the skill's triage rule says so).

## Totals by bucket (means over tasks and repetitions)

| bucket | arm | runs | pass rate | cost $/run | vs alone | turns | session splits | wall s | parent output tok | tool-output KB in context | delegated | child tok |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| S | alone | 18 | 100% | 0.062 | - | 4.7 | 0.0 | 15 | 627 | 0.8 | 0/18 | - |
| S | policy | 17 | 100% | 0.064 | +3% | 4.8 | 0.0 | 16 | 728 | 0.7 | 0/17 | - |
| S | lean | 2 | 50% | 0.046 | -26% | 8.0 | 0.0 | 134 | 2056 | 4.6 | 2/2 | 374266 |
| S | lean_alone | 2 | 100% | 0.015 | -76% | 4.0 | 0.0 | 9 | 513 | 0.5 | 0/2 | - |

## Per task (mean over repetitions)

| task | arm | pass | cost $ | turns | wall s | gruntly (status, attempts) | false pass |
|---|---|---|---|---|---|---|---|
| flatten | alone | 2/2 | 0.061 | 5.0 | 16 | - | - |
| flatten | policy | 2/2 | 0.062 | 4.5 | 14 | - | - |
| flatten | lean | 0/1 | 0.061 | 11.0 | 168 | escalate (2); escalate (1); escalate (1); passed+applied (2); escalate (1); escalate (1) | 1 |
| flatten | lean_alone | 1/1 | 0.016 | 5.0 | 10 | - | - |
| lru_cache | alone | 2/2 | 0.063 | 5.0 | 15 | - | - |
| lru_cache | policy | 2/2 | 0.064 | 4.5 | 14 | - | - |
| lru_cache | lean | 1/1 | 0.031 | 5.0 | 100 | escalate (1); passed+applied (2); escalate (1); escalate (1) | - |
| lru_cache | lean_alone | 1/1 | 0.013 | 3.0 | 8 | - | - |
| merge_intervals | alone | 2/2 | 0.059 | 4.0 | 14 | - | - |
| merge_intervals | policy | 2/2 | 0.064 | 5.0 | 18 | - | - |
| paginate | alone | 2/2 | 0.059 | 4.0 | 14 | - | - |
| paginate | policy | 2/2 | 0.063 | 6.0 | 16 | - | - |
| parse_duration | alone | 2/2 | 0.064 | 5.0 | 17 | - | - |
| parse_duration | policy | 2/2 | 0.066 | 5.0 | 16 | - | - |
| retry | alone | 2/2 | 0.061 | 4.5 | 13 | - | - |
| retry | policy | 2/2 | 0.067 | 5.5 | 17 | - | - |
| rolling_mean | alone | 2/2 | 0.061 | 4.5 | 13 | - | - |
| rolling_mean | policy | 2/2 | 0.062 | 4.0 | 14 | - | - |
| roman | alone | 2/2 | 0.067 | 5.0 | 16 | - | - |
| roman | policy | 1/1 | 0.068 | 5.0 | 16 | - | - |
| slugify | alone | 1/1 | 0.061 | 5.0 | 14 | - | - |
| slugify | policy | 1/1 | 0.060 | 4.0 | 15 | - | - |
| word_count | alone | 1/1 | 0.061 | 5.0 | 15 | - | - |
| word_count | policy | 1/1 | 0.062 | 4.0 | 16 | - | - |

Accounting: parent cost is Claude Code's own `total_cost_usd` for the whole session (cache reads included), so any takeover after an escalation is counted. Local child tokens are free of paid cost but cost wall time. False pass = gruntly reported `passed` but the hidden tests failed. Transcripts are in `bench/runs/`.
