# gruntly benchmark (v2)

Local child: `hermes` / `poolside/laguna-xs-2.1` at 32k context. Parent: Claude Code (sonnet). Run 2026-11-11. Pass = hidden tests (never shown to the parent or the child) pass afterwards. S = ten small tasks the parent solves in ~4 turns; L = three larger tasks (six bugs, a 15-file rename, a CLI feature). Arms: `alone`; `forced` (told to delegate through the one-call flow); `policy` (may delegate if the skill's triage rule says so).

## Totals by bucket (means over tasks and repetitions)

| bucket | arm | runs | pass rate | cost $/run | vs alone | turns | session splits | wall s | parent output tok | tool-output KB in context | delegated | child tok |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| S | forced | 5 | 80% | 0.056 | - | 2.0 | 0.0 | 74 | 306 | 1.5 | 5/5 | - |

## Per task (mean over repetitions)

| task | arm | pass | cost $ | turns | wall s | gruntly (status, attempts) | false pass |
|---|---|---|---|---|---|---|---|
| paginate | forced | 1/1 | 0.054 | 2.0 | 47 | passed+applied (1) | - |
| retry | forced | 1/1 | 0.056 | 2.0 | 75 | passed+applied (1) | - |
| roman | forced | 1/1 | 0.059 | 2.0 | 158 | passed+applied (1) | - |
| slugify | forced | 1/1 | 0.055 | 2.0 | 53 | passed+applied (1) | - |
| word_count | forced | 0/1 | 0.055 | 2.0 | 38 | passed+applied (1) | 1 |

Accounting: parent cost is Claude Code's own `total_cost_usd` for the whole session (cache reads included), so any takeover after an escalation is counted. Local child tokens are free of paid cost but cost wall time. False pass = gruntly reported `passed` but the hidden tests failed. Transcripts are in `bench/runs/`.
