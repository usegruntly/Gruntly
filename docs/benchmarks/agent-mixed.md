# gruntly benchmark (v2)

Local child: `claude` / `haiku` at 32k context. Parent: Claude Code (sonnet). Run 2026-11-12. Pass = hidden tests (never shown to the parent or the child) pass afterwards. S = ten small tasks the parent solves in ~4 turns; L = three larger tasks (six bugs, a 15-file rename, a CLI feature); R = real fix commits of public repositories (hidden tests = the fix's own). Arms: `alone`; `forced` (told to delegate through the one-call flow); `policy` (may delegate if the skill's triage rule says so).

## Totals by bucket (means over tasks and repetitions)

| bucket | arm | runs | pass rate | cost $/run | reviewer $ | vs alone | marginal $ (after the $0.045 floor) | vs alone, marginal | cost of a pass $ | turns | takeover edits | session splits | wall s | parent output tok | tool-output KB in context | delegated | child tok |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| S | alone | 2 | 100% | 0.250 | 0.0000 | - | 0.205 | - | 0.250 | 14.5 | 0.0 | 0.0 | 100 | 10362 | 12.0 | 0/2 | - |
| S | forced | 2 | 100% | 0.097 | 0.0000 | -61% | 0.052 | -75% | 0.097 | 5.5 | 1.0 | 0.0 | 56 | 1952 | 5.5 | 2/2 | 111260 |

## Share of runs that passed within a cost cap (parent + reviewers per run; a run over the cap counts as not solved)

| arm | runs | <= $0.05 | <= $0.10 | <= $0.20 | <= $0.50 | <= $1.00 |
|---|---|---|---|---|---|---|
| alone | 2 | 0% | 0% | 50% | 100% | 100% |
| forced | 2 | 0% | 50% | 100% | 100% | 100% |

## Per task (mean over repetitions)

| task | arm | pass | cost $ | turns | wall s | gruntly (status, attempts) | false pass |
|---|---|---|---|---|---|---|---|
| content_range_rfc | alone | 1/1 | 0.152 | 11.0 | 60 | - | - |
| content_range_rfc | forced | 1/1 | 0.110 | 8.0 | 66 | passed+applied (1) | - |
| retry_after_rfc | alone | 1/1 | 0.347 | 18.0 | 139 | - | - |
| retry_after_rfc | forced | 1/1 | 0.084 | 3.0 | 45 | passed+applied (1) | - |

Accounting: cost = Claude Code's own `total_cost_usd` for the whole session (cache reads included, so any takeover after an escalation is counted) plus the reviewers gruntly called outside it. Marginal = cost minus the $0.045 every fresh `claude -p` session pays before doing anything (it is the same in every arm, so it hides the differences). Cost of a pass = mean cost / pass rate. Takeover edits = the parent's own Edit/Write calls after its first gruntly call. Local child tokens are free of paid cost but cost wall time. False pass = gruntly reported `passed` but the hidden tests failed. Transcripts are in `bench/runs/`.
