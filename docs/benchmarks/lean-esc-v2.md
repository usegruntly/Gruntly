# gruntly benchmark (v2)

Local child: `claude` / `haiku` at 32k context. Parent: Claude Code (sonnet). Run 2026-11-13. Pass = hidden tests (never shown to the parent or the child) pass afterwards. S = ten small tasks the parent solves in ~4 turns; L = three larger tasks (six bugs, a 15-file rename, a CLI feature); R = real fix commits of public repositories (hidden tests = the fix's own). Arms: `alone`; `forced` (told to delegate through the one-call flow); `policy` (may delegate if the skill's triage rule says so).

## Totals by bucket (means over tasks and repetitions)

| bucket | arm | runs | pass rate | cost $/run | reviewer $ | vs alone | marginal $ (after the $0.045 floor) | vs alone, marginal | cost of a pass $ | turns | takeover edits | session splits | wall s | parent output tok | tool-output KB in context | delegated | child tok |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| L | lean_esc | 10 | 100% | 0.061 | 0.0000 | - | 0.016 | - | 0.061 | 3.7 | 0.0 | 0.0 | 67 | 1621 | 7.4 | 10/10 | 2045869 |

## Escalation A/B (`lean_esc`: a stuck task goes to a full session with the normal system prompt and tools)

Measured inside every run: the hidden tests run after the lean phase (what `lean` alone would have delivered) and again after the escalation, so each run carries both outcomes and both costs. Needless = the run was already passing when it escalated.

| runs | escalated | rescued (fail to pass) | needless | still failed | pass before | pass after | lean phase $ | escalation $ | escalation $ per rescued pass | $ per correct task before | $ per correct task after |
|---|---|---|---|---|---|---|---|---|---|---|---|
| 10 | 2 | 0 | 2 | 0 | 10/10 | 10/10 | $0.442 | $0.170 | n/a | $0.044 | $0.061 |

Escalations: rename_domain #1 (gruntly recommends escalation after the second round, because the request names `customer_label` and the diff never adds it. That flag looks spurious, since `cu): not rescued, +$0.085, 5 turns; rename_domain #2 (the local child's rename passed the suite and I fixed `check_names.py` with a second run, but gruntly marked the work incomplete after 2 rounds and recommended ): not rescued, +$0.085, 5 turns

## Share of runs that passed within a cost cap (parent + reviewers per run; a run over the cap counts as not solved)

| arm | runs | <= $0.05 | <= $0.10 | <= $0.20 | <= $0.50 | <= $1.00 |
|---|---|---|---|---|---|---|
| lean_esc | 10 | 60% | 80% | 100% | 100% | 100% |

## Per task (mean over repetitions)

| task | arm | pass | cost $ | turns | wall s | gruntly (status, attempts) | false pass |
|---|---|---|---|---|---|---|---|
| bugs_batch | lean_esc | 2/2 | 0.043 | 2.0 | 94 | passed+applied (1); passed+applied (1); passed+applied (1); passed+applied (1); passed+applied (1); passed+applied (1); passed+applied (1); passed+applied (1); passed+applied (1); passed+applied (1); passed+applied (1); passed+applied (1) | - |
| cli_json | lean_esc | 2/2 | 0.029 | 3.5 | 36 | passed+applied (1); escalate (1); passed+applied (1) | - |
| inventory_reorder | lean_esc | 2/2 | 0.076 | 3.0 | 102 | passed+applied (2); passed+applied (2); passed+applied (2); passed+applied (2) | - |
| rename_domain | lean_esc | 2/2 | 0.131 | 8.0 | 71 | passed+applied (1); passed+applied (1); passed+applied (1); passed+applied (1) | - |
| settings_refactor | lean_esc | 2/2 | 0.027 | 2.0 | 33 | passed+applied (1); passed+applied (1) | - |

Accounting: cost = Claude Code's own `total_cost_usd` for the whole session (cache reads included, so any takeover after an escalation is counted) plus the reviewers gruntly called outside it. Marginal = cost minus the $0.045 every fresh `claude -p` session pays before doing anything (it is the same in every arm, so it hides the differences). Cost of a pass = mean cost / pass rate. Takeover edits = the parent's own Edit/Write calls after its first gruntly call. Local child tokens are free of paid cost but cost wall time. False pass = gruntly reported `passed` but the hidden tests failed. Transcripts are in `bench/runs/`.
