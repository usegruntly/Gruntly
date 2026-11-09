# gruntly benchmark (v2)

Local child: `opencode` / `nvidia/nemotron-3.5-bolt-e4b` at 32k context. Parent: Claude Code (sonnet). Run 2026-11-10. Pass = hidden tests (never shown to the parent or the child) pass afterwards. S = ten small tasks the parent solves in ~4 turns; L = three larger tasks (six bugs, a 15-file rename, a CLI feature). Arms: `alone`; `forced` (told to delegate through the one-call flow); `policy` (may delegate if the skill's triage rule says so).

## Totals by bucket (means over tasks and repetitions)

| bucket | arm | runs | pass rate | cost $/run | vs alone | turns | session splits | wall s | parent output tok | tool-output KB in context | delegated | child tok |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| S | alone | 2 | 100% | 0.059 | - | 4.0 | 0.0 | 13 | 437 | 1.1 | 0/2 | - |
| S | policy | 2 | 100% | 0.062 | +5% | 5.0 | 0.0 | 14 | 544 | 0.8 | 0/2 | - |
| S | lean | 2 | 50% | 0.030 | -49% | 4.5 | 0.0 | 68 | 1092 | 2.5 | 2/2 | 111522 |
| S | lean_alone | 2 | 100% | 0.021 | -65% | 4.5 | 0.0 | 10 | 446 | 0.8 | 0/2 | - |

## Per task (mean over repetitions)

| task | arm | pass | cost $ | turns | wall s | gruntly (status, attempts) | false pass |
|---|---|---|---|---|---|---|---|
| paginate | alone | 1/1 | 0.059 | 4.0 | 13 | - | - |
| paginate | policy | 1/1 | 0.064 | 6.0 | 14 | - | - |
| paginate | lean | 1/1 | 0.025 | 5.0 | 77 | escalate (1); passed+applied (2); escalate (1); escalate (1) | - |
| paginate | lean_alone | 1/1 | 0.013 | 4.0 | 10 | - | - |
| slugify | alone | 1/1 | 0.059 | 4.0 | 13 | - | - |
| slugify | policy | 1/1 | 0.060 | 4.0 | 13 | - | - |
| slugify | lean | 0/1 | 0.036 | 4.0 | 59 | escalate (2) | - |
| slugify | lean_alone | 1/1 | 0.028 | 5.0 | 10 | - | - |

Accounting: parent cost is Claude Code's own `total_cost_usd` for the whole session (cache reads included), so any takeover after an escalation is counted. Local child tokens are free of paid cost but cost wall time. False pass = gruntly reported `passed` but the hidden tests failed. Transcripts are in `bench/runs/`.
