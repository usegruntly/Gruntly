# gruntly benchmark (v2)

Local child: `opencode` / `qwen/qwen3.5-9b` at 32k context. Parent: Claude Code (sonnet). Run 2026-11-08. Pass = hidden tests (never shown to the parent or the child) pass afterwards. S = ten small tasks the parent solves in ~4 turns; L = three larger tasks (six bugs, a 15-file rename, a CLI feature). Arms: `alone`; `forced` (told to delegate through the one-call flow); `policy` (may delegate if the skill's triage rule says so).

## Totals by bucket (means over tasks and repetitions)

| bucket | arm | runs | pass rate | cost $/run | vs alone | turns | session splits | wall s | parent output tok | tool-output KB in context | delegated | child tok |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| S | alone | 12 | 100% | 0.059 | - | 4.7 | 0.0 | 11 | 573 | 0.9 | 0/12 | - |
| S | gd | 12 | 75% | 0.046 | -21% | 1.0 | 0.0 | 42 | 72 | 0.0 | 12/12 | 49804 |
| L | alone | 4 | 100% | 0.069 | - | 4.2 | 0.0 | 15 | 872 | 2.8 | 0/4 | - |
| L | gd | 4 | 100% | 0.081 | +17% | 9.0 | 0.0 | 20 | 1512 | 2.2 | 0/4 | - |

## Per task (mean over repetitions)

| task | arm | pass | cost $ | turns | wall s | gruntly (status, attempts) | false pass |
|---|---|---|---|---|---|---|---|
| bugs_batch | alone | 2/2 | 0.075 | 4.0 | 16 | - | - |
| bugs_batch | gd | 2/2 | 0.094 | 12.5 | 24 | - | - |
| cli_json | alone | 2/2 | 0.063 | 4.5 | 13 | - | - |
| cli_json | gd | 2/2 | 0.069 | 5.5 | 16 | - | - |
| flatten | alone | 2/2 | 0.059 | 5.0 | 11 | - | - |
| flatten | gd | 2/2 | 0.046 | 1.0 | 42 | passed+applied (1); passed+applied (1) | - |
| merge_intervals | alone | 2/2 | 0.057 | 4.0 | 11 | - | - |
| merge_intervals | gd | 2/2 | 0.046 | 1.0 | 39 | passed+applied (1); passed+applied (1) | - |
| paginate | alone | 2/2 | 0.057 | 4.0 | 11 | - | - |
| paginate | gd | 2/2 | 0.046 | 1.0 | 33 | passed+applied (1); passed+applied (1) | - |
| parse_duration | alone | 2/2 | 0.061 | 5.0 | 11 | - | - |
| parse_duration | gd | 1/2 | 0.047 | 1.0 | 52 | passed+applied (1); passed+applied (1) | 1 |
| retry | alone | 2/2 | 0.060 | 5.0 | 11 | - | - |
| retry | gd | 0/2 | 0.047 | 1.0 | 47 | passed+applied (1); passed+applied (1) | 2 |
| slugify | alone | 2/2 | 0.058 | 5.0 | 12 | - | - |
| slugify | gd | 2/2 | 0.047 | 1.0 | 36 | passed+applied (1); passed+applied (1) | - |

Accounting: parent cost is Claude Code's own `total_cost_usd` for the whole session (cache reads included), so any takeover after an escalation is counted. Local child tokens are free of paid cost but cost wall time. False pass = gruntly reported `passed` but the hidden tests failed. Transcripts are in `bench/runs/`.

## What this run shows (Sonnet parent, 16 runs per arm, 2 repetitions of 8 tasks)

`/gruntly:gd <the task's own sentence>` against Claude alone. Six small single-function tasks that `gd` can handle, plus two larger ones (`bugs_batch`, `cli_json`) that it correctly refuses.

- **The mechanism works at scale.** All 12 small runs took exactly 1 model request with 0 tool calls and 0 session splits. `gd` refused both large tasks (no gruntly run), and Claude then did them itself.
- **Cost on tasks `gd` handles: -21%** ($0.046 against $0.059 per run), 1 request against 4.7. About $0.013 per task in absolute terms: these `claude -p` runs are dominated by a fixed ~$0.045 cold-start cost, and a marginal parent turn costs only about $0.0035 here.
- **Correctness is the problem.** Hidden-test pass rate on the small tasks: **75% for `gd` against 100% for Claude alone.** All three failures were *false passes*: gruntly's gates were green and Claude reported success, but the hidden tests failed (`retry` 0/2, `parse_duration` 1/2). Both tasks need behaviour the one-sentence request does not state (for example `retry` must preserve the wrapped function's name); Sonnet supplies such conventions by habit, the 9B model did not.
- **Per solved task the saving disappears:** counting only runs that pass the hidden tests, `gd` costs more per solved task than Claude alone (see the totals), and that ignores the cost of discovering and fixing the false passes.
- **Refusals are not free in practice.** On the two large tasks the slash command added overhead and Claude's fallback was sometimes slower ($0.081 against $0.069, 9 requests against 4.2; one run took 21 requests).
- **Wall time is worse:** about 42 s against 11 s on the small tasks.

Honest limits: 8 tasks, 2 repetitions, one parent model, one local model; the tasks are tiny functions that favour neither side by design. n is too small for the 21% to be more than indicative.
