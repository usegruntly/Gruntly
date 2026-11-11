# gruntly benchmark (v2)

Local child: `opencode` / `qwen/qwen3.5-9b` at 32k context. Parent: Claude Code (haiku). Run 2026-11-11. Pass = hidden tests (never shown to the parent or the child) pass afterwards. S = ten small tasks the parent solves in ~4 turns; L = three larger tasks (six bugs, a 15-file rename, a CLI feature). Arms: `alone`; `forced` (told to delegate through the one-call flow); `policy` (may delegate if the skill's triage rule says so).

## Totals by bucket (means over tasks and repetitions)

| bucket | arm | runs | pass rate | cost $/run | vs alone | turns | session splits | wall s | parent output tok | tool-output KB in context | delegated | child tok |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| S | alone | 10 | 100% | 0.004 | - | 4.9 | 0.0 | 13 | 956 | 1.2 | 0/10 | - |
| L | alone | 5 | 80% | 0.007 | - | 9.8 | 0.0 | 27 | 3453 | 7.5 | 0/5 | - |

## Per task (mean over repetitions)

| task | arm | pass | cost $ | turns | wall s | gruntly (status, attempts) | false pass |
|---|---|---|---|---|---|---|---|
| bugs_batch | alone | 0/1 | 0.009 | 7.0 | 34 | - | - |
| cli_json | alone | 1/1 | 0.005 | 11.0 | 15 | - | - |
| flatten | alone | 1/1 | 0.004 | 5.0 | 13 | - | - |
| inventory_reorder | alone | 1/1 | 0.009 | 9.0 | 40 | - | - |
| lru_cache | alone | 1/1 | 0.004 | 4.0 | 13 | - | - |
| merge_intervals | alone | 1/1 | 0.004 | 5.0 | 11 | - | - |
| paginate | alone | 1/1 | 0.004 | 5.0 | 11 | - | - |
| parse_duration | alone | 1/1 | 0.004 | 4.0 | 13 | - | - |
| rename_domain | alone | 1/1 | 0.007 | 10.0 | 24 | - | - |
| retry | alone | 1/1 | 0.004 | 6.0 | 15 | - | - |
| rolling_mean | alone | 1/1 | 0.004 | 5.0 | 11 | - | - |
| roman | alone | 1/1 | 0.004 | 5.0 | 16 | - | - |
| settings_refactor | alone | 1/1 | 0.006 | 12.0 | 21 | - | - |
| slugify | alone | 1/1 | 0.004 | 5.0 | 12 | - | - |
| word_count | alone | 1/1 | 0.004 | 5.0 | 12 | - | - |

Accounting: parent cost is Claude Code's own `total_cost_usd` for the whole session (cache reads included), so any takeover after an escalation is counted. Local child tokens are free of paid cost but cost wall time. False pass = gruntly reported `passed` but the hidden tests failed. Transcripts are in `bench/runs/`.
