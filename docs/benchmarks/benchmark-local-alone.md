# The local model alone (no Claude, no gruntly)

`opencode` stock agent / `qwen/qwen3.5-9b`, run 2026-11-08. Same tasks, instructions and hidden-test judge as the `alone` arm for Claude. No gates, no retries, no evaluate & fix.

| task | hidden-test pass | visible check passes at the end | wall s | child tokens | requests |
|---|---|---|---|---|---|
| bugs_batch | 0/2 | 2/2 | 338 | 161137 | 11.0 |
| cli_json | 2/2 | 2/2 | 110 | 119656 | 9.5 |
| flatten | 2/2 | 2/2 | 179 | 44942 | 4.0 |
| merge_intervals | 2/2 | 2/2 | 142 | 51780 | 4.5 |
| paginate | 2/2 | 2/2 | 76 | 51347 | 4.5 |
| parse_duration | 1/2 | 2/2 | 94 | 168520 | 13.0 |
| retry | 0/2 | 2/2 | 64 | 71123 | 6.0 |
| slugify | 1/2 | 2/2 | 94 | 56760 | 5.0 |

**Overall: 10/16 pass the hidden tests; 16/16 pass the visible check, and 6 of those fail the hidden tests (false passes).** Mean wall time 137 s, mean 90,658 local tokens per run.
