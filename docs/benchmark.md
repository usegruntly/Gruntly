# gruntly benchmark

Local child: `opencode` / `qwen/qwen3.5-9b`. Parent: Claude Code (default model). Run on 2026-11-07. Pass = hidden tests (never shown to parent or child) pass after the run.

| task | mode | pass | cost $ | parent out tok | parent ctx tok | turns | wall s | gruntly status (attempts) | child tok |
|---|---|---|---|---|---|---|---|---|---|
| flatten | alone | yes | 0.069 | 404 | 89401 | 4 | 12 | - | - |
| flatten | gruntly | yes | 0.103 | 792 | 203045 | 7 | 85 | passed (1) | 47154 |
| lru_cache | alone | yes | 0.074 | 695 | 90035 | 5 | 14 | - | - |
| lru_cache | gruntly | yes | 0.180 | 2202 | 423117 | 11 | 372 | - | - |
| merge_intervals | alone | yes | 0.070 | 455 | 89642 | 4 | 11 | - | - |
| merge_intervals | gruntly | yes | 0.188 | 1220 | 292944 | 7 | 471 | passed (1) | 46558 |
| paginate | alone | yes | 0.070 | 426 | 89602 | 4 | 26 | - | - |
| paginate | gruntly | NO | 0.097 | 918 | 135302 | 6 | 21 | - | - |
| parse_duration | alone | yes | 0.075 | 809 | 90135 | 5 | 14 | - | - |
| parse_duration | gruntly | NO | 0.097 | 946 | 135360 | 6 | 23 | - | - |
| retry | alone | yes | 0.071 | 530 | 89611 | 4 | 13 | - | - |
| retry | gruntly | NO | 0.099 | 1096 | 135777 | 6 | 20 | - | - |
| rolling_mean | alone | yes | 0.072 | 533 | 89762 | 4 | 13 | - | - |
| rolling_mean | gruntly | NO | 0.095 | 755 | 135351 | 6 | 23 | - | - |
| roman | alone | yes | 0.078 | 1035 | 90348 | 5 | 15 | - | - |
| roman | gruntly | yes | 0.131 | 2028 | 249683 | 9 | 193 | passed (1) | 48339 |
| slugify | alone | yes | 0.072 | 539 | 90001 | 5 | 12 | - | - |
| slugify | gruntly | NO | 0.096 | 886 | 135262 | 6 | 16 | - | - |
| word_count | alone | yes | 0.071 | 473 | 89675 | 4 | 13 | - | - |
| word_count | gruntly | NO | 0.096 | 881 | 135358 | 6 | 16 | - | - |

## Totals

| mode | tasks | passed | total cost $ | parent output tok | parent context tok | mean wall s | local child tok |
|---|---|---|---|---|---|---|---|
| alone | 10 | 10 | 0.722 | 5899 | 898212 | 14 | - |
| gruntly | 10 | 4 | 1.182 | 11724 | 1981199 | 124 | 142051 |

Accounting notes: parent tokens and cost cover the whole Claude session, including any takeover after an escalation. Context tokens include cache reads, which are billed at a lower rate; cost is Claude Code's own `total_cost_usd`. Local child tokens are free of paid cost but cost wall time. Tasks are small synthetic functions, so treat the numbers as a floor on task difficulty, not a verdict; add tasks from your own repos under `bench/tasks/`.
