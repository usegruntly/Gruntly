# gruntly benchmark (v2)

Local child: `opencode` / `qwen/qwen3.5-9b` at 32k context. Parent: Claude Code (sonnet). Run 2026-11-12. Pass = hidden tests (never shown to the parent or the child) pass afterwards. S = ten small tasks the parent solves in ~4 turns; L = three larger tasks (six bugs, a 15-file rename, a CLI feature); R = real fix commits of public repositories (hidden tests = the fix's own). Arms: `alone`; `forced` (told to delegate through the one-call flow); `policy` (may delegate if the skill's triage rule says so).

## Totals by bucket (means over tasks and repetitions)

| bucket | arm | runs | pass rate | cost $/run | reviewer $ | vs alone | marginal $ (after the $0.045 floor) | vs alone, marginal | cost of a pass $ | turns | takeover edits | session splits | wall s | parent output tok | tool-output KB in context | delegated | child tok |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| R | alone | 8 | 50% | 0.122 | 0.0000 | - | 0.077 | - | 0.243 | 10.9 | 0.0 | 0.0 | 32 | 2708 | 11.3 | 0/8 | - |

## Share of runs that passed within a cost cap (parent + reviewers per run; a run over the cap counts as not solved)

| arm | runs | <= $0.05 | <= $0.10 | <= $0.20 | <= $0.50 | <= $1.00 |
|---|---|---|---|---|---|---|
| alone | 8 | 0% | 25% | 50% | 50% | 50% |

## Per task (mean over repetitions)

| task | arm | pass | cost $ | turns | wall s | gruntly (status, attempts) | false pass |
|---|---|---|---|---|---|---|---|
| click_deprecated_label_formatting | alone | 1/1 | 0.117 | 13.0 | 29 | - | - |
| click_helpformatter_write_usage_producing_spurious | alone | 1/1 | 0.096 | 7.0 | 23 | - | - |
| click_metavar_for_choice_options_when | alone | 0/1 | 0.134 | 14.0 | 36 | - | - |
| click_short_help_abbreviation | alone | 1/1 | 0.084 | 6.0 | 20 | - | - |
| click_show_custom_error_message_in | alone | 0/1 | 0.170 | 15.0 | 40 | - | - |
| click_show_envvar_output_for_a | alone | 1/1 | 0.122 | 10.0 | 32 | - | - |
| click_use_non_shadowed_help_option | alone | 0/1 | 0.107 | 10.0 | 35 | - | - |
| click_validate_style_color_arguments_explicit | alone | 0/1 | 0.142 | 12.0 | 42 | - | - |

Accounting: cost = Claude Code's own `total_cost_usd` for the whole session (cache reads included, so any takeover after an escalation is counted) plus the reviewers gruntly called outside it. Marginal = cost minus the $0.045 every fresh `claude -p` session pays before doing anything (it is the same in every arm, so it hides the differences). Cost of a pass = mean cost / pass rate. Takeover edits = the parent's own Edit/Write calls after its first gruntly call. Local child tokens are free of paid cost but cost wall time. False pass = gruntly reported `passed` but the hidden tests failed. Transcripts are in `bench/runs/`.
