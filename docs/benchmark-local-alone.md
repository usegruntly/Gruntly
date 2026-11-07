# The local model alone (no Claude, no gruntly)

`opencode` stock agent / `qwen/qwen3.5-9b`, run 2026-11-08. Same tasks, instructions and hidden-test judge as the `alone` arm for Claude. No gates, no retries, no evaluate & fix.

| task | hidden-test pass | visible check passes at the end | wall s | child tokens | requests |
|---|---|---|---|---|---|
| flatten | 1/1 | 1/1 | 204 | 45009 | 4.0 |
| merge_intervals | 1/1 | 1/1 | 90 | 57953 | 5.0 |
| paginate | 1/1 | 1/1 | 62 | 56821 | 5.0 |
| parse_duration | 0/1 | 1/1 | 117 | 202889 | 15.0 |
| retry | 0/1 | 1/1 | 57 | 69961 | 6.0 |
| slugify | 0/1 | 1/1 | 77 | 56714 | 5.0 |

**Overall: 3/6 pass the hidden tests; 6/6 pass the visible check, and 3 of those fail the hidden tests (false passes).** Mean wall time 101 s, mean 81,558 local tokens per run.
