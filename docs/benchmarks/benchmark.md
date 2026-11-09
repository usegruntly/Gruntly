# gruntly benchmark

Local child: `opencode` / `qwen/qwen3.5-9b`. Parent: Claude Code (default model). Run on 2026-11-07. Pass = hidden tests (never shown to parent or child) pass after the run.

| task | mode | pass | cost $ | parent out tok | parent ctx tok | turns | wall s | gruntly status (attempts) | child tok |
|---|---|---|---|---|---|---|---|---|---|
| flatten | alone | yes | 0.069 | 404 | 89401 | 4 | 12 | - | - |
| flatten | gruntly | yes | 0.113 | 1176 | 210196 | 9 | 228 | escalate (2) | 12465 |
| lru_cache | alone | yes | 0.074 | 695 | 90035 | 5 | 14 | - | - |
| lru_cache | gruntly | yes | 0.103 | 863 | 202173 | 7 | 335 | passed (1) | 77265 |
| merge_intervals | alone | yes | 0.070 | 455 | 89642 | 4 | 11 | - | - |
| merge_intervals | gruntly | NO | 0.148 | 1238 | 260454 | 7 | 328 | passed (1) | 47384 |
| paginate | alone | yes | 0.070 | 426 | 89602 | 4 | 26 | - | - |
| paginate | gruntly | yes | 0.118 | 1295 | 247440 | 9 | 194 | escalate (2) | 51601 |
| parse_duration | alone | yes | 0.075 | 809 | 90135 | 5 | 14 | - | - |
| parse_duration | gruntly | yes | 0.158 | 2598 | 408625 | 13 | 395 | escalate (2) | 94134 |
| retry | alone | yes | 0.071 | 530 | 89611 | 4 | 13 | - | - |
| retry | gruntly | yes | 0.111 | 1063 | 210209 | 9 | 170 | passed (2) | 73777 |
| rolling_mean | alone | yes | 0.072 | 533 | 89762 | 4 | 13 | - | - |
| rolling_mean | gruntly | yes | 0.115 | 1133 | 247032 | 9 | 67 | passed (1) | 47264 |
| roman | alone | yes | 0.078 | 1035 | 90348 | 5 | 15 | - | - |
| roman | gruntly | yes | 0.116 | 1158 | 245834 | 9 | 91 | passed (1) | 48592 |
| slugify | alone | yes | 0.072 | 539 | 90001 | 5 | 12 | - | - |
| slugify | gruntly | yes | 0.114 | 1084 | 246285 | 9 | 105 | passed (1) | 59685 |
| word_count | alone | yes | 0.071 | 473 | 89675 | 4 | 13 | - | - |
| word_count | gruntly | yes | 0.130 | 1551 | 321984 | 11 | 365 | passed (1) | 46950 |

## Totals

| mode | tasks | passed | total cost $ | parent output tok | parent context tok | mean wall s | local child tok |
|---|---|---|---|---|---|---|---|
| alone | 10 | 10 | 0.722 | 5899 | 898212 | 14 | - |
| gruntly | 10 | 9 | 1.226 | 13159 | 2600232 | 228 | 559117 |

Accounting notes: parent tokens and cost cover the whole Claude session, including any takeover after an escalation. Context tokens include cache reads, which are billed at a lower rate; cost is Claude Code's own `total_cost_usd`. Local child tokens are free of paid cost but cost wall time. Tasks are small synthetic functions, so treat the numbers as a floor on task difficulty, not a verdict; add tasks from your own repos under `bench/tasks/`.

## What this run shows

On these ten small tasks, delegating did **not** save paid tokens or money. It cost more and was slower.

| | alone | with gruntly |
|---|---|---|
| passed hidden tests | 10 / 10 | 9 / 10 |
| parent cost | $0.72 | $1.23 (+70%) |
| parent output tokens | 5.9k | 13.2k |
| parent context tokens (incl. cache reads) | 0.90M | 2.60M |
| mean wall time | 14 s | 228 s |

Why:
- **The tasks are too easy to delegate.** Claude alone solves each in about 4 turns for about $0.07. Delegating adds a fixed overhead of roughly $0.04 to $0.08 per task: loading the skill, writing the spec, reading the result, checking the diff, applying and re-running tests (about 9 turns instead of 4).
- **Three tasks escalated** (flatten, paginate, parse_duration): the 9B model failed twice, then Claude did the work itself. Those runs paid for both attempts.
- **One false pass:** on merge_intervals gruntly reported `passed` (the visible tests), but the hidden tests failed because the child's fix missed an edge case. This is why the skill says `passed` is not proof of correctness.
- The local model was also much slower than the parent (child time dominates wall time).

What it does **not** show: whether delegation pays on larger work. Delegation can only win when producing the work costs the parent more than the roughly $0.05 to $0.10 of fixed overhead, for example multi-file changes that need many turns and large reads. These tasks cannot test that, so no saving is claimed. Next experiments: tasks that take the parent 20+ turns, a shorter skill and fewer verification turns, and tasks from real repos.
