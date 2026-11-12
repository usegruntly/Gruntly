# gruntly benchmark (v2)

Local child: `claude` / `haiku` at 32k context. Parent: Claude Code (haiku). Run 2026-11-12. Pass = hidden tests (never shown to the parent or the child) pass afterwards. S = ten small tasks the parent solves in ~4 turns; L = three larger tasks (six bugs, a 15-file rename, a CLI feature); R = real fix commits of public repositories (hidden tests = the fix's own). Arms: `alone`; `forced` (told to delegate through the one-call flow); `policy` (may delegate if the skill's triage rule says so).

## Totals by bucket (means over tasks and repetitions)

| bucket | arm | runs | pass rate | cost $/run | reviewer $ | vs alone | marginal $ (after the $0.045 floor) | vs alone, marginal | cost of a pass $ | turns | takeover edits | session splits | wall s | parent output tok | tool-output KB in context | delegated | child tok |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| R | alone | 8 | 38% | 0.007 | 0.0000 | - | -0.037 | - | 0.020 | 9.2 | 0.0 | 0.0 | 29 | 3191 | 7.6 | 0/8 | - |

## Share of runs that passed within a cost cap (parent + reviewers per run; a run over the cap counts as not solved)

| arm | runs | <= $0.05 | <= $0.10 | <= $0.20 | <= $0.50 | <= $1.00 |
|---|---|---|---|---|---|---|
| alone | 8 | 38% | 38% | 38% | 38% | 38% |

## Per task (mean over repetitions)

| task | arm | pass | cost $ | turns | wall s | gruntly (status, attempts) | false pass |
|---|---|---|---|---|---|---|---|
| click_deprecated_label_formatting | alone | 1/1 | 0.009 | 11.0 | 27 | - | - |
| click_helpformatter_write_usage_producing_spurious | alone | 1/1 | 0.005 | 6.0 | 19 | - | - |
| click_metavar_for_choice_options_when | alone | 0/1 | 0.009 | 12.0 | 36 | - | - |
| click_short_help_abbreviation | alone | 1/1 | 0.006 | 8.0 | 25 | - | - |
| click_show_custom_error_message_in | alone | 0/1 | 0.008 | 9.0 | 33 | - | - |
| click_show_envvar_output_for_a | alone | 0/1 | 0.006 | 8.0 | 24 | - | - |
| click_use_non_shadowed_help_option | alone | 0/1 | 0.007 | 11.0 | 26 | - | - |
| click_validate_style_color_arguments_explicit | alone | 0/1 | 0.009 | 9.0 | 39 | - | - |

Accounting: cost = Claude Code's own `total_cost_usd` for the whole session (cache reads included, so any takeover after an escalation is counted) plus the reviewers gruntly called outside it. Marginal = cost minus the $0.045 every fresh `claude -p` session pays before doing anything (it is the same in every arm, so it hides the differences). Cost of a pass = mean cost / pass rate. Takeover edits = the parent's own Edit/Write calls after its first gruntly call. Local child tokens are free of paid cost but cost wall time. False pass = gruntly reported `passed` but the hidden tests failed. Transcripts are in `bench/runs/`.
