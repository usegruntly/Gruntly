# gruntly benchmark (v2)

Local child: `claude` / `haiku` at 32k context. Parent: Claude Code (sonnet). Run 2026-11-13. Pass = hidden tests (never shown to the parent or the child) pass afterwards. S = ten small tasks the parent solves in ~4 turns; L = three larger tasks (six bugs, a 15-file rename, a CLI feature); R = real fix commits of public repositories (hidden tests = the fix's own). Arms: `alone`; `forced` (told to delegate through the one-call flow); `policy` (may delegate if the skill's triage rule says so).

## Totals by bucket (means over tasks and repetitions)

| bucket | arm | runs | pass rate | cost $/run | reviewer $ | vs alone | marginal $ (after the $0.045 floor) | vs alone, marginal | cost of a pass $ | turns | takeover edits | session splits | wall s | parent output tok | tool-output KB in context | delegated | child tok |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| L | lean_esc | 2 | 100% | 0.046 | 0.0000 | - | 0.001 | - | 0.046 | 2.5 | 0.0 | 0.0 | 46 | 1410 | 6.5 | 2/2 | 359573 |

## Escalation A/B (`lean_esc`: a stuck task goes to a full session with the normal system prompt and tools)

Measured inside every run: the hidden tests run after the lean phase (what `lean` alone would have delivered) and again after the escalation, so each run carries both outcomes and both costs. Needless = the run was already passing when it escalated.

| runs | escalated | rescued (fail to pass) | needless | still failed | pass before | pass after | lean phase $ | escalation $ | escalation $ per rescued pass | $ per correct task before | $ per correct task after |
|---|---|---|---|---|---|---|---|---|---|---|---|
| 2 | 0 | 0 | 0 | 0 | 2/2 | 2/2 | $0.092 | $0.000 | n/a | $0.046 | $0.046 |

## Share of runs that passed within a cost cap (parent + reviewers per run; a run over the cap counts as not solved)

| arm | runs | <= $0.05 | <= $0.10 | <= $0.20 | <= $0.50 | <= $1.00 |
|---|---|---|---|---|---|---|
| lean_esc | 2 | 100% | 100% | 100% | 100% | 100% |

## Per task (mean over repetitions)

| task | arm | pass | cost $ | turns | wall s | gruntly (status, attempts) | false pass |
|---|---|---|---|---|---|---|---|
| rename_domain | lean_esc | 2/2 | 0.046 | 2.5 | 46 | passed+applied (1); passed+applied (1); passed+applied (1) | - |

Accounting: cost = Claude Code's own `total_cost_usd` for the whole session (cache reads included, so any takeover after an escalation is counted) plus the reviewers gruntly called outside it. Marginal = cost minus the $0.045 every fresh `claude -p` session pays before doing anything (it is the same in every arm, so it hides the differences). Cost of a pass = mean cost / pass rate. Takeover edits = the parent's own Edit/Write calls after its first gruntly call. Local child tokens are free of paid cost but cost wall time. False pass = gruntly reported `passed` but the hidden tests failed. Transcripts are in `bench/runs/`.
