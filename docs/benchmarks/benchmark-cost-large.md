# gruntly benchmark (v2)

Local child: `hermes` / `poolside/laguna-xs-2.1` at 32k context. Parent: Claude Code (sonnet). Run 2026-11-10. Pass = hidden tests (never shown to the parent or the child) pass afterwards. S = ten small tasks the parent solves in ~4 turns; L = three larger tasks (six bugs, a 15-file rename, a CLI feature). Arms: `alone`; `forced` (told to delegate through the one-call flow); `policy` (may delegate if the skill's triage rule says so).

## Totals by bucket (means over tasks and repetitions)

| bucket | arm | runs | pass rate | cost $/run | vs alone | turns | session splits | wall s | parent output tok | tool-output KB in context | delegated | child tok |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| L | alone | 3 | 100% | 0.070 | - | 4.3 | 0.0 | 17 | 785 | 2.4 | 0/3 | - |
| L | forced | 3 | 100% | 0.090 | +28% | 7.3 | 0.0 | 409 | 1118 | 5.2 | 2/3 | - |

## Per task (mean over repetitions)

| task | arm | pass | cost $ | turns | wall s | gruntly (status, attempts) | false pass |
|---|---|---|---|---|---|---|---|
| bugs_batch | alone | 1/1 | 0.080 | 4.0 | 21 | - | - |
| bugs_batch | forced | 1/1 | 0.102 | 8.0 | 775 | passed+applied (1); passed+applied (1); passed+applied (1); passed+applied (2) | - |
| cli_json | alone | 1/1 | 0.066 | 5.0 | 16 | - | - |
| cli_json | forced | 1/1 | 0.080 | 6.0 | 159 | passed+applied (1) | - |
| rename_domain | alone | 1/1 | 0.064 | 4.0 | 15 | - | - |
| rename_domain | forced | 1/1 | 0.088 | 8.0 | 293 | - | - |

Accounting: parent cost is Claude Code's own `total_cost_usd` for the whole session (cache reads included), so any takeover after an escalation is counted. Local child tokens are free of paid cost but cost wall time. False pass = gruntly reported `passed` but the hidden tests failed. Transcripts are in `bench/runs/`.
