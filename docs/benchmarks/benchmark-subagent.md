# gruntly benchmark (v2)

Local child: `opencode` / `qwen/qwen3.5-9b` at 32k context. Parent: Claude Code (sonnet). Run 2026-11-11. Pass = hidden tests (never shown to the parent or the child) pass afterwards. S = ten small tasks the parent solves in ~4 turns; L = three larger tasks (six bugs, a 15-file rename, a CLI feature). Arms: `alone`; `forced` (told to delegate through the one-call flow); `policy` (may delegate if the skill's triage rule says so).

## Totals by bucket (means over tasks and repetitions)

| bucket | arm | runs | pass rate | cost $/run | vs alone | turns | session splits | wall s | parent output tok | tool-output KB in context | delegated | child tok |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| S | subagent | 3 | 100% | 0.071 | - | 2.0 | 1.0 | 22 | 196 | 2.5 | 0/3 | - |
| L | subagent | 1 | 100% | 0.076 | - | 2.0 | 1.0 | 36 | 235 | 6.3 | 0/1 | - |

## Per task (mean over repetitions)

| task | arm | pass | cost $ | turns | wall s | gruntly (status, attempts) | false pass |
|---|---|---|---|---|---|---|---|
| cli_json | subagent | 1/1 | 0.076 | 2.0 | 36 | - | - |
| paginate | subagent | 1/1 | 0.071 | 2.0 | 22 | - | - |
| retry | subagent | 1/1 | 0.071 | 2.0 | 22 | - | - |
| slugify | subagent | 1/1 | 0.071 | 2.0 | 21 | - | - |

Accounting: parent cost is Claude Code's own `total_cost_usd` for the whole session (cache reads included), so any takeover after an escalation is counted. Local child tokens are free of paid cost but cost wall time. False pass = gruntly reported `passed` but the hidden tests failed. Transcripts are in `bench/runs/`.
