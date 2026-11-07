# Child benchmark: which profile should the local model get?

Local child `opencode` / `qwen/qwen3.5-9b`, no Claude involved (2026-11-07). Each run is `gruntly run --apply-on-pass` judged by hidden tests. Arms: `default` = the harness as shipped; `typist` / `worker` = slim profiles; suffix `-self` = the child may run the acceptance command itself (otherwise gruntly evaluates and feeds errors back). `precise` briefs are the normal ones; `vague` briefs leave out names, edge cases and the method.

## precise briefs

| arm | runs | first-try pass | hidden-test pass | false pass | escalated | input tok/request | child tok/run | requests/run | wall s |
|---|---|---|---|---|---|---|---|---|---|
| default | 2 | 100% | 100% | 0 | 0 | 11399 | 46069 | 4.0 | 67 |
| typist | 2 | 100% | 100% | 0 | 0 | 1462 | 3403 | 2.0 | 28 |
| typist-self | 2 | 100% | 100% | 0 | 0 | 3020 | 11492 | 3.5 | 38 |
| worker | 2 | 100% | 100% | 0 | 0 | 2516 | 8081 | 3.0 | 29 |

## Per task (hidden-test passes / runs)

| task | brief | default | typist | typist-self | worker |
|---|---|---|---|---|---|
| flatten | precise | 1/1 | 1/1 | 1/1 | 1/1 |
| paginate | precise | 1/1 | 1/1 | 1/1 | 1/1 |

False pass = gruntly reported `passed` (all its gates green) but the hidden tests failed.
Decision rule (docs/plan): adopt typist where its hidden-test pass rate is within 5 points of `default` and it uses at least 40% fewer child tokens; adopt worker where its vague-brief pass rate beats typist by at least 15 points.
