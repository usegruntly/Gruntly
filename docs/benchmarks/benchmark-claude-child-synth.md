# gruntly benchmark (v2)

Local child: `claude` / `haiku` at 32k context. Parent: Claude Code (sonnet). Run 2026-11-12. Pass = hidden tests (never shown to the parent or the child) pass afterwards. S = ten small tasks the parent solves in ~4 turns; L = three larger tasks (six bugs, a 15-file rename, a CLI feature); R = real fix commits of public repositories (hidden tests = the fix's own). Arms: `alone`; `forced` (told to delegate through the one-call flow); `policy` (may delegate if the skill's triage rule says so).

## Totals by bucket (means over tasks and repetitions)

| bucket | arm | runs | pass rate | cost $/run | reviewer $ | vs alone | marginal $ (after the $0.045 floor) | vs alone, marginal | cost of a pass $ | turns | takeover edits | session splits | wall s | parent output tok | tool-output KB in context | delegated | child tok |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| S | forced | 5 | 100% | 0.070 | 0.0000 | - | 0.025 | - | 0.070 | 2.0 | 0.0 | 0.0 | 25 | 444 | 1.8 | 5/5 | 307582 |
| L | forced | 3 | 100% | 0.084 | 0.0000 | - | 0.039 | - | 0.084 | 3.7 | 0.3 | 0.0 | 62 | 1054 | 6.0 | 3/3 | 489556 |

## Share of runs that passed within a cost cap (parent + reviewers per run; a run over the cap counts as not solved)

| arm | runs | <= $0.05 | <= $0.10 | <= $0.20 | <= $0.50 | <= $1.00 |
|---|---|---|---|---|---|---|
| forced | 8 | 0% | 75% | 100% | 100% | 100% |

## Per task (mean over repetitions)

| task | arm | pass | cost $ | turns | wall s | gruntly (status, attempts) | false pass |
|---|---|---|---|---|---|---|---|
| bugs_batch | forced | 1/1 | 0.108 | 5.0 | 113 | passed+applied (1); passed+applied (1); passed+applied (1); passed+applied (1); passed+applied (1); passed+applied (1) | - |
| cli_json | forced | 1/1 | 0.065 | 3.0 | 32 | passed+applied (1) | - |
| paginate | forced | 1/1 | 0.058 | 2.0 | 23 | passed+applied (1) | - |
| rename_domain | forced | 1/1 | 0.079 | 3.0 | 42 | passed+applied (1) | - |
| retry | forced | 1/1 | 0.060 | 2.0 | 25 | passed+applied (1) | - |
| roman | forced | 1/1 | 0.061 | 2.0 | 30 | passed+applied (1) | - |
| slugify | forced | 1/1 | 0.114 | 2.0 | 22 | passed+applied (1) | - |
| word_count | forced | 1/1 | 0.058 | 2.0 | 23 | passed+applied (1) | - |

Accounting: cost = Claude Code's own `total_cost_usd` for the whole session (cache reads included, so any takeover after an escalation is counted) plus the reviewers gruntly called outside it. Marginal = cost minus the $0.045 every fresh `claude -p` session pays before doing anything (it is the same in every arm, so it hides the differences). Cost of a pass = mean cost / pass rate. Takeover edits = the parent's own Edit/Write calls after its first gruntly call. Local child tokens are free of paid cost but cost wall time. False pass = gruntly reported `passed` but the hidden tests failed. Transcripts are in `bench/runs/`.
