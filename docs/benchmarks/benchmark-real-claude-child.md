# gruntly benchmark (v2)

Local child: `claude` / `haiku` at 32k context. Parent: Claude Code (sonnet). Run 2026-11-12. Pass = hidden tests (never shown to the parent or the child) pass afterwards. S = ten small tasks the parent solves in ~4 turns; L = three larger tasks (six bugs, a 15-file rename, a CLI feature); R = real fix commits of public repositories (hidden tests = the fix's own). Arms: `alone`; `forced` (told to delegate through the one-call flow); `policy` (may delegate if the skill's triage rule says so).

## Totals by bucket (means over tasks and repetitions)

| bucket | arm | runs | pass rate | cost $/run | reviewer $ | vs alone | marginal $ (after the $0.045 floor) | vs alone, marginal | cost of a pass $ | turns | takeover edits | session splits | wall s | parent output tok | tool-output KB in context | delegated | child tok |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| R | forced | 8 | 38% | 0.109 | 0.0000 | - | 0.064 | - | 0.290 | 4.6 | 0.5 | 0.0 | 90 | 2210 | 5.0 | 8/8 | 1792946 |

## Share of runs that passed within a cost cap (parent + reviewers per run; a run over the cap counts as not solved)

| arm | runs | <= $0.05 | <= $0.10 | <= $0.20 | <= $0.50 | <= $1.00 |
|---|---|---|---|---|---|---|
| forced | 8 | 0% | 38% | 38% | 38% | 38% |

## Per task (mean over repetitions)

| task | arm | pass | cost $ | turns | wall s | gruntly (status, attempts) | false pass |
|---|---|---|---|---|---|---|---|
| click_deprecated_label_formatting | forced | 1/1 | 0.071 | 2.0 | 53 | passed+applied (1) | - |
| click_helpformatter_write_usage_producing_spurious | forced | 1/1 | 0.069 | 2.0 | 41 | passed+applied (1) | - |
| click_metavar_for_choice_options_when | forced | 0/1 | 0.222 | 12.0 | 195 | escalate (2); escalate (2) | - |
| click_short_help_abbreviation | forced | 0/1 | 0.124 | 4.0 | 90 | passed+applied (1) | 1 |
| click_show_custom_error_message_in | forced | 0/1 | 0.071 | 2.0 | 45 | passed+applied (1) | 1 |
| click_show_envvar_output_for_a | forced | 1/1 | 0.073 | 2.0 | 61 | passed+applied (1) | - |
| click_use_non_shadowed_help_option | forced | 0/1 | 0.168 | 11.0 | 184 | escalate (2); escalate (2) | - |
| click_validate_style_color_arguments_explicit | forced | 0/1 | 0.073 | 2.0 | 50 | passed+applied (1) | 1 |

Accounting: cost = Claude Code's own `total_cost_usd` for the whole session (cache reads included, so any takeover after an escalation is counted) plus the reviewers gruntly called outside it. Marginal = cost minus the $0.045 every fresh `claude -p` session pays before doing anything (it is the same in every arm, so it hides the differences). Cost of a pass = mean cost / pass rate. Takeover edits = the parent's own Edit/Write calls after its first gruntly call. Local child tokens are free of paid cost but cost wall time. False pass = gruntly reported `passed` but the hidden tests failed. Transcripts are in `bench/runs/`.
