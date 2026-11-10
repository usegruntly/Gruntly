# gruntly benchmark (v2)

Local child: `hermes` / `poolside/laguna-xs-2.1` at 32k context. Parent: Claude Code (sonnet). Run 2026-11-10. Pass = hidden tests (never shown to the parent or the child) pass afterwards. S = ten small tasks the parent solves in ~4 turns; L = three larger tasks (six bugs, a 15-file rename, a CLI feature). Arms: `alone`; `forced` (told to delegate through the one-call flow); `policy` (may delegate if the skill's triage rule says so).

## Totals by bucket (means over tasks and repetitions)

| bucket | arm | runs | pass rate | cost $/run | vs alone | turns | session splits | wall s | parent output tok | tool-output KB in context | delegated | child tok |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| L | alone | 3 | 67% | 0.074 | - | 5.3 | 0.0 | 20 | 930 | 2.7 | 0/3 | - |
| L | planner | 3 | 0% | 0.075 | +2% | 3.3 | 0.0 | 630 | 1373 | 2.2 | 3/3 | - |

## Per task (mean over repetitions)

| task | arm | pass | cost $ | turns | wall s | gruntly (status, attempts) | false pass |
|---|---|---|---|---|---|---|---|
| bugs_batch | alone | 1/1 | 0.075 | 4.0 | 19 | - | - |
| bugs_batch | planner | 0/1 | 0.067 | 2.0 | 95 | passed+applied (1) | 1 |
| cli_json | alone | 0/1 | 0.087 | 9.0 | 22 | - | - |
| cli_json | planner | 0/1 | 0.086 | 5.0 | 1055 | timeout (2); passed+applied (1) | 1 |
| rename_domain | alone | 1/1 | 0.059 | 3.0 | 18 | - | - |
| rename_domain | planner | 0/1 | 0.072 | 3.0 | 741 | escalate (4) | - |

Accounting: parent cost is Claude Code's own `total_cost_usd` for the whole session (cache reads included), so any takeover after an escalation is counted. Local child tokens are free of paid cost but cost wall time. False pass = gruntly reported `passed` but the hidden tests failed. Transcripts are in `bench/runs/`.
