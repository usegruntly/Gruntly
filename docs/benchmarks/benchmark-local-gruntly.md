# Child benchmark: which profile should the local model get?

Local child `opencode` / `qwen/qwen3.5-9b`, no Claude involved (2026-11-08). Each run is `gruntly run --apply-on-pass` judged by hidden tests. Arms: `default` = the harness as shipped; `typist` / `worker` = slim profiles; suffix `-self` = the child may run the acceptance command itself (otherwise gruntly evaluates and feeds errors back). `precise` briefs are the normal ones; `vague` briefs leave out names, edge cases and the method.

## precise briefs

| arm | runs | first-try pass | hidden-test pass | false pass | escalated | input tok/request | child tok/run | requests/run | wall s |
|---|---|---|---|---|---|---|---|---|---|
| auto | 14 | 86% | 71% | 3 | 1 | 1770 | 4732 | 2.3 | 48 |

## Per task (hidden-test passes / runs)

| task | brief | auto |
|---|---|---|
| bugs_batch | precise | 0/1 |
| cli_json | precise | 1/1 |
| flatten | precise | 2/2 |
| merge_intervals | precise | 2/2 |
| paginate | precise | 2/2 |
| parse_duration | precise | 1/2 |
| retry | precise | 0/2 |
| slugify | precise | 2/2 |

False pass = gruntly reported `passed` (all its gates green) but the hidden tests failed.
Decision rule (docs/plan): adopt typist where its hidden-test pass rate is within 5 points of `default` and it uses at least 40% fewer child tokens; adopt worker where its vague-brief pass rate beats typist by at least 15 points.
