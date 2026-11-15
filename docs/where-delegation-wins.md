# Where delegation wins, and where it does not

*Generated 2026-11-12 by `bench/gold_doc.py` from stored benchmark rows. That script is no longer in the tree (it is at commit `91a53ae`), so this is now a fixed record of those runs.*

The question: for each kind of agent work, does a dearer parent (Claude Sonnet) handing the work to a cheaper child (Claude Haiku, through gruntly) reach the parent's result for less money? Costs are API-equivalent dollars as Claude Code reports them: the parent's session plus the child's own dollars. The child is never counted as free. Claude Code versions in these runs: 2.1.322 (Claude Code).

## How to read the evidence

- **Measured** numbers are from runs in fresh benchmark sessions, one run per task and arm unless a row says otherwise. With a handful of tasks the intervals are wide.
- **Modelled** numbers (marked) extend measured turns and child cost to a long session with the per-turn costs measured in real sessions. They are not runs.
- **Pilot** means fewer than 4 tasks: the verdict is UNSURE by rule, whatever the numbers look like.
- A workload where the reference or the cheap model does as well for less is reported with the same prominence as one where delegation wins.

**Verdict rule (fixed before any verdict was computed).** For a workload with n tasks (the tasks the delegated arm ran):
quality is *non-inferior* when the delegated pass rate is at least the reference's minus 1/n (it may lose at most one task);
*fresh-session saving* is the paired per-task cost difference of delegated against the reference with the one-off cold-cache cost removed;
*long-session saving* is modelled from the measured turns and child cost with the per-turn costs of a 150k to 300k context
(`bench/cost_model.py`), per correct task.
- **DELEGATE**: n is at least 4, quality is non-inferior, the fresh saving is at least 15% and its 95% interval is below zero.
- **DELEGATE IN LONG SESSIONS**: n is at least 4, quality is non-inferior, the fresh difference is within plus or minus 15%, and the modelled long-session saving is at least 25%.
- **AVOID**: delegated loses more than one task against the reference, or costs 15% or more *more* in fresh sessions with no modelled long-session saving of 25%.
- **UNSURE**: everything else, always including n below 4. UNSURE means: do not delegate by default, and run more tasks.

## Verdict matrix

| workload | tasks | pass: parent alone | pass: delegated | pass: child alone | $ per run: parent alone | $ per run: delegated | $ per run: child alone | fresh-session change | modelled long-session change, per correct task | verdict |
|---|---|---|---|---|---|---|---|---|---|---|
| Small code edits | 5 | 100% | 100% | 100% | $0.062 | $0.059 | $0.004 | -4% (-7% to -2%) | -59% | **DELEGATE IN LONG SESSIONS (modelled, not measured)** |
| Larger code edits | 3 | 100% | 100% | 67% | $0.070 | $0.084 | $0.007 | +20% (-1% to +40%) | +5% | **UNSURE (n < 4)** |
| Real bug fixes in a public library | 8 | 50% | 38% | 38% | $0.122 | $0.109 | $0.007 | -10% (-45% to +25%) | -34% | **DELEGATE IN LONG SESSIONS (modelled, not measured)** |
| Reading code and answering | 2 | 100% | 100% | 100% | $0.082 | $0.081 | $0.004 | -1% | -23% | **UNSURE (n < 4)** |
| Exact fetch from a page | 2 | 100% | 100% | 100% | $0.075 | $0.072 | $0.004 | -4% | +2% | **UNSURE (n < 4)** |
| Web research with sources | 2 | 100% | 50% | 100% | $0.119 | $0.091 | $0.025 | -23% | -16% | **UNSURE (n < 4)** |
| Summarising long inputs | 2 | 100% | 100% | 100% | $0.086 | $0.080 | $0.007 | -7% | -32% | **UNSURE (n < 4)** |
| Data wrangling by script | 2 | 100% | 100% | 100% | $0.067 | $0.071 | $0.004 | +6% | -45% | **UNSURE (n < 4)** |
| Mixed: read the RFC, then code | 2 | 100% | 100% | 100% | $0.250 | $0.097 | $0.008 | -61% | -56% | **UNSURE (n < 4)** |
| Control: answerable from memory | 1 | 100% | 100% | 100% | $0.055 | $0.074 | $0.003 | +35% | +21% | **UNSURE (n < 4)** |

Pass rates are shares of runs whose answer or patch met the task's grader (hidden tests, or the deterministic graders in `bench/graders.py`). "Fresh-session change" is delegated against the parent alone, paired by task, with the one-off cold-cache cost removed.

## What delegation does to the parent's context

The mechanism the saving relies on: whatever the child reads stays out of the parent's context, which the parent pays to re-read on every turn.

| workload | parent tool output kept in its context, alone | delegated | parent turns, alone | delegated | wall seconds, alone | delegated |
|---|---|---|---|---|---|---|
| Small code edits | 0.8 KB | 1.8 KB | 5 | 2 | 14 | 25 |
| Larger code edits | 2.4 KB | 6.0 KB | 4 | 4 | 17 | 62 |
| Real bug fixes in a public library | 11.3 KB | 5.0 KB | 11 | 5 | 32 | 90 |
| Reading code and answering | 8.1 KB | 5.9 KB | 4 | 3 | 15 | 30 |
| Exact fetch from a page | 10.3 KB | 3.0 KB | 4 | 4 | 13 | 30 |
| Web research with sources | 12.7 KB | 2.2 KB | 6 | 2 | 36 | 57 |
| Summarising long inputs | 5.6 KB | 3.3 KB | 6 | 4 | 18 | 29 |
| Data wrangling by script | 0.9 KB | 0.9 KB | 4 | 2 | 16 | 28 |
| Mixed: read the RFC, then code | 12.0 KB | 5.5 KB | 14 | 6 | 100 | 56 |
| Control: answerable from memory | 1.8 KB | 0.7 KB | 2 | 2 | 10 | 46 |

## What the parent said it expected, and what happened

In the delegated arm the parent wrote `CONFIDENCE: NN%` before handing the work over. It is recorded, never used to decide anything.

| stated chance | runs | passed | pass rate |
|---|---|---|---|
| below 50% | 1 | 0 | 0% |
| 50% to 79% | 7 | 7 | 100% |
| 80% or more | 3 | 3 | 100% |

Brier score 0.113 over 11 runs (always saying the overall pass rate of 91% would score 0.083; lower is better; a score no better than that means the stated chance carries no information).

## By workload

### Small code edits

*One file, a failing test, a clear request.* Tasks: `paginate`, `retry`, `roman`, `slugify`, `word_count`. Verdict: **DELEGATE IN LONG SESSIONS (modelled, not measured)**.

| task | arm | score | pass | total $ | parent $ | child $ | parent turns | wall s | parent said | what went wrong |
|---|---|---|---|---|---|---|---|---|---|---|
| paginate | parent alone | 1.00 | yes | 0.059 | 0.059 | 0.0000 | 4 | 13 | - | - |
| paginate | parent alone | 1.00 | yes | 0.059 | 0.059 | 0.0000 | 4 | 16 | - | - |
| retry | parent alone | 1.00 | yes | 0.062 | 0.062 | 0.0000 | 5 | 13 | - | - |
| retry | parent alone | 1.00 | yes | 0.060 | 0.060 | 0.0000 | 4 | 13 | - | - |
| roman | parent alone | 1.00 | yes | 0.065 | 0.065 | 0.0000 | 5 | 16 | - | - |
| roman | parent alone | 1.00 | yes | 0.068 | 0.068 | 0.0000 | 5 | 15 | - | - |
| slugify | parent alone | 1.00 | yes | 0.061 | 0.061 | 0.0000 | 5 | 14 | - | - |
| word_count | parent alone | 1.00 | yes | 0.061 | 0.061 | 0.0000 | 5 | 15 | - | - |
| paginate | delegated | 1.00 | yes | 0.058 | 0.056 | 0.0024 | 2 | 23 | - | - |
| retry | delegated | 1.00 | yes | 0.060 | 0.058 | 0.0026 | 2 | 25 | - | - |
| roman | delegated | 1.00 | yes | 0.061 | 0.058 | 0.0035 | 2 | 30 | - | - |
| slugify | delegated | 1.00 | yes | 0.114 | 0.111 | 0.0022 | 2 | 22 | - | - |
| word_count | delegated | 1.00 | yes | 0.058 | 0.056 | 0.0024 | 2 | 23 | - | - |
| paginate | child alone | 1.00 | yes | 0.004 | 0.004 | 0.0000 | 5 | 11 | - | - |
| retry | child alone | 1.00 | yes | 0.004 | 0.004 | 0.0000 | 6 | 15 | - | - |
| roman | child alone | 1.00 | yes | 0.004 | 0.004 | 0.0000 | 5 | 16 | - | - |
| slugify | child alone | 1.00 | yes | 0.004 | 0.004 | 0.0000 | 5 | 12 | - | - |
| word_count | child alone | 1.00 | yes | 0.004 | 0.004 | 0.0000 | 5 | 12 | - | - |

### Larger code edits

*Several bugs in several files, a 15-file rename, a CLI feature.* Tasks: `bugs_batch`, `cli_json`, `rename_domain`. Verdict: **UNSURE (n < 4)**.

| task | arm | score | pass | total $ | parent $ | child $ | parent turns | wall s | parent said | what went wrong |
|---|---|---|---|---|---|---|---|---|---|---|
| bugs_batch | parent alone | 1.00 | yes | 0.080 | 0.080 | 0.0000 | 4 | 21 | - | - |
| cli_json | parent alone | 1.00 | yes | 0.066 | 0.066 | 0.0000 | 5 | 16 | - | - |
| rename_domain | parent alone | 1.00 | yes | 0.064 | 0.064 | 0.0000 | 4 | 15 | - | - |
| bugs_batch | delegated | 1.00 | yes | 0.108 | 0.095 | 0.0133 | 5 | 113 | - | - |
| cli_json | delegated | 1.00 | yes | 0.065 | 0.062 | 0.0030 | 3 | 32 | - | - |
| rename_domain | delegated | 1.00 | yes | 0.079 | 0.073 | 0.0051 | 3 | 42 | - | - |
| bugs_batch | child alone | 0.00 | NO | 0.009 | 0.009 | 0.0000 | 7 | 34 | - | failed |
| cli_json | child alone | 1.00 | yes | 0.005 | 0.005 | 0.0000 | 11 | 15 | - | - |
| rename_domain | child alone | 1.00 | yes | 0.007 | 0.007 | 0.0000 | 10 | 24 | - | - |

### Real bug fixes in a public library

*One-line changelog statements; hidden tests ask for specifics. 8 fixes in `click`.* Tasks: `click_deprecated_label_formatting`, `click_helpformatter_write_usage_producing_spurious`, `click_metavar_for_choice_options_when`, `click_short_help_abbreviation`, `click_show_custom_error_message_in`, `click_show_envvar_output_for_a`, `click_use_non_shadowed_help_option`, `click_validate_style_color_arguments_explicit`. Verdict: **DELEGATE IN LONG SESSIONS (modelled, not measured)**.

| task | arm | score | pass | total $ | parent $ | child $ | parent turns | wall s | parent said | what went wrong |
|---|---|---|---|---|---|---|---|---|---|---|
| click_deprecated_label_formatting | parent alone | 1.00 | yes | 0.117 | 0.117 | 0.0000 | 13 | 29 | - | - |
| click_helpformatter_write_usage_producing_spurious | parent alone | 1.00 | yes | 0.096 | 0.096 | 0.0000 | 7 | 23 | - | - |
| click_metavar_for_choice_options_when | parent alone | 0.00 | NO | 0.134 | 0.134 | 0.0000 | 14 | 36 | - | failed |
| click_short_help_abbreviation | parent alone | 1.00 | yes | 0.084 | 0.084 | 0.0000 | 6 | 20 | - | - |
| click_show_custom_error_message_in | parent alone | 0.00 | NO | 0.170 | 0.170 | 0.0000 | 15 | 40 | - | failed |
| click_show_envvar_output_for_a | parent alone | 1.00 | yes | 0.122 | 0.122 | 0.0000 | 10 | 32 | - | - |
| click_use_non_shadowed_help_option | parent alone | 0.00 | NO | 0.107 | 0.107 | 0.0000 | 10 | 35 | - | failed |
| click_validate_style_color_arguments_explicit | parent alone | 0.00 | NO | 0.142 | 0.142 | 0.0000 | 12 | 42 | - | failed |
| click_deprecated_label_formatting | delegated | 1.00 | yes | 0.071 | 0.065 | 0.0059 | 2 | 53 | - | - |
| click_helpformatter_write_usage_producing_spurious | delegated | 1.00 | yes | 0.069 | 0.060 | 0.0082 | 2 | 41 | - | - |
| click_metavar_for_choice_options_when | delegated | 0.00 | NO | 0.222 | 0.175 | 0.0477 | 12 | 195 | - | tests/test_options.py::test_usage_show_choices[text choices] |
| click_short_help_abbreviation | delegated | 0.00 | NO | 0.124 | 0.112 | 0.0118 | 4 | 90 | - | tests/test_utils/test_make_default_short_help.py::test_make_ |
| click_show_custom_error_message_in | delegated | 0.00 | NO | 0.071 | 0.061 | 0.0102 | 2 | 45 | - | tests/test_termui.py::test_hide_input_error_message[custom-r |
| click_show_envvar_output_for_a | delegated | 1.00 | yes | 0.073 | 0.066 | 0.0070 | 2 | 61 | - | - |
| click_use_non_shadowed_help_option | delegated | 0.00 | NO | 0.168 | 0.129 | 0.0394 | 11 | 184 | - | tests/test_formatting.py::test_formatting_usage_error_help_h |
| click_validate_style_color_arguments_explicit | delegated | 0.00 | NO | 0.073 | 0.065 | 0.0080 | 2 | 50 | - | tests/test_utils/test_style.py::test_styling_invalid_color[- |
| click_deprecated_label_formatting | child alone | 1.00 | yes | 0.009 | 0.009 | 0.0000 | 11 | 27 | - | - |
| click_helpformatter_write_usage_producing_spurious | child alone | 1.00 | yes | 0.005 | 0.005 | 0.0000 | 6 | 19 | - | - |
| click_metavar_for_choice_options_when | child alone | 0.00 | NO | 0.009 | 0.009 | 0.0000 | 12 | 36 | - | tests/test_options.py::test_usage_show_choices[text choices] |
| click_short_help_abbreviation | child alone | 1.00 | yes | 0.006 | 0.006 | 0.0000 | 8 | 25 | - | - |
| click_show_custom_error_message_in | child alone | 0.00 | NO | 0.008 | 0.008 | 0.0000 | 9 | 33 | - | tests/test_termui.py::test_hide_input_error_message[builtin- |
| click_show_envvar_output_for_a | child alone | 0.00 | NO | 0.006 | 0.006 | 0.0000 | 8 | 24 | - | tests/test_options.py::test_missing_envvar_sequence[envvar2- |
| click_use_non_shadowed_help_option | child alone | 0.00 | NO | 0.007 | 0.007 | 0.0000 | 11 | 26 | - | tests/test_formatting.py::test_formatting_usage_error_help_h |
| click_validate_style_color_arguments_explicit | child alone | 0.00 | NO | 0.009 | 0.009 | 0.0000 | 9 | 39 | - | tests/test_utils/test_style.py::test_styling_invalid_color[- |

### Reading code and answering

*Questions about a pinned source tree; ground truth from the syntax tree.* Tasks: `read_invoke_callers`, `read_paramtype_names`. Verdict: **UNSURE (n < 4)**.

| task | arm | score | pass | total $ | parent $ | child $ | parent turns | wall s | parent said | what went wrong |
|---|---|---|---|---|---|---|---|---|---|---|
| read_invoke_callers | parent alone | 1.00 | yes | 0.084 | 0.084 | 0.0000 | 4 | 13 | - | - |
| read_paramtype_names | parent alone | 1.00 | yes | 0.079 | 0.079 | 0.0000 | 5 | 17 | - | - |
| read_invoke_callers | delegated | 1.00 | yes | 0.084 | 0.081 | 0.0030 | 3 | 28 | 70% | - |
| read_paramtype_names | delegated | 1.00 | yes | 0.077 | 0.075 | 0.0028 | 3 | 31 | 65% | - |
| read_invoke_callers | child alone | 1.00 | yes | 0.003 | 0.003 | 0.0000 | 2 | 11 | - | - |
| read_paramtype_names | child alone | 1.00 | yes | 0.004 | 0.004 | 0.0000 | 3 | 13 | - | - |

### Exact fetch from a page

*Details of RFCs published after the models' training.* Tasks: `fetch_rfc10075_snac_bit`, `fetch_rfc9995_cose_labels`. Verdict: **UNSURE (n < 4)**.

| task | arm | score | pass | total $ | parent $ | child $ | parent turns | wall s | parent said | what went wrong |
|---|---|---|---|---|---|---|---|---|---|---|
| fetch_rfc10075_snac_bit | parent alone | 1.00 | yes | 0.063 | 0.063 | 0.0000 | 3 | 12 | - | - |
| fetch_rfc9995_cose_labels | parent alone | 1.00 | yes | 0.087 | 0.087 | 0.0000 | 4 | 14 | - | - |
| fetch_rfc10075_snac_bit | delegated | 1.00 | yes | 0.060 | 0.057 | 0.0028 | 2 | 25 | 60% | - |
| fetch_rfc9995_cose_labels | delegated | 1.00 | yes | 0.084 | 0.082 | 0.0023 | 5 | 36 | 60% | - |
| fetch_rfc10075_snac_bit | child alone | 1.00 | yes | 0.004 | 0.004 | 0.0000 | 2 | 10 | - | - |
| fetch_rfc9995_cose_labels | child alone | 1.00 | yes | 0.004 | 0.004 | 0.0000 | 2 | 10 | - | - |

### Web research with sources

*Facts to find, every claim cited with a quote that must occur on the cited page.* Tasks: `research_jscontact_registry`, `research_oauth_audience`. Verdict: **UNSURE (n < 4)**.

| task | arm | score | pass | total $ | parent $ | child $ | parent turns | wall s | parent said | what went wrong |
|---|---|---|---|---|---|---|---|---|---|---|
| research_jscontact_registry | parent alone | 1.00 | yes | 0.108 | 0.108 | 0.0000 | 6 | 30 | - | - |
| research_oauth_audience | parent alone | 1.00 | yes | 0.130 | 0.130 | 0.0000 | 6 | 41 | - | - |
| research_jscontact_registry | delegated | 1.00 | yes | 0.096 | 0.077 | 0.0185 | 3 | 60 | 55% | - |
| research_oauth_audience | delegated | 0.83 | NO | 0.086 | 0.066 | 0.0198 | 2 | 54 | 40% | missing: ['sole'] |
| research_jscontact_registry | child alone | 1.00 | yes | 0.018 | 0.018 | 0.0000 | 5 | 31 | - | - |
| research_oauth_audience | child alone | 1.00 | yes | 0.032 | 0.032 | 0.0000 | 6 | 33 | - | - |

### Summarising long inputs

*A 270 KB log and a 300-release changelog with planted facts.* Tasks: `summarise_changelog_breaking`, `summarise_incident_log`. Verdict: **UNSURE (n < 4)**.

| task | arm | score | pass | total $ | parent $ | child $ | parent turns | wall s | parent said | what went wrong |
|---|---|---|---|---|---|---|---|---|---|---|
| summarise_changelog_breaking | parent alone | 1.00 | yes | 0.093 | 0.093 | 0.0000 | 6 | 18 | - | - |
| summarise_incident_log | parent alone | 1.00 | yes | 0.078 | 0.078 | 0.0000 | 5 | 17 | - | - |
| summarise_changelog_breaking | delegated | 1.00 | yes | 0.078 | 0.075 | 0.0030 | 3 | 26 | 80% | - |
| summarise_incident_log | delegated | 1.00 | yes | 0.082 | 0.079 | 0.0030 | 5 | 32 | 60% | - |
| summarise_changelog_breaking | child alone | 1.00 | yes | 0.009 | 0.009 | 0.0000 | 3 | 9 | - | - |
| summarise_incident_log | child alone | 1.00 | yes | 0.004 | 0.004 | 0.0000 | 4 | 16 | - | - |

### Data wrangling by script

*A 5,000-row CSV and a 4,000-line event log; computed answers.* Tasks: `wrangle_events_conversion`, `wrangle_orders_revenue`. Verdict: **UNSURE (n < 4)**.

| task | arm | score | pass | total $ | parent $ | child $ | parent turns | wall s | parent said | what went wrong |
|---|---|---|---|---|---|---|---|---|---|---|
| wrangle_events_conversion | parent alone | 1.00 | yes | 0.067 | 0.067 | 0.0000 | 4 | 14 | - | - |
| wrangle_orders_revenue | parent alone | 1.00 | yes | 0.068 | 0.068 | 0.0000 | 4 | 19 | - | - |
| wrangle_events_conversion | delegated | 1.00 | yes | 0.066 | 0.059 | 0.0069 | 2 | 24 | 70% | - |
| wrangle_orders_revenue | delegated | 1.00 | yes | 0.077 | 0.070 | 0.0072 | 3 | 31 | 80% | - |
| wrangle_events_conversion | child alone | 1.00 | yes | 0.004 | 0.004 | 0.0000 | 4 | 16 | - | - |
| wrangle_orders_revenue | child alone | 1.00 | yes | 0.004 | 0.004 | 0.0000 | 4 | 15 | - | - |

### Mixed: read the RFC, then code

*Implement a header parser whose details are only in an RFC.* Tasks: `content_range_rfc`, `retry_after_rfc`. Verdict: **UNSURE (n < 4)**.

| task | arm | score | pass | total $ | parent $ | child $ | parent turns | wall s | parent said | what went wrong |
|---|---|---|---|---|---|---|---|---|---|---|
| content_range_rfc | parent alone | 1.00 | yes | 0.152 | 0.152 | 0.0000 | 11 | 60 | - | - |
| retry_after_rfc | parent alone | 1.00 | yes | 0.347 | 0.347 | 0.0000 | 18 | 139 | - | - |
| content_range_rfc | delegated | 1.00 | yes | 0.110 | 0.107 | 0.0034 | 8 | 66 | - | - |
| retry_after_rfc | delegated | 1.00 | yes | 0.084 | 0.079 | 0.0046 | 3 | 45 | - | - |
| content_range_rfc | child alone | 1.00 | yes | 0.008 | 0.008 | 0.0000 | 6 | 34 | - | - |
| retry_after_rfc | child alone | 1.00 | yes | 0.008 | 0.008 | 0.0000 | 7 | 38 | - | - |

### Control: answerable from memory

*A famous RFC's opcode list: needs no retrieval.* Tasks: `control_rfc6455_opcodes`. Verdict: **UNSURE (n < 4)**.

| task | arm | score | pass | total $ | parent $ | child $ | parent turns | wall s | parent said | what went wrong |
|---|---|---|---|---|---|---|---|---|---|---|
| control_rfc6455_opcodes | parent alone | 1.00 | yes | 0.055 | 0.055 | 0.0000 | 2 | 10 | - | - |
| control_rfc6455_opcodes | delegated | 1.00 | yes | 0.074 | 0.059 | 0.0147 | 2 | 46 | 88% | - |
| control_rfc6455_opcodes | child alone | 1.00 | yes | 0.003 | 0.003 | 0.0000 | 1 | 7 | - | - |

## Method and reproducibility

The `bench/` paths below are at commit `91a53ae` (the folder was removed from the tree on 2026-11-15; see `benchmarks/README.md`).

- Tasks: `bench/tasks/` (code, with hidden tests), `bench/tasks-real/` (fix commits of public repositories) and `bench/tasks-agent/` (non-code). `bench/make_agent_tasks.py` regenerates the non-code ones deterministically; their ground truth comes from generation, the syntax tree, or immutable web pages published after the models' training.
- Graders: `bench/graders.py`. No model judges anything. Research answers must cite a quote that occurs on the cited page.
- Runners: `bench/run_bench.py` (code), `bench/run_agent_bench.py` (non-code). Per-run raw material (transcripts, gruntly records, answers, final patches) is in the git-ignored `bench/runs*/` folders.
- Reports for one experiment: `bench/decision_report.py`. This document: `bench/gold_doc.py`.

## Limits of this evidence

- One repetition per task and arm in most rows: no run-to-run variance is measured.
- Reference and child-alone rows for the code workloads come from earlier days; their cache warmth and prompts may differ.
- Fresh sessions understate what the parent pays per turn in a long session; the long-session column is a model.
- The Haiku child's results do not carry over to a local model or another hosted model; each needs its own run.
- The parent-alone arm is Claude Code as it behaves by default, including its own sub-agents. In 2 of the 14 parent-alone runs of the 2026-11-12 pilot it handed a page fetch to its built-in `web-fetch` sub-agent, which ran on Haiku and cost about $0.001; it never used the `Explore` sub-agent. A run in which Claude Code is *told* to scout with its own sub-agent is not measured yet, so these results do not show that gruntly beats Claude Code's own scouting.
- In the mixed tasks the saving came from the child doing the coding, not the reading: the parent alone wrote about 16,000 output tokens on one task, the delegated parent about 1,300. Two tasks, one run each.
- Subjective work (writing, design) and side-effecting work (setup, deployment) are not measured yet, so this document says nothing about them.
