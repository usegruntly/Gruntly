# Can gruntly be cheaper than Claude alone? Investigation of 2026-11-11

Protocol followed: `docs/investigation-protocol.md`. Every number is labelled **measured** (from a transcript or a run on
this machine), **derived** (computed from measured numbers by a stated formula) or **estimate**. Raw data:
`bench/runs*/`, `docs/benchmarks/*.json`, the user's own Claude Code session files (aggregates only), and the scripts named
in section 10.

## Verdict

**Yes, it can be cheaper, in one regime, and the benchmarks run until yesterday were structurally unable to show it.**

- **Measured, fresh session, small tasks (the hardest case):** with the one-call flow finished yesterday, Sonnet delegating
  to Laguna took **exactly 2 parent turns in 5 of 5 runs**, at $0.056 against $0.062 alone (**−11%**), 4 of 5 correct (one
  passed the gates but failed the hidden tests). The older one-turn `/gd` path, where the result arrives with the prompt,
  measured **−21%** ($0.047) at 75% correct with a weak 9B child.
- **Derived for the user's real sessions:** a turn there costs $0.013 to $0.076 (median $0.036 at 150k to 300k of context),
  3 to 10 times the $0.006 of a benchmark turn. From those measured per-turn costs, a 2-turn delegation with one Sonnet
  review and a 10% takeover allowance costs **35% less than Sonnet alone on a 4-turn task and 67% less on an 8-turn task**
  at 150k to 300k context. Break-even is **3 alone-turns** in every real-session regime, 5 in the fresh benchmark session.
- **Where that matters:** 27% of the user's prompts take 8 or more turns, and those prompts are **63% of everything spent**.
  The median prompt (3 turns, $0.14) is at break-even; delegating it gains nothing.
- **The condition is discipline, not machinery:** exactly 2 parent turns (1 with `/gd`), no takeover, a child that finishes
  (Laguna 13 of 14 today, Haiku 5.5 14 of 15), deterministic gates, at most one strong review. Every earlier loss in this
  project came from extra parent turns: skill loads, manual reads, YAML specs, `git diff`, waits, takeovers.
- **The uncomfortable finding:** a free local child is worth about **$0.005 per task** over Haiku 5.5 doing the same work
  inside Claude Code ($0.0037 to $0.0087 measured, 14 of 15 correct, 17 s). The saving comes from the parent's turns, and
  any child delivers that. Claude Code's own Haiku sub-agent delivers the child part at $0.004, but measured today it cost
  the parent 7 to 11 API calls because it runs in the background and re-invokes the parent on every notification
  ($0.071 to $0.076 per task, dearer than Sonnet alone), so gruntly's blocking one-call shape is cheaper than the built-in
  alternative. What is defensible about gruntly is that shape, the worktree and gates, holdout tests, and, on a
  subscription, a child that does not consume the usage limit (which stopped this investigation twice today).
- **Confidence:** high on the fresh-session numbers (measured, n=5 to 20); medium on the deep-session numbers (a model
  built from measured per-turn costs, validated against every measured arm within $0.004, but not an end-to-end run);
  low on quality at scale (n=5 to 15, synthetic tasks, one false pass already seen). The experiment that settles the
  deep-session claim is designed in section 9 and costs about $3.50.

"It will never work" is false. "It always works" is also false: on prompts of 3 turns or fewer, or whenever the parent
spends a third turn, it loses.

## 1. How Claude Code bills a turn (measured)

Fitted against Claude Code's own `total_cost_usd` on 141 benchmark transcripts, then checked on three of them to the cent
(`modelUsage.costBasis: list`):

| Sonnet 5.5 | per million tokens |
|---|---|
| fresh input | $2.00 |
| output | $10.00 |
| cache read | **$0.10** (0.05x; the pricing page confirms 0.05x for Sonnet 5.5 and Opus 5.5, 0.1x for other models) |
| cache write, 1 hour | **$4.00** (2x) |

Claude Code writes only 1-hour cache entries (1,678,501 one-hour tokens, zero five-minute tokens across the transcripts).
Haiku 5.5: $0.10 / $0.50 / $0.01 / $0.20 for prompts up to 100k tokens. Opus 5.5: $4 / $20 / $0.20 / $8.

A turn therefore costs about `context × $0.10/M + new tokens × $4/M + output × $10/M`. New tokens are expensive (40 reads'
worth) and the context is cheap per token but re-read every turn.

**The fresh-session floor.** In a `claude -p` session, turn 1 writes Claude Code's own prompt into the cache: median 10,950
tokens written plus 14,517 read, **about $0.045**. A later turn at the median 27k context with 664 new tokens costs about
$0.006. So of a $0.062 benchmark task, **$0.045 (72%) is paid before the task starts, identically in every arm**. A perfect
2-turn delegation can only remove the two or three $0.006 turns after the floor: the best possible fresh-session result is
about −17%, and −11% was measured.

## 2. Where the user's money actually goes (measured from the user's own sessions)

Twelve sessions with five or more turns (bench and test sessions excluded), 1,967 main-session turns, $142 at list prices.
Caveat: 1,333 of those turns are this one gruntly development session (Sonnet, median context 328k, maximum 858k, $111); the
Website session (Opus, 244 turns, median 130k, $14) and a session on another project (Sonnet, 215 turns, median 263k, $12) are the
next largest.

**A turn by context size** (median of that turn's cost, including its typical new-token write):

| context at the turn | turns | median new tokens | median cost per turn |
|---|---|---|---|
| 30k to 60k | 143 | 715 | $0.013 |
| 60k to 100k | 291 | 812 | $0.018 |
| 100k to 150k | 271 | 952 | $0.024 |
| 150k to 300k | 475 | 1,108 | $0.036 |
| 300k and above | 781 | 1,324 | $0.076 |

**What a prompt costs:** 265 prompts; turns per prompt median 3, 75th percentile 8, 90th percentile 20, maximum 122; cost per
prompt median $0.143, 75th percentile $0.457, 90th percentile $1.22, mean $0.544. Prompts with 8+ turns: 71 (27%), 63% of all
cost, median $0.643 each. Prompts with 1 to 3 turns: 147 (55%), 25% of cost. Prompts that start above 300k of context: median
4 turns and $0.395, mean $1.15.

**Where the bill goes:** Sonnet turns: cache read 58%, cache write 21%, output and fresh input 21%. Opus turns: 56 / 28 / 16.
The context is re-read every turn, so its size is the first-order cost; new tokens are second; the model's own output is a
small share.

**What grows the context.** Excluding cache re-writes, 3.91M tokens were written. A regression of each turn's written tokens
on the previous turn's output and on the tool results it carried gives `new ≈ 1.11 × previous output tokens + 0.10 × tool-result
tokens + 590` (R² 0.51): **about 59% of growth is the model's own previous output, thinking included, re-sent at the next
tool step**, as the API requires during tool use (Anthropic's extended-thinking documentation: thinking blocks of the last
assistant message must be passed back during tool use and are billed for the blocks shown). Tool results are between 3%
(regression) and 33% (raw characters at 3.5 per token) of growth; the gap comes from Claude Code's truncation of large
outputs and from the chars-per-token estimate. Either way, **a parent tool step writes its own thinking into the cache at
$4/M**, which is a second mechanism, besides the re-read, by which fewer parent turns save money.

**Cache re-writes after an idle hour or a model switch:** 11 turns, 2.69M tokens, **$25.63 (18% of the $142)**. Median
re-write 128k tokens, $0.51; the largest 650,642 tokens after switching to Fable 5.1 at $20/M, **$13.01 for one turn**. This
has nothing to do with gruntly, but it is the single largest avoidable cost in these sessions.

## 3. What was measured today

New runs (about $0.75 in total, see section 10):

| arm | runs | correct (hidden tests) | parent cost per run | parent turns | wall |
|---|---|---|---|---|---|
| Haiku 5.5 alone, Claude Code, all 15 tasks | 15 | 14 (bugs_batch failed) | **$0.0050** (small tasks $0.0037 to $0.0044) | 6.5 | 17 s |
| Sonnet → gruntly, one-call flow, Hermes + Laguna, 5 small tasks | 5 | 4 (word_count: gates passed, hidden tests failed) | **$0.0559** | **2.0 in every run** | 74 s (38 to 158) |
| Sonnet → one Haiku sub-agent inside Claude Code, 4 tasks | see section 3a | | | | |

Earlier measurements this week, same tasks, Sonnet parent, fresh sessions: alone $0.062 (19 to 20 of 20 correct);
plugin installed and Claude deciding, +4% and it never delegated; forced through the old spec flow, +45% at 7.5 turns;
`/gd` one turn, $0.047 (−21%) at 75% correct with Qwen 9B, 100% when Claude then checked the diff but at alone's cost;
planner (Claude plans, child explores), 0 of 3; the three larger tasks, +28% at 7.3 turns.

### 3a. Sonnet with a Haiku sub-agent inside Claude Code (measured)

4 of 4 correct. Claude Code reported 2 turns, but the parent made **7 to 11 API calls**: the Agent tool started the
sub-agent in the background, each of its notifications re-invoked the parent (several of those calls were thinking only),
then the parent ran the check itself and replied. Cost **$0.0707 to $0.0756** per run: Sonnet $0.067 to $0.071 plus Haiku
$0.0036 to $0.0042. That is +14% to +22% against Sonnet alone and +27% to +35% against gruntly's blocking call on the same
tasks. The Haiku child's own cost matched the model ($0.005). The lesson is about shape, not models: the cheapest delegation
is one blocking call whose single tool result holds everything the parent needs; in this Claude Code build the Agent tool is
not that shape, and gruntly's `agent-run` is.

A note on counting: Claude Code's `num_turns` counts user-visible turns, so where this document gives turns for today's
runs they were counted as API calls from message ids: Sonnet alone 3 to 5, gruntly 2, sub-agent 7 to 11.

## 4. The cost model (`bench/cost_model.py`)

Inputs are the measured prices, the $0.045 fresh-session floor, 700 new tokens per alone turn, an 800-token result block,
a 150-token request, a $0.005 Haiku child, a $0.0072 Sonnet review (low effort, caching off, measured) and the real-session
per-turn medians above. Validation against the fresh-session arms: alone modelled $0.066 (measured $0.062), 2-turn delegation
$0.054 (measured $0.056), one turn $0.049 (measured $0.047).

| design | fresh 27k | 60-100k | 100-150k | 150-300k | 300k+ |
|---|---|---|---|---|---|
| Sonnet alone, 4 turns | 0.066 | 0.071 | 0.096 | 0.143 | 0.304 |
| Sonnet alone, 8 turns | 0.095 | 0.142 | 0.191 | 0.286 | 0.607 |
| gruntly, 2 parent turns, free child, gates only | 0.054 | 0.035 | 0.048 | 0.072 | 0.152 |
| + one Sonnet final review | 0.061 | 0.043 | 0.055 | 0.079 | 0.159 |
| + 10% takeover risk on a 4-turn task | 0.067 | 0.050 | 0.065 | 0.093 | 0.189 |
| gruntly, Haiku child in Claude Code, + Sonnet review | 0.066 | 0.048 | 0.060 | 0.084 | 0.164 |
| supervised (plan review, 6 Haiku step reviews, final Sonnet) | 0.072 | 0.053 | 0.066 | 0.090 | 0.170 |
| one parent turn (`/gd` style), free child, gates only | 0.049 | 0.018 | 0.024 | 0.036 | 0.076 |
| gruntly outside the session + Sonnet review (0 parent turns) | 0.007 | 0.007 | 0.007 | 0.007 | 0.007 |
| Haiku alone in Claude Code (a model choice, not a delegation) | 0.005 | 0.005 | 0.005 | 0.005 | 0.005 |

Break-even (2 parent turns, free child, one Sonnet review, 10% takeover): 5 alone-turns in the fresh benchmark session,
**3 alone-turns in every real-session regime**. Context kept out of the session per delegation: about 2k tokens on a 4-turn
task, 4.8k on 8 turns, 9.7k on 15 turns, worth $4/M once and $0.10/M on every later turn.

The deep-session columns are a model. Their inputs are measured, but no end-to-end delegated task has been run inside a
150k-context session yet. Section 9 designs that run.

## 5. Why the earlier benchmarks said "never"

1. **The floor.** $0.045 of every $0.062 fresh-session task is Claude Code writing its own prompt into the cache. Both arms
   pay it. Differences of a few turns are compressed to a few percent.
2. **The tasks.** Sonnet finishes them in 4 to 5 turns. Break-even in that session is 5 turns.
3. **The flow.** Until yesterday a delegation cost 7.5 parent turns (skill load, flag guessing, the manual, a YAML spec,
   `git diff`, waits, takeovers). Today it costs 2.
4. **No carry.** A fresh session ends after the task, so the benchmark never counts the context Claude alone adds and then
   re-reads for the rest of a real session.
5. **Wrong unit.** Real tasks cost $0.30 to $1.20 (Agentless reports $0.34 to $0.70 per SWE-bench Lite issue; vals.ai
   measured about $1.24 per SWE-bench Verified task for Claude 4 Sonnet; the user's own 90th-percentile prompt is $1.22). A
   $0.06 task cannot show a $0.05 saving.

## 6. Designs, ranked

**A. Keep the concept; make the two-turn flow the product (recommended first).** Measured −11% fresh; derived −35% to −67%
in deep sessions on 4- to 8-turn tasks. What it needs: the one call (done), a result block the parent never needs to look
past (done, code first), gates, one optional Sonnet review of the final diff, and **the parent writing a holdout test in the
same call** when it knows the behaviour: output tokens are cheap ($10/M for a 30-line test is $0.003) and a holdout is the
one check that catches the "passed the gates, failed the hidden tests" case seen in 1 of 5 runs today. Loses when the
prompt is 3 turns or fewer, or the child fails and the parent takes over.

**B. One parent turn.** `/gd` runs gruntly before the model's turn, so the block arrives with the prompt: measured 1 API call,
−21% fresh, derived −75% deep. Two fixes make it real: `plugin/commands/gd.md` uses `--max-block 100`, which returns
"still running" for any child slower than 100 s (Laguna took 38 to 158 s today) and forces a second turn; and the quality
depends entirely on the child plus gates, so it suits bounded requests only. A hook that runs gruntly when mode is ON and
the prompt is clearly bounded would give the same one-turn cost without typing `/gd`; it is speculative and would need
the user's explicit opt-in.

**C. Haiku 5.5 as the child, Claude Code as the child harness.** Same parent cost as A (gruntly's blocking call, not the
Agent tool, which measured 7 to 11 parent calls), $0.005 child, 14 of 15 correct, 17 s instead of 74 to 158 s, no rate
limits, no proxy. Costs a `claude` adapter (`claude -p --model haiku` in the worktree, with gruntly's gates and holdouts
around it). Loses the local, private, off-meter story: sub-agent and `-p` usage "count toward
the same usage limits as your main conversation" (Claude Code docs). On a Max plan where the limit binds, the free child
is the real advantage of the current concept; the weighting of Haiku against the limit is not documented.

**D. gruntly outside the session, Claude only as reviewer.** The user runs `gruntly do 'fix X'` in a terminal; the child
works, the gates run, one Sonnet review approves ($0.007). About $0.007 per task against $0.14 to $0.64 for the same work in
the session. It is the cheapest point on the frontier by an order of magnitude, and a different product: Claude Code stops
being the parent for mechanical tasks.

**E. Supervised runs (built this week).** Derived: $0.01 to $0.02 more per task than A, and 15 to 40 minutes with Laguna.
Keep it for large tasks where a plan review earns its cost; move the rules, CLAUDE.md, task and plan into the reviewer's
system prompt so the 1-hour cache serves them (break-even at two reviews; today each review re-sends them at $2/M).

**F. Read-only delegation (the scout plan).** Tool results are at most a third of the user's context growth, the model's
own previous output is more, and Claude Code already ships read-only sub-agents on a cheap model for exactly this.
Cognition's follow-up post says read-only sub-agents are the multi-agent pattern that works. gruntly adds nothing here;
do not build it.

**G. Stop.** Right if the goal were dollars on fresh-session small tasks: Haiku alone wins at $0.005 and no delegation beats
it. Wrong for the prompts that cost the user money.

## 7. Repo improvements, with evidence

1. **Remove `plugin/.mcp.json`.** It launches `uvx --from "gruntly[mcp] @ git+https://github.com/usegruntly/Gruntly@v0.3.0"`:
   a server pinned to a two-week-old tag of a private repository. For anyone but the owner it fails at session start; for
   the owner it exposes the old spec-only `gruntly_run` next to the skill's plain-words flow (an old copy is running in this
   very session). The skill plus Bash is the path; the MCP server stays for non-Claude agents, started by hand.
2. **`gd.md`: `--max-block 540`.** Otherwise the one-turn path becomes a two-turn path for every child slower than 100 s.
3. **Holdout in the same call.** `gruntly agent-run --holdout 'pytest tests/holdout_x.py' --holdout-file tests/holdout_x.py
   <<EOF ... EOF`, or a `tests/holdout_*.py` the parent writes with its Write tool in the same turn as the call. Addresses the
   false pass directly, at output-token prices.
4. **A `claude` child harness** (design C), so the child choice is a config line and the benchmark can compare children on
   equal footing.
5. **Reviewer caching.** Stable context into `--system-prompt`, step into the user message (design E).
6. **A false-pass flag the parent can act on.** When the acceptance was the whole existing suite and the child added its own
   tests, the block already says so; make it the first line, not a flag in the middle.
7. **Wall time.** Laguna: 38 to 158 s on one-function tasks, 2 to 13 minutes per supervised step; 31 to 45 model requests
   per step. Parallel parts are done; the remaining lever is a faster child (Haiku) or a faster endpoint.
8. **The benchmark.** Report marginal cost after the $0.045 floor, not session totals; add the deep-session arm (section 9);
   add tasks of 8 or more alone-turns; keep hidden tests; stop drawing conclusions from n=1 arms.
9. **Weight of the code.** 5,811 lines in `src/gruntly`: 1,048 (18%) face the parent, 2,016 orchestrate and check, 1,177
   drive child harnesses, providers and the proxy, 1,570 are onboarding, live view and CLI plumbing; plus 413 in the plugin
   and 2,631 in tests. Most of the engineering went into child-side features whose tokens are free; the cost lever (parent
   turns and parent context) became the design target only yesterday. A reconstruction would start from "two parent turns,
   no parent context growth, one strong check" and treat everything child-side as pluggable.
10. **Per-turn tax of the plugin** (estimates at 4 chars per token): skill description about 128 tokens always loaded, mode
    hint about 128 tokens when mode is on, result block 190 to 220 tokens plus a diff of up to about 900. All acceptable;
    the MCP schemas (about 400 tokens of docstrings plus schema) are deferred by this Claude Code build and cost little, but
    see item 1.
11. **Not gruntly's, but the user's biggest lever:** the $25.63 of cache re-writes (idle gaps over an hour, model switches
    mid-session) and the 781 turns run above 300k of context at $0.076 each. `/compact`, `/clear` between tasks, and not
    switching models inside a 600k-token session would save more than any delegation design in this document.

## 8. What the literature says, and how it bears on this

- **Minions / MinionS** ([arXiv 2502.15964](https://arxiv.org/abs/2502.15964), ICML 2025): a local model reads the long
  context, the cloud model never does; 5.7x lower remote cost at 97.9% of remote quality, on financial, medical and
  scientific document QA. No code-editing task. The saving comes from keeping the long input off the paid model, which is
  the same lever as keeping file reads and tool steps out of the parent's context; the setting is reading, not editing.
- **SWE-Pruner** ([arXiv 2601.16746](https://arxiv.org/abs/2601.16746)): in a mini-SWE-agent run with Claude Sonnet 4.5, read
  operations were 76.1% of token spend; line-level pruning cut tokens 23 to 54%. In the user's own sessions reads are a
  smaller share (at most a third) because the harness truncates and the model's own re-sent output dominates; the lever
  exists but is smaller here.
- **Speculative Uncertainty** ([arXiv 2609.05274](https://arxiv.org/abs/2609.05274)): a small draft model gates a black-box
  coding agent's actions before execution; 14 to 19% fewer tokens, 6 to 8 points fewer execution errors. A cheap model as a
  *gate* that can only stop work, which is the role proposed for Haiku in the supervised design.
- **RLM-Cascade** ([arXiv 2606.22840](https://arxiv.org/abs/2606.22840)): a proxy where a cheap draft answers Claude Code
  requests and a strong model verifies or is bypassed; the authors report −45.8% API cost on 125 production requests with an
  88.8% draft rate. Small sample, authors' own numbers, but it is the closest published design to "cheap model works, strong
  model decides" on Claude Code traffic.
- **Anthropic's advisor tool** ([docs](https://platform.claude.com/docs/en/agents-and-tools/tool-use/advisor-tool)): a cheaper
  executor consults a stronger advisor that reads the full transcript; Anthropic says a Sonnet executor with an Opus advisor
  "keeps total cost similar or lower" on coding tasks when it reduces tool calls, and a Haiku executor with an Opus advisor
  costs more than Haiku alone but less than a larger executor. The vendor's own evidence that the cheap-executor pattern
  works, with the strong model paid per consultation.
- **Aider architect/editor** ([post](https://aider.chat/2024/09/26/architect.html), [leaderboard](https://aider.chat/docs/leaderboards/)):
  o3-high + GPT-4.1 scored 78.2% at $17.55 against o3-high alone 81.3% at $21.23; DeepSeek R1 + Sonnet cost more than R1
  alone. Splitting reasoning from editing is a quality tool first; its cost effect depends on the pair and is not always a
  saving.
- **Anthropic on context** ([effective context engineering](https://www.anthropic.com/engineering/effective-context-engineering-for-ai-agents),
  [costs](https://code.claude.com/docs/en/costs), [sub-agents](https://code.claude.com/docs/en/sub-agents)): sub-agents
  "explore extensively, using tens of thousands of tokens" and return "1,000-2,000 tokens"; tool-result clearing is "one of
  the safest" forms of compaction; "token costs scale with context size"; sub-agents can run on `haiku` and count toward the
  same usage limits; the average enterprise developer costs about $13 per active day. gruntly's two-turn path is the same
  shape as a sub-agent call with a stricter return format and deterministic gates.
- **Multi-agent cost** ([Anthropic guide](https://claude.com/resources/articles/building-multi-agent-systems-when-and-how-to-use-them),
  [Cognition](https://cognition.ai/blog/dont-build-multi-agents), [MAST, arXiv 2503.13657](https://arxiv.org/abs/2503.13657)):
  multi-agent designs use 3 to 10 times the tokens of a single agent; failures come mostly from specification and
  coordination; read-only sub-agents are what works in production. Supports keeping one writer, one call, deterministic
  checks, and moving tokens to a cheaper model rather than adding agents.
- **Verification** ([self-correction limits, arXiv 2310.01798](https://arxiv.org/abs/2310.01798),
  [LLM-as-a-judge, arXiv 2306.05685](https://arxiv.org/abs/2306.05685), [CriticGPT, arXiv 2407.00215](https://arxiv.org/abs/2407.00215),
  [weak-to-strong, arXiv 2312.09390](https://arxiv.org/abs/2312.09390), [CodeT](https://arxiv.org/abs/2207.10397),
  [LEVER](https://arxiv.org/abs/2302.08468), [TDD with GPT-4](https://arxiv.org/abs/2402.13521)): models do not reliably
  correct themselves without external feedback; strong judges reach about 80% agreement with humans and carry known biases;
  trained critics catch bugs humans miss but also hallucinate bugs; tests given first improve generated code. Together:
  deterministic tests first, one strong review second, never a weak model approving.
- **Cascades and routers** ([FrugalGPT](https://arxiv.org/abs/2305.05176), [RouteLLM](https://arxiv.org/abs/2406.18665),
  [AutoMix](https://arxiv.org/abs/2310.12963)): 2x to much larger savings on single-query benchmarks with a learned scorer
  or router; none evaluated on multi-turn coding agents. The score-based approval idea was rejected for the reasons given
  in `docs/research-brief.md`.
- **Small models for agents** ([arXiv 2506.02153](https://arxiv.org/abs/2506.02153), a position paper): argues most agentic
  calls can go to models under 10B. Today's data is consistent for the typing step (Laguna 13 of 14, Haiku 14 of 15) and
  not for the specifying step (planner 0 of 3; the 4B model failed 7-part briefs outright).
- **Cost of real tasks** ([Agentless, arXiv 2407.01489](https://arxiv.org/abs/2407.01489), [vals.ai](https://www.vals.ai/benchmarks/swebench)):
  $0.34 to $1.24 per real issue, which is the scale on which a delegation saving is visible.

## 9. What would change the verdict, and the next experiment

**It becomes "no" if** an end-to-end deep-session run shows the parent taking more than 2 turns on average (takeovers,
follow-ups, re-reads), or the child's false-pass rate stays near today's 1 in 5 without a holdout, or the wall time makes the
user intervene. **It becomes a clear "yes" if** the deep-session run reproduces the modelled 35 to 67%.

**Deep-session benchmark (about $3.50, needs approval):** one repository that contains all task folders; two sessions
(alone and delegated), each primed once by reading about 150k tokens of files (one turn, about $0.60 per session); then the
ten tasks sent in the same order to each session with `claude -p --resume`, within the 1-hour cache window, hidden tests
run after every task; metrics: cost per prompt, parent turns, context growth, hidden-test pass. The context grows across
tasks in both arms, as in real use. Delegated arm: the one-call flow with a parent-written holdout; child Laguna via Hermes,
and the same ten tasks again with the Haiku child for the cheapest honest comparison (another $1.20).

**Quality at scale:** 20 runs per arm on tasks of 8 or more alone-turns, built from real repositories, before any claim
about parity.

## 10. Spend, files, provenance

- New spend today: Haiku alone 15 runs $0.075; Sonnet one-call flow 5 runs $0.28; Sonnet with Haiku sub-agent 4 runs
  $0.29; reviewer probes earlier today about $0.08; seven web-fetch sub-agents (about 195k tokens, model unrecorded).
  About $0.72 in total, under the $1 the protocol allowed.
- Scripts: `bench/cost_model.py` (the model), the billing fit, real-session aggregates and the thinking-resend regression are
  in the session scratchpad; the results are in `docs/benchmarks/benchmark-haiku-alone.*`, `benchmark-forced-oneflow.*`,
  `benchmark-subagent.*`. `bench/run_bench.py` gained `--runs-dir` and the `subagent` arm.
- The user's session files were read for aggregate token counts only; no content was copied.
