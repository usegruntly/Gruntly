# Deep-session benchmark

Parent: Claude Code `sonnet`; child: `hermes` / `poolside/laguna-xs-2.1` (nvidia). Run 2026-11-12. One session per arm, primed to about 150,000 tokens, then the same tasks in the same order with `--resume`. Pass = hidden tests. The priming turn is listed apart and not charged to the tasks.

| arm | tasks | pass | cost per task $ | cost of a pass $ | turns per task | takeover edits per task | context at the end | priming $ |
|---|---|---|---|---|---|---|---|---|
| alone | 2 | 100% | 1.539 | 1.539 | 5.5 | 0.0 | 316,124 | 0.9631 |

## Per task

| # | task | arm | pass | cost $ | turns | context | takeover edits | gruntly | wall s |
|---|---|---|---|---|---|---|---|---|---|
| 1 | flatten | alone | yes | 1.4672 | 6 | 313,758 | 0 | - | 16 |
| 2 | lru_cache | alone | yes | 1.6107 | 5 | 316,124 | 0 | - | 15 |

Cost is Claude Code's `total_cost_usd` for that call only (the reviewers, if any, are not used in this benchmark). The child is local or the person's own hosted key and is never counted as money. Ten tasks per arm is a measurement of cost in a long session, not a quality claim: the order, the cache window and one repetition are fixed (see the protocol in `docs/investigation-2026-11-11.md` section 9).

**Read this before using these numbers.** The run was stopped after 2 of 10 tasks, with $4.04 spent (priming $0.96 plus $1.47 and $1.61), well past its $2.5 cap: the cap was checked between calls, and a single call at this context size cost more than the margin. The costs are not those of a long interactive session. `modelUsage` shows about 300k cache-creation tokens in each task call (299,239 and 301,186, about $1.2 at $4/M), so each `claude -p --resume` call re-wrote nearly the whole context to the cache; the same 5 or 6 turns cost about $0.46 in the user's own sessions above 300k tokens ($0.076 a turn). The priming also overshot: 83 turns left 226k tokens of context for a 150k target. What this run does show: the per-call overhead of resuming a very large session is dominated by cache writes, so a benchmark of delegation in a long session must keep one process alive (a stream-json input) instead of resuming. The delegated arm was not run, because the hosted child was down (see `../plan-2026-11-11.md`, status).
