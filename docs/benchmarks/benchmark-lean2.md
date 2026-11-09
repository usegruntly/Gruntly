# gruntly benchmark (v2)

Local child: `opencode` / `qwen/qwen3.5-9b` at 32k context. Parent: Claude Code (sonnet). Run 2026-11-08. Pass = hidden tests (never shown to the parent or the child) pass afterwards. S = ten small tasks the parent solves in ~4 turns; L = three larger tasks (six bugs, a 15-file rename, a CLI feature). Arms: `alone`; `forced` (told to delegate through the one-call flow); `policy` (may delegate if the skill's triage rule says so).

## Totals by bucket (means over tasks and repetitions)

| bucket | arm | runs | pass rate | cost $/run | vs alone | turns | session splits | wall s | parent output tok | tool-output KB in context | delegated | child tok |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| S | lean | 10 | 100% | 0.019 | - | 2.7 | 0.0 | 96 | 679 | 2.4 | 10/10 | 66617 |

## Per task (mean over repetitions)

| task | arm | pass | cost $ | turns | wall s | gruntly (status, attempts) | false pass |
|---|---|---|---|---|---|---|---|
| flatten | lean | 2/2 | 0.035 | 4.5 | 237 | escalate (4); passed+applied (1) | - |
| merge_intervals | lean | 2/2 | 0.014 | 2.0 | 64 | passed+applied (2); passed+applied (1) | - |
| paginate | lean | 2/2 | 0.011 | 2.0 | 37 | passed+applied (1); passed+applied (1) | - |
| retry | lean | 2/2 | 0.023 | 3.0 | 100 | passed+applied (1); passed+applied (1); passed+applied (1); passed+applied (1) | - |
| slugify | lean | 2/2 | 0.011 | 2.0 | 38 | passed+applied (1); passed+applied (1) | - |

Accounting: parent cost is Claude Code's own `total_cost_usd` for the whole session (cache reads included), so any takeover after an escalation is counted. Local child tokens are free of paid cost but cost wall time. False pass = gruntly reported `passed` but the hidden tests failed. Transcripts are in `bench/runs/`.
