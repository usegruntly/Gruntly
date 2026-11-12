# gruntly benchmark (v2)

Local child: `claude` / `haiku` at 32k context. Parent: Claude Code (sonnet). Run 2026-11-13. Pass = hidden tests (never shown to the parent or the child) pass afterwards. S = ten small tasks the parent solves in ~4 turns; L = three larger tasks (six bugs, a 15-file rename, a CLI feature); R = real fix commits of public repositories (hidden tests = the fix's own). Arms: `alone`; `forced` (told to delegate through the one-call flow); `policy` (may delegate if the skill's triage rule says so).

## Totals by bucket (means over tasks and repetitions)

| bucket | arm | runs | pass rate | cost $/run | reviewer $ | vs alone | marginal $ (after the $0.045 floor) | vs alone, marginal | cost of a pass $ | turns | takeover edits | session splits | wall s | parent output tok | tool-output KB in context | delegated | child tok |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| R | lean_esc | 8 | 25% | 0.094 | 0.0000 | - | 0.049 | - | 0.375 | 5.2 | 0.1 | 0.0 | 126 | 2646 | 7.5 | 8/8 | 2474292 |

## Escalation A/B (`lean_esc`: a stuck task goes to a full session with the normal system prompt and tools)

Measured inside every run: the hidden tests run after the lean phase (what `lean` alone would have delivered) and again after the escalation, so each run carries both outcomes and both costs. Needless = the run was already passing when it escalated.

| runs | escalated | rescued (fail to pass) | needless | still failed | pass before | pass after | lean phase $ | escalation $ | escalation $ per rescued pass | $ per correct task before | $ per correct task after |
|---|---|---|---|---|---|---|---|---|---|---|---|
| 8 | 1 | 1 | 0 | 0 | 1/8 | 2/8 | $0.577 | $0.174 | $0.174 | $0.577 | $0.375 |

Escalations: click_helpformatter_write_usage_producing_spurious #1 (The local child failed twice on the same `test_weakening` gate, and gruntly recommends escalation. The first run only changed `CHANGES.rst`. The second run touc): rescued, +$0.174, 9 turns

## Share of runs that passed within a cost cap (parent + reviewers per run; a run over the cap counts as not solved)

| arm | runs | <= $0.05 | <= $0.10 | <= $0.20 | <= $0.50 | <= $1.00 |
|---|---|---|---|---|---|---|
| lean_esc | 8 | 0% | 12% | 12% | 25% | 25% |

## Per task (mean over repetitions)

| task | arm | pass | cost $ | turns | wall s | gruntly (status, attempts) | false pass |
|---|---|---|---|---|---|---|---|
| click_deprecated_label_formatting | lean_esc | 1/1 | 0.087 | 4.0 | 174 | passed+applied (1); passed+applied (1); passed+applied (1) | - |
| click_helpformatter_write_usage_producing_spurious | lean_esc | 1/1 | 0.219 | 12.0 | 108 | escalate (2); passed+applied (1) | - |
| click_metavar_for_choice_options_when | lean_esc | 0/1 | 0.118 | 6.0 | 137 | escalate (4) | - |
| click_short_help_abbreviation | lean_esc | 0/1 | 0.102 | 7.0 | 212 | passed+applied (3); escalate (2); passed+applied (1) | 1 |
| click_show_custom_error_message_in | lean_esc | 0/1 | 0.065 | 3.0 | 134 | passed+applied (1); passed+applied (1) | 1 |
| click_show_envvar_output_for_a | lean_esc | 0/1 | 0.037 | 3.0 | 73 | escalate (2) | - |
| click_use_non_shadowed_help_option | lean_esc | 0/1 | 0.045 | 3.0 | 65 | passed+applied (2); passed+applied (1) | 1 |
| click_validate_style_color_arguments_explicit | lean_esc | 0/1 | 0.077 | 4.0 | 104 | passed+applied (1); passed+applied (1) | 1 |

Accounting: cost = Claude Code's own `total_cost_usd` for the whole session (cache reads included, so any takeover after an escalation is counted) plus the reviewers gruntly called outside it. Marginal = cost minus the $0.045 every fresh `claude -p` session pays before doing anything (it is the same in every arm, so it hides the differences). Cost of a pass = mean cost / pass rate. Takeover edits = the parent's own Edit/Write calls after its first gruntly call. Local child tokens are free of paid cost but cost wall time. False pass = gruntly reported `passed` but the hidden tests failed. Transcripts are in `bench/runs/`.
