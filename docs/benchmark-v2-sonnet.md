# gruntly benchmark (v2)

Local child: `opencode` / `qwen/qwen3.5-9b` at 32k context. Parent: Claude Code (sonnet). Run 2026-11-07. Pass = hidden tests (never shown to the parent or the child) pass afterwards. S = ten small tasks the parent solves in ~4 turns; L = three larger tasks (six bugs, a 15-file rename, a CLI feature). Arms: `alone`; `forced` (told to delegate through the one-call flow); `policy` (may delegate if the skill's triage rule says so).

## Totals by bucket (means over tasks and repetitions)

| bucket | arm | runs | pass rate | cost $/run | vs alone | turns | wall s | parent output tok | tool-output KB in context | delegated | child tok |
|---|---|---|---|---|---|---|---|---|---|---|---|
| S | alone | 5 | 100% | 0.072 | - | 4.6 | 18 | 568 | 0.8 | 0/5 | - |
| S | forced | 5 | 100% | 0.090 | +25% | 2.2 | 114 | 284 | 0.8 | 5/5 | 600490 |
| S | policy | 5 | 100% | 0.074 | +3% | 4.2 | 19 | 542 | 0.5 | 0/5 | - |
| L | alone | 3 | 100% | 0.079 | - | 4.0 | 20 | 687 | 2.4 | 0/3 | - |
| L | forced | 3 | 67% | 0.092 | +16% | 2.0 | 288 | 216 | 0.9 | 3/3 | 587959 |
| L | policy | 3 | 100% | 0.084 | +6% | 4.3 | 27 | 716 | 2.3 | 0/3 | - |

## Per task (mean over repetitions)

| task | arm | pass | cost $ | turns | wall s | gruntly (status, attempts) | false pass |
|---|---|---|---|---|---|---|---|
| bugs_batch | alone | 1/1 | 0.088 | 4.0 | 25 | - | - |
| bugs_batch | forced | 0/1 | 0.086 | 2.0 | 118 | passed+applied (1) | 1 |
| bugs_batch | policy | 1/1 | 0.090 | 4.0 | 34 | - | - |
| cli_json | alone | 1/1 | 0.080 | 5.0 | 19 | - | - |
| cli_json | forced | 1/1 | 0.097 | 2.0 | 324 | passed+applied (1) | - |
| cli_json | policy | 1/1 | 0.082 | 5.0 | 23 | - | - |
| flatten | alone | 1/1 | 0.071 | 5.0 | 18 | - | - |
| flatten | forced | 1/1 | 0.093 | 3.0 | 63 | passed+applied (1) | - |
| flatten | policy | 1/1 | 0.073 | 4.0 | 14 | - | - |
| paginate | alone | 1/1 | 0.069 | 4.0 | 19 | - | - |
| paginate | forced | 1/1 | 0.085 | 2.0 | 141 | passed+applied (1) | - |
| paginate | policy | 1/1 | 0.073 | 4.0 | 17 | - | - |
| parse_duration | alone | 1/1 | 0.075 | 5.0 | 18 | - | - |
| parse_duration | forced | 1/1 | 0.091 | 2.0 | 194 | passed+applied (1) | - |
| parse_duration | policy | 1/1 | 0.077 | 5.0 | 22 | - | - |
| rename_domain | alone | 1/1 | 0.069 | 3.0 | 15 | - | - |
| rename_domain | forced | 1/1 | 0.093 | 2.0 | 423 | passed+applied (1) | - |
| rename_domain | policy | 1/1 | 0.078 | 4.0 | 23 | - | - |
| retry | alone | 1/1 | 0.074 | 5.0 | 19 | - | - |
| retry | forced | 1/1 | 0.092 | 2.0 | 102 | passed+applied (1) | - |
| retry | policy | 1/1 | 0.074 | 4.0 | 25 | - | - |
| slugify | alone | 1/1 | 0.071 | 4.0 | 18 | - | - |
| slugify | forced | 1/1 | 0.091 | 2.0 | 70 | passed+applied (1) | - |
| slugify | policy | 1/1 | 0.073 | 4.0 | 15 | - | - |

Accounting: parent cost is Claude Code's own `total_cost_usd` for the whole session (cache reads included), so any takeover after an escalation is counted. Local child tokens are free of paid cost but cost wall time. False pass = gruntly reported `passed` but the hidden tests failed. Transcripts are in `bench/runs/`.
