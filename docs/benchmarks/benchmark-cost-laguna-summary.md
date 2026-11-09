# Cost summary: benchmark-cost-laguna.json

50 runs, 10 tasks. Parent cost is Claude Code's own `total_cost_usd` for the whole session (cache reads included, takeover after a failed delegation included). The child's tokens cost nothing in the primary numbers.

| arm | runs | passed | parent $/run | $ per correct task | turns | parent tokens (all kinds) | of which output | child tokens | delegated | false pass |
|---|---|---|---|---|---|---|---|---|---|---|
| alone | 20 | 19/20 | 0.0619 | 0.0652 | 4.7 | 80,094 | 622 | 0 | 0/20 | - |
| policy | 20 | 20/20 | 0.0641 | 0.0641 | 4.8 | 79,551 | 747 | 0 | 0/20 | - |
| forced | 10 | 10/10 | 0.0896 | 0.0896 | 7.5 | 184,056 | 962 | 0 | 10/10 | - |

### policy against alone (20 paired runs)

- **Primary (child free): parent cost per run 0.0641 vs 0.0619 = +4%** (mean paired difference +0.0022 $, 95% bootstrap interval +0.0013 to +0.0032). 3 of 20 pairs cheaper with gruntly, 17 dearer.
- Correct (hidden tests): 20/20 with gruntly vs 19/20 for the baseline.
- Parent tokens per run (all kinds, cache reads included): 79,551 vs 80,094 (-1%); output tokens 747 vs 622.
- Child tokens per run: 0. In raw tokens, parent + child = 79,551 vs 80,094 (-1%).
- If the child were paid at sonnet-5.5 input ($2.00/M): 0.0641 vs 0.0619 = +4%.
- If the child were paid at haiku-5.5 input ($0.10/M): 0.0641 vs 0.0619 = +4%.

| task | policy $ | alone $ | difference | gruntly status |
|---|---|---|---|---|
| flatten#1 | 0.0645 | 0.0611 | +0.0034 | - |
| flatten#2 | 0.0605 | 0.0603 | +0.0002 | - |
| lru_cache#1 | 0.0627 | 0.0634 | -0.0007 | - |
| lru_cache#2 | 0.0652 | 0.0628 | +0.0024 | - |
| merge_intervals#1 | 0.0646 | 0.0596 | +0.0050 | - |
| merge_intervals#2 | 0.0637 | 0.0592 | +0.0045 | - |
| paginate#1 | 0.0629 | 0.0591 | +0.0038 | - |
| paginate#2 | 0.0632 | 0.0585 | +0.0047 | - |
| parse_duration#1 | 0.0666 | 0.0641 | +0.0025 | - |
| parse_duration#2 | 0.0659 | 0.0646 | +0.0013 | - |
| retry#1 | 0.0688 | 0.0625 | +0.0063 | - |
| retry#2 | 0.0643 | 0.0605 | +0.0038 | - |
| rolling_mean#1 | 0.0621 | 0.0618 | +0.0003 | - |
| rolling_mean#2 | 0.0616 | 0.0602 | +0.0014 | - |
| roman#1 | 0.0682 | 0.0652 | +0.0030 | - |
| roman#2 | 0.0694 | 0.0680 | +0.0014 | - |
| slugify#1 | 0.0604 | 0.0607 | -0.0003 | - |
| slugify#2 | 0.0635 | 0.0612 | +0.0023 | - |
| word_count#1 | 0.0617 | 0.0614 | +0.0003 | - |
| word_count#2 | 0.0628 | 0.0641 | -0.0013 | - |

### forced against alone (10 paired runs)

- **Primary (child free): parent cost per run 0.0896 vs 0.0619 = +45%** (mean paired difference +0.0278 $, 95% bootstrap interval +0.0248 to +0.0314). 0 of 10 pairs cheaper with gruntly, 10 dearer.
- Correct (hidden tests): 10/10 with gruntly vs 10/10 for the baseline.
- Parent tokens per run (all kinds, cache reads included): 184,056 vs 78,842 (+133%); output tokens 962 vs 617.
- Child tokens per run: 0. In raw tokens, parent + child = 184,056 vs 78,842 (+133%).
- If the child were paid at sonnet-5.5 input ($2.00/M): 0.0896 vs 0.0619 = +45%.
- If the child were paid at haiku-5.5 input ($0.10/M): 0.0896 vs 0.0619 = +45%.

| task | forced $ | alone $ | difference | gruntly status |
|---|---|---|---|---|
| flatten#1 | 0.0833 | 0.0611 | +0.0222 | passed |
| lru_cache#1 | 0.0849 | 0.0634 | +0.0215 | passed |
| merge_intervals#1 | 0.0875 | 0.0596 | +0.0279 | passed |
| paginate#1 | 0.0844 | 0.0591 | +0.0253 | passed |
| parse_duration#1 | 0.0914 | 0.0641 | +0.0273 | passed |
| retry#1 | 0.0952 | 0.0625 | +0.0327 | passed |
| rolling_mean#1 | 0.0865 | 0.0618 | +0.0247 | passed |
| roman#1 | 0.0908 | 0.0652 | +0.0256 | passed |
| slugify#1 | 0.0893 | 0.0607 | +0.0286 | passed |
| word_count#1 | 0.1031 | 0.0614 | +0.0417 | error |

