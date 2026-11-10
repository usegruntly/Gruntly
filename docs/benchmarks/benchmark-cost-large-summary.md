# Cost summary: benchmark-cost-large.json

6 runs, 3 tasks. Parent cost is Claude Code's own `total_cost_usd` for the whole session (cache reads included, takeover after a failed delegation included). The child's tokens cost nothing in the primary numbers.

| arm | runs | passed | parent $/run | $ per correct task | turns | parent tokens (all kinds) | of which output | child tokens | delegated | false pass |
|---|---|---|---|---|---|---|---|---|---|---|
| alone | 3 | 3/3 | 0.0701 | 0.0701 | 4.3 | 107,547 | 785 | 0 | 0/3 | - |
| forced | 3 | 3/3 | 0.0901 | 0.0901 | 7.3 | 179,877 | 1,118 | 0 | 2/3 | - |

### forced against alone (3 paired runs)

- **Primary (child free): parent cost per run 0.0901 vs 0.0701 = +28%** (mean paired difference +0.0199 $, 95% bootstrap interval +0.0137 to +0.0235). 0 of 3 pairs cheaper with gruntly, 3 dearer.
- Correct (hidden tests): 3/3 with gruntly vs 3/3 for the baseline.
- Parent tokens per run (all kinds, cache reads included): 179,877 vs 107,547 (+67%); output tokens 1,118 vs 785.
- Child tokens per run: 0. In raw tokens, parent + child = 179,877 vs 107,547 (+67%).
- If the child were paid at sonnet-5.5 input ($2.00/M): 0.0901 vs 0.0701 = +28%.
- If the child were paid at haiku-5.5 input ($0.10/M): 0.0901 vs 0.0701 = +28%.

| task | forced $ | alone $ | difference | gruntly status |
|---|---|---|---|---|
| bugs_batch#1 | 0.1022 | 0.0796 | +0.0226 | passed, passed, passed, passed |
| cli_json#1 | 0.0801 | 0.0664 | +0.0137 | passed |
| rename_domain#1 | 0.0879 | 0.0644 | +0.0235 | - |

