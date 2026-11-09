# gruntly benchmark (v2)

Local child: `hermes` / `poolside/laguna-xs-2.1` at 32k context. Parent: Claude Code (sonnet). Run 2026-11-10. Pass = hidden tests (never shown to the parent or the child) pass afterwards. S = ten small tasks the parent solves in ~4 turns; L = three larger tasks (six bugs, a 15-file rename, a CLI feature). Arms: `alone`; `forced` (told to delegate through the one-call flow); `policy` (may delegate if the skill's triage rule says so).

## Totals by bucket (means over tasks and repetitions)

| bucket | arm | runs | pass rate | cost $/run | vs alone | turns | session splits | wall s | parent output tok | tool-output KB in context | delegated | child tok |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| S | alone | 20 | 95% | 0.062 | - | 4.7 | 0.0 | 14 | 622 | 0.8 | 0/20 | - |
| S | forced | 10 | 100% | 0.090 | +45% | 7.5 | 0.0 | 62 | 962 | 7.0 | 10/10 | - |
| S | policy | 20 | 100% | 0.064 | +4% | 4.8 | 0.0 | 16 | 747 | 0.7 | 0/20 | - |

## Per task (mean over repetitions)

| task | arm | pass | cost $ | turns | wall s | gruntly (status, attempts) | false pass |
|---|---|---|---|---|---|---|---|
| flatten | alone | 2/2 | 0.061 | 5.0 | 16 | - | - |
| flatten | forced | 1/1 | 0.083 | 7.0 | 43 | passed+applied (1) | - |
| flatten | policy | 2/2 | 0.062 | 4.5 | 14 | - | - |
| lru_cache | alone | 2/2 | 0.063 | 5.0 | 15 | - | - |
| lru_cache | forced | 1/1 | 0.085 | 7.0 | 37 | passed+applied (1) | - |
| lru_cache | policy | 2/2 | 0.064 | 4.5 | 14 | - | - |
| merge_intervals | alone | 2/2 | 0.059 | 4.0 | 14 | - | - |
| merge_intervals | forced | 1/1 | 0.087 | 7.0 | 61 | passed+applied (1) | - |
| merge_intervals | policy | 2/2 | 0.064 | 5.0 | 18 | - | - |
| paginate | alone | 2/2 | 0.059 | 4.0 | 14 | - | - |
| paginate | forced | 1/1 | 0.084 | 7.0 | 64 | passed+applied (1) | - |
| paginate | policy | 2/2 | 0.063 | 6.0 | 16 | - | - |
| parse_duration | alone | 2/2 | 0.064 | 5.0 | 17 | - | - |
| parse_duration | forced | 1/1 | 0.091 | 8.0 | 57 | passed+applied (1) | - |
| parse_duration | policy | 2/2 | 0.066 | 5.0 | 16 | - | - |
| retry | alone | 2/2 | 0.061 | 4.5 | 13 | - | - |
| retry | forced | 1/1 | 0.095 | 8.0 | 86 | passed+applied (1) | - |
| retry | policy | 2/2 | 0.067 | 5.5 | 17 | - | - |
| rolling_mean | alone | 2/2 | 0.061 | 4.5 | 13 | - | - |
| rolling_mean | forced | 1/1 | 0.086 | 7.0 | 55 | passed+applied (1) | - |
| rolling_mean | policy | 2/2 | 0.062 | 4.0 | 14 | - | - |
| roman | alone | 2/2 | 0.067 | 5.0 | 16 | - | - |
| roman | forced | 1/1 | 0.091 | 7.0 | 69 | passed+applied (1) | - |
| roman | policy | 2/2 | 0.069 | 5.0 | 16 | - | - |
| slugify | alone | 2/2 | 0.061 | 5.0 | 13 | - | - |
| slugify | forced | 1/1 | 0.089 | 8.0 | 38 | passed+applied (1) | - |
| slugify | policy | 2/2 | 0.062 | 4.5 | 14 | - | - |
| word_count | alone | 1/2 | 0.063 | 5.0 | 14 | - | - |
| word_count | forced | 1/1 | 0.103 | 9.0 | 110 | error (0) | - |
| word_count | policy | 2/2 | 0.062 | 4.5 | 15 | - | - |

Accounting: parent cost is Claude Code's own `total_cost_usd` for the whole session (cache reads included), so any takeover after an escalation is counted. Local child tokens are free of paid cost but cost wall time. False pass = gruntly reported `passed` but the hidden tests failed. Transcripts are in `bench/runs/`.
