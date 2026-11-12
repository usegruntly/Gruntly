# gruntly benchmark (v2)

Local child: `claude` / `haiku` at 32k context. Parent: Claude Code (sonnet). Run 2026-11-13. Pass = hidden tests (never shown to the parent or the child) pass afterwards. S = ten small tasks the parent solves in ~4 turns; L = three larger tasks (six bugs, a 15-file rename, a CLI feature); R = real fix commits of public repositories (hidden tests = the fix's own). Arms: `alone`; `forced` (told to delegate through the one-call flow); `policy` (may delegate if the skill's triage rule says so).

## Totals by bucket (means over tasks and repetitions)

| bucket | arm | runs | pass rate | cost $/run | reviewer $ | vs alone | marginal $ (after the $0.045 floor) | vs alone, marginal | cost of a pass $ | turns | takeover edits | session splits | wall s | parent output tok | tool-output KB in context | delegated | child tok |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| R | alone | 8 | 50% | 0.134 | 0.0000 | - | 0.089 | - | 0.268 | 11.6 | 0.0 | 0.0 | 35 | 3491 | 11.3 | 0/8 | - |
| R | lean | 8 | 12% | 0.064 | 0.0000 | -52% | 0.019 | -78% | 0.514 | 3.6 | 0.0 | 0.0 | 106 | 1834 | 3.8 | 8/8 | 2063815 |

## Share of runs that passed within a cost cap (parent + reviewers per run; a run over the cap counts as not solved)

| arm | runs | <= $0.05 | <= $0.10 | <= $0.20 | <= $0.50 | <= $1.00 |
|---|---|---|---|---|---|---|
| alone | 8 | 0% | 12% | 50% | 50% | 50% |
| lean | 8 | 0% | 12% | 12% | 12% | 12% |

## Per task (mean over repetitions)

| task | arm | pass | cost $ | turns | wall s | gruntly (status, attempts) | false pass |
|---|---|---|---|---|---|---|---|
| click_deprecated_label_formatting | alone | 1/1 | 0.105 | 11.0 | 23 | - | - |
| click_deprecated_label_formatting | lean | 1/1 | 0.079 | 4.0 | 111 | passed+applied (1); passed+applied (1) | - |
| click_helpformatter_write_usage_producing_spurious | alone | 1/1 | 0.089 | 6.0 | 18 | - | - |
| click_helpformatter_write_usage_producing_spurious | lean | 0/1 | 0.043 | 4.0 | 57 | escalate (2); passed+applied (1) | 1 |
| click_metavar_for_choice_options_when | alone | 0/1 | 0.120 | 12.0 | 32 | - | - |
| click_metavar_for_choice_options_when | lean | 0/1 | 0.084 | 4.0 | 128 | escalate (4) | - |
| click_short_help_abbreviation | alone | 1/1 | 0.117 | 7.0 | 40 | - | - |
| click_short_help_abbreviation | lean | 0/1 | 0.028 | 3.0 | 61 | escalate (2) | - |
| click_show_custom_error_message_in | alone | 0/1 | 0.266 | 29.0 | 76 | - | - |
| click_show_custom_error_message_in | lean | 0/1 | 0.105 | 5.0 | 179 | passed+applied (2); passed+applied (1); escalate (2) | 1 |
| click_show_envvar_output_for_a | alone | 1/1 | 0.116 | 9.0 | 28 | - | - |
| click_show_envvar_output_for_a | lean | 0/1 | 0.052 | 3.0 | 67 | passed+applied (1) | 1 |
| click_use_non_shadowed_help_option | alone | 0/1 | 0.141 | 10.0 | 37 | - | - |
| click_use_non_shadowed_help_option | lean | 0/1 | 0.067 | 3.0 | 152 | escalate (4) | - |
| click_validate_style_color_arguments_explicit | alone | 0/1 | 0.117 | 9.0 | 25 | - | - |
| click_validate_style_color_arguments_explicit | lean | 0/1 | 0.057 | 3.0 | 95 | escalate (1); passed+applied (1) | 1 |

Accounting: cost = Claude Code's own `total_cost_usd` for the whole session (cache reads included, so any takeover after an escalation is counted) plus the reviewers gruntly called outside it. Marginal = cost minus the $0.045 every fresh `claude -p` session pays before doing anything (it is the same in every arm, so it hides the differences). Cost of a pass = mean cost / pass rate. Takeover edits = the parent's own Edit/Write calls after its first gruntly call. Local child tokens are free of paid cost but cost wall time. False pass = gruntly reported `passed` but the hidden tests failed. Transcripts are in `bench/runs/`.
