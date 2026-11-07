# Child benchmark: which profile should the local model get?

Local child `opencode` / `qwen/qwen3.5-9b`, no Claude involved (2026-11-07). Each run is `gruntly run --apply-on-pass` judged by hidden tests. Arms: `default` = the harness as shipped; `typist` / `worker` = slim profiles; suffix `-self` = the child may run the acceptance command itself (otherwise gruntly evaluates and feeds errors back). `precise` briefs are the normal ones; `vague` briefs leave out names, edge cases and the method.

## precise briefs

| arm | runs | first-try pass | hidden-test pass | false pass | escalated | input tok/request | child tok/run | requests/run | wall s |
|---|---|---|---|---|---|---|---|---|---|
| default | 16 | 100% | 62% | 6 | 0 | 12991 | 132012 | 8.2 | 161 |
| typist | 16 | 81% | 69% | 4 | 1 | 2886 | 39760 | 6.6 | 91 |
| typist-self | 16 | 100% | 62% | 6 | 0 | 4361 | 37863 | 5.8 | 83 |
| worker | 16 | 69% | 69% | 3 | 2 | 4317 | 36522 | 5.4 | 106 |

## vague briefs

| arm | runs | first-try pass | hidden-test pass | false pass | escalated | input tok/request | child tok/run | requests/run | wall s |
|---|---|---|---|---|---|---|---|---|---|
| default | 6 | 100% | 17% | 5 | 0 | 12256 | 81346 | 6.5 | 127 |
| typist | 5 | 40% | 20% | 4 | 0 | 3023 | 9140 | 2.4 | 86 |
| typist-self | 5 | 100% | 20% | 4 | 0 | 4136 | 27869 | 6.0 | 76 |
| worker | 5 | 100% | 0% | 5 | 0 | 3104 | 17592 | 4.6 | 51 |

## Per task (hidden-test passes / runs)

| task | brief | default | typist | typist-self | worker |
|---|---|---|---|---|---|
| bugs_batch | precise | 0/2 | 1/2 | 0/2 | 0/2 |
| bugs_batch | vague | 0/1 | 0/1 | 0/1 | 0/1 |
| cli_json | precise | 2/2 | 2/2 | 2/2 | 2/2 |
| cli_json | vague | 0/1 | 0/1 | 0/1 | 0/1 |
| flatten | precise | 2/2 | 2/2 | 2/2 | 2/2 |
| paginate | precise | 2/2 | 2/2 | 2/2 | 2/2 |
| parse_duration | precise | 1/2 | 0/2 | 0/2 | 0/2 |
| parse_duration | vague | 1/2 | 0/1 | 0/1 | 0/1 |
| rename_domain | precise | 2/2 | 2/2 | 2/2 | 2/2 |
| retry | precise | 0/2 | 0/2 | 0/2 | 1/2 |
| slugify | precise | 1/2 | 2/2 | 2/2 | 2/2 |
| slugify | vague | 0/2 | 1/2 | 1/2 | 0/2 |

False pass = gruntly reported `passed` (all its gates green) but the hidden tests failed.
Decision rule (docs/plan): adopt typist where its hidden-test pass rate is within 5 points of `default` and it uses at least 40% fewer child tokens; adopt worker where its vague-brief pass rate beats typist by at least 15 points.

## Result

Only OpenCode was measured (Qwen Code's slim path is still untested). The precise stage is complete (64 runs, 2 repetitions); the vague stage stopped at 21 of 32 runs when the machine ran low on memory, so its cells hold 5 to 6 runs each: read them as directional.

Applying the decision rule written before the run:

1. **Adopt `typist` for small, literal scopes: yes.** Hidden-test pass rate 68% against 62% for `default` (within the 5-point margin, and slightly above). Child tokens per run: 39,760 against 132,012 (-70%); on the tasks that finished in every arm, excluding the 15-file rename, 12.8k against 61.4k (-79%). Wall time 90 s against 160 s.
2. **Adopt `worker` where it beats typist on vague briefs by 15 points: no.** On vague briefs `worker` passed 0 of 5, `typist` 1 of 5, `default` 1 of 6. No profile, including the stock harness, can resolve an ambiguous brief with this model: 4 to 5 of every 5 runs passed gruntly's gates and failed the hidden tests. **The child should not be the planner; the parent keeps writing precise briefs.** `worker` is only a fallback for tasks whose files cannot be named in advance.
3. **Evaluate & fix (no shell for the child) is not worse than letting it test itself.** `typist` against `typist-self`: hidden-test passes 11/16 against 10/16, and `typist-self` used more tokens on the comparable tasks (16.4k against 12.8k). Letting the child run the acceptance command bought nothing.

What no profile fixed: **false passes** (gates green, hidden tests red): 6 of 16 `default`, 4 `typist`, 6 `typist-self`, 3 `worker`. They come from briefs and visible tests that do not mention behaviour the hidden tests check (for example `retry` must keep the wrapped function's name), so they cannot be fixed by changing the child's prompt. The remedy is the held-out `holdout` test and fuller briefs.

Limits: two repetitions per cell, one harness, one local model, and the `rename_domain` outlier (a 15-file scope inlined into every request) dominates the token averages. `auto` should send multi-file or glob scopes to `worker`, never `typist`; that rule is already in `profiles.resolve`.
