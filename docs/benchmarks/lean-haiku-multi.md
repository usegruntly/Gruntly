# gruntly benchmark (v2)

Local child: `claude` / `haiku` at 32k context. Parent: Claude Code (sonnet). Run 2026-11-12. Pass = hidden tests (never shown to the parent or the child) pass afterwards. S = ten small tasks the parent solves in ~4 turns; L = three larger tasks (six bugs, a 15-file rename, a CLI feature); R = real fix commits of public repositories (hidden tests = the fix's own). Arms: `alone`; `forced` (told to delegate through the one-call flow); `policy` (may delegate if the skill's triage rule says so).

## Totals by bucket (means over tasks and repetitions)

| bucket | arm | runs | pass rate | cost $/run | reviewer $ | vs alone | marginal $ (after the $0.045 floor) | vs alone, marginal | cost of a pass $ | turns | takeover edits | session splits | wall s | parent output tok | tool-output KB in context | delegated | child tok |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| L | alone | 10 | 100% | 0.105 | 0.0000 | - | 0.060 | - | 0.105 | 13.1 | 0.0 | 0.0 | 23 | 2246 | 4.7 | 0/10 | - |
| L | lean | 10 | 60% | 0.049 | 0.0000 | -54% | 0.004 | -94% | 0.081 | 3.2 | 0.0 | 0.0 | 76 | 1529 | 5.0 | 10/10 | 2205707 |

## Share of runs that passed within a cost cap (parent + reviewers per run; a run over the cap counts as not solved)

| arm | runs | <= $0.05 | <= $0.10 | <= $0.20 | <= $0.50 | <= $1.00 |
|---|---|---|---|---|---|---|
| alone | 10 | 0% | 20% | 100% | 100% | 100% |
| lean | 10 | 50% | 60% | 60% | 60% | 60% |

## Per task (mean over repetitions)

| task | arm | pass | cost $ | turns | wall s | gruntly (status, attempts) | false pass |
|---|---|---|---|---|---|---|---|
| bugs_batch | alone | 2/2 | 0.124 | 10.5 | 24 | - | - |
| bugs_batch | lean | 2/2 | 0.048 | 2.0 | 91 | passed+applied (1); passed+applied (1); passed+applied (1); passed+applied (1); passed+applied (1); passed+applied (1); passed+applied (1); passed+applied (1); passed+applied (1); passed+applied (1); passed+applied (1); passed+applied (1) | - |
| cli_json | alone | 2/2 | 0.074 | 8.0 | 14 | - | - |
| cli_json | lean | 2/2 | 0.031 | 3.0 | 50 | escalate (1); passed+applied (1); passed+applied (1); escalate (1) | - |
| inventory_reorder | alone | 2/2 | 0.112 | 15.5 | 26 | - | - |
| inventory_reorder | lean | 0/2 | 0.078 | 4.0 | 124 | passed+applied (1); passed+applied (2); passed+applied (1); escalate (4); passed+applied (1) | 2 |
| rename_domain | alone | 2/2 | 0.104 | 11.0 | 23 | - | - |
| rename_domain | lean | 2/2 | 0.043 | 3.5 | 45 | passed+applied (1); passed+applied (1); passed+applied (1) | - |
| settings_refactor | alone | 2/2 | 0.112 | 20.5 | 26 | - | - |
| settings_refactor | lean | 0/2 | 0.043 | 3.5 | 70 | escalate (1); passed+applied (1); passed+applied (1); escalate (4) | 2 |

Accounting: cost = Claude Code's own `total_cost_usd` for the whole session (cache reads included, so any takeover after an escalation is counted) plus the reviewers gruntly called outside it. Marginal = cost minus the $0.045 every fresh `claude -p` session pays before doing anything (it is the same in every arm, so it hides the differences). Cost of a pass = mean cost / pass rate. Takeover edits = the parent's own Edit/Write calls after its first gruntly call. Local child tokens are free of paid cost but cost wall time. False pass = gruntly reported `passed` but the hidden tests failed. Transcripts are in `bench/runs/`.
