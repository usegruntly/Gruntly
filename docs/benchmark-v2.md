# gruntly benchmark (v2)

Local child: `opencode` / `qwen/qwen3.5-9b` at 32k context. Parent: Claude Code (default model). Run 2026-11-07. Pass = hidden tests (never shown to the parent or the child) pass afterwards. S = ten small tasks the parent solves in ~4 turns; L = three larger tasks (six bugs, a 15-file rename, a CLI feature). Arms: `alone`; `forced` (told to delegate through the one-call flow); `policy` (may delegate if the skill's triage rule says so).

## Totals by bucket (means over tasks and repetitions)

| bucket | arm | runs | pass rate | cost $/run | vs alone | turns | wall s | parent output tok | tool-output KB in context | delegated | child tok |
|---|---|---|---|---|---|---|---|---|---|---|---|
| S | alone | 5 | 100% | 0.157 | - | 5.4 | 19 | 758 | 1.3 | 0/5 | - |
| S | forced | 5 | 100% | 0.186 | +19% | 3.8 | 137 | 673 | 1.1 | 5/5 | 288188 |
| S | policy | 5 | 100% | 0.168 | +7% | 6.2 | 22 | 852 | 1.4 | 0/5 | - |
| L | alone | 3 | 100% | 0.170 | - | 4.0 | 22 | 1090 | 2.4 | 0/3 | - |
| L | forced | 3 | 67% | 0.266 | +57% | 5.0 | 280 | 1134 | 3.4 | 2/3 | 101212 |
| L | policy | 3 | 100% | 0.172 | +1% | 4.3 | 25 | 996 | 1.6 | 0/3 | - |

## Per task (mean over repetitions)

| task | arm | pass | cost $ | turns | wall s | gruntly (status, attempts) | false pass |
|---|---|---|---|---|---|---|---|
| bugs_batch | alone | 1/1 | 0.180 | 3.0 | 24 | - | - |
| bugs_batch | forced | 0/1 | 0.349 | 3.0 | 259 | passed+applied (1) | 1 |
| bugs_batch | policy | 1/1 | 0.180 | 3.0 | 25 | - | - |
| cli_json | alone | 1/1 | 0.165 | 5.0 | 22 | - | - |
| cli_json | forced | 1/1 | 0.229 | 8.0 | 134 | passed+applied (1) | - |
| cli_json | policy | 1/1 | 0.171 | 6.0 | 22 | - | - |
| flatten | alone | 1/1 | 0.171 | 7.0 | 24 | - | - |
| flatten | forced | 1/1 | 0.178 | 2.0 | 55 | passed+applied (1) | - |
| flatten | policy | 1/1 | 0.176 | 7.0 | 23 | - | - |
| paginate | alone | 1/1 | 0.154 | 6.0 | 18 | - | - |
| paginate | forced | 1/1 | 0.157 | 4.0 | 158 | passed+applied (1) | - |
| paginate | policy | 1/1 | 0.157 | 5.0 | 17 | - | - |
| parse_duration | alone | 1/1 | 0.153 | 4.0 | 16 | - | - |
| parse_duration | forced | 1/1 | 0.156 | 4.0 | 160 | passed+applied (1) | - |
| parse_duration | policy | 1/1 | 0.186 | 7.0 | 26 | - | - |
| rename_domain | alone | 1/1 | 0.165 | 4.0 | 20 | - | - |
| rename_domain | forced | 1/1 | 0.220 | 4.0 | 446 | - | - |
| rename_domain | policy | 1/1 | 0.166 | 4.0 | 27 | - | - |
| retry | alone | 1/1 | 0.150 | 4.0 | 17 | - | - |
| retry | forced | 1/1 | 0.282 | 5.0 | 119 | passed+applied (1) | - |
| retry | policy | 1/1 | 0.165 | 6.0 | 20 | - | - |
| slugify | alone | 1/1 | 0.156 | 6.0 | 19 | - | - |
| slugify | forced | 1/1 | 0.156 | 4.0 | 191 | passed+applied (1) | - |
| slugify | policy | 1/1 | 0.158 | 6.0 | 22 | - | - |

Accounting: parent cost is Claude Code's own `total_cost_usd` for the whole session (cache reads included), so any takeover after an escalation is counted. Local child tokens are free of paid cost but cost wall time. False pass = gruntly reported `passed` but the hidden tests failed. Transcripts are in `bench/runs/`.

## What this run shows (n = 1 per cell, Opus 5.5 as the parent)

**There is no saving anywhere in this run.** Cost per run: small tasks alone $0.157, forced delegation $0.186 (+19%), policy $0.168 (+7%); larger tasks alone $0.170, forced $0.266 (+57%), policy $0.172 (+1%).

1. **The flow overhead is now about zero on clean runs.** v1 cost +70%. Here `flatten` +4%, `paginate` +2%, `parse_duration` +2%, `slugify` 0%, `cli_json` +39% (8 turns, one holdout detour). The small-task mean of +19% is dominated by `retry` (+88%): the parent wrote its holdout test outside the repo, gruntly crashed with a raw git error, and the parent spent turns recovering. That is a gruntly bug, fixed in 0.2.1 (a clear error at spec time, and a skill note).
2. **There is a price floor the tasks never get past.** Every `alone` session costs $0.15 to $0.18 whatever the task, because each turn re-reads a ~65k-token cached prefix (the user's tools and MCP servers). Delegation can only save what the parent spends beyond that floor. Opus finished even the "large" tasks in 3 to 5 turns (one `sed`, one multi-file write), so there was almost nothing beyond the floor to save. These tasks measure overhead only. They cannot show a win.
3. **The triage rule works.** The policy arm delegated 0 of 8 tasks and cost about the same as alone (+1% to +7%, the cost of loading the skill).
4. **Quality is worse when delegated.** Alone passed 8/8. Forced delegation passed 7/8 hidden-test suites and had: one **false pass** (`bugs_batch`: gruntly's gates and the parent's own holdout were green, the benchmark's hidden edge cases failed: a holdout is only as good as the tests the parent thinks to write), and one **escalation** (`rename_domain`: the parent forgot `tests_writable: true`, now in the skill; it then did the rename itself with `sed`).
5. **The local model did its part.** 6 of 7 delegations passed on the first attempt, in 55 to 450 s, about 58k child tokens each, at 32k context (the 15k-context runs in v1 escalated 3 of 10).

Caveats: one repetition per cell, so differences of a few percent are noise (prompt-cache warmth alone moves a run by about $0.02). `turns` is Claude's `num_turns`, which restarts when a run goes to the background, so it undercounts; trust cost. A legacy `gruntly stats` row (old 15k-context runs, marked `avoid`) was visible to the parent throughout and may have discouraged delegation in the policy arm.

## What it means

The idea is **untested, not refuted**. On tasks the parent can finish in 3 to 5 turns, the best a delegation flow can do is break even, and this one nearly does. To find out whether delegation can win, the benchmark needs tasks where the parent's own cost is well above the floor (15 to 30 turns: exploring an unfamiliar repo, debug loops, writing tests to a coverage target), a parent whose turns cost less than Opus's, and a long session where tool output piling up in context is what costs money. The tasks here are too regular (a single `sed` solves them) and too small. Next experiment: three to five real-repo tasks of that size, three repetitions, `alone` against `policy`.
