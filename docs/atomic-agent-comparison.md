# What atomic-agent does differently (read 2026-11-11)

Source: a full clone of [AtomicBot-ai/atomic-agent](https://github.com/AtomicBot-ai/atomic-agent) at commit `1b4e641`
(2026-11-10, version 0.7.0, 3,312 TypeScript files), read in an isolated folder; nothing in it was run. File paths below are
theirs. Every claim about what it does is from the code or its own docs; every number about gruntly is from
`docs/investigation-2026-11-11.md`.

## 1. The "5x cheaper" claim is not in their repo or on their site

I searched the README, every Markdown file, the TypeScript comments, the JSON, and their website (home page, compare
pages, blog index). There is no "5x cheaper", "five times", or any cost-per-task comparison with Claude Code, Cursor,
Hermes or a cloud-only run. What they do claim, with evidence:

| Claim | Where | Basis |
|---|---|---|
| GAIA Level 1: 69.8% vs Hermes 58.5%, same local `qwen-3.6-35b-a3b`, same 40-step budget, same timeout | README, `eval-agents/docs/GAIA-L1-EXPERIMENT.md` | 53 tasks, deterministic GAIA scorer, raw traces published |
| About 217 s vs 351 s per task (medians), about 8 steps per task | same | same run |
| The same loop on a 9B model: 52.8%; on a 12B: 45.3% | same | different agent versions per row, stated |
| "No API costs with local models", "metered cost stays at zero" | README, site FAQ | not a measurement |
| Memory fabric: "~7-13x fewer tokens" than MemGPT on LoCoMo | `docs/archive/2026-10-06/MEMORY_FABRIC_V2.md` | their memory benchmark, about memory recall, not agent runs |
| TurboQuant KV-cache "up to ~6.4x" less memory than F16 | README | memory, not tokens or dollars |

So whatever "5x cheaper" you saw was either the memory-fabric token figure, a third party's reading, or a statement about
local inference being free. Their cost argument is **local-first ($0 metered), not "cheaper than Claude alone"**; nowhere
do they measure a paid parent's bill, which is the only bill our investigation found to matter.

## 2. Different layer, same problem

- **atomic-agent is a harness.** It owns the agent loop, the prompt, the parser, the tools, the memory, the local
  `llama.cpp` server, and a TUI, built from the start around small quantized local models.
- **gruntly is a delegation layer.** It runs other people's harnesses (OpenCode, Qwen Code, Hermes) as shipped, wraps
  them in a worktree and deterministic gates, and feeds one block back to a paid parent.

Their equivalent of gruntly's parent/child split is **Fusion mode**: "one model plans and hands the independent bulk of a
job (wide reads, drafts, tests) to a pool of workers via `fusion.delegate`, then checks and merges their results. Usually a
cloud orchestrator with local workers." Its stated economics are gruntly's thesis in one line (`src/prompt/fusion-guidance.ts`):
"Fusion's whole economics — cloud tokens for the thinking, local tokens for the bulk". And it can be driven by the user's
Claude subscription: the README lists "your existing Claude Code and OpenAI Codex subscriptions ... driven through their
own signed-in CLIs with no API key" as providers. **That makes it a direct competitor to gruntly's concept, implemented one
level lower**, and in several respects more complete (parallel workers, judge, worktree per task, replanning, budgets).

## 3. What they do that gruntly's child harnesses do not

Grouped by the failures gruntly met this week.

### 3.1 The small model's loop: one inference, a grammar-locked batch of calls
- One inference returns **one JSON array of tool calls**; the core runs them, independent reads in parallel
  (`src/agent/step/step-batch-policy.ts`, `src/agent/dispatch/batch-scheduler.ts`). About 8 inferences per GAIA task.
- On a local server the output is **grammar-constrained (GBNF)** (`grammars/tool-call.gbnf`, `src/llm/grammar/`), so the
  shape is always valid. The grammar has per-tool branches that forbid the exact failures small models produce: an empty
  `{}` for `os.shell.run` ("Nemotron 3.5 Bolt E4B, 23.10.2026" is cited in the grammar comments), an empty `path` for
  reads and writes, a reply that closes its quote on `: "`.
- A model that **narrates tool calls as text instead of making them** is detected and refused
  (`src/llm/reliability/fabricated-tool-transcript.ts`): two such lines in a finished completion fail it; six lines while
  streaming abort the request ("87,228 characters ... 45 fabricated tool-call lines ... $0.129" is the case that motivated it).
- A completion that does not parse gets one bounded repair request, not a retry of the whole step.

This is the nemotron failure gruntly saw twice in the website test ("[runs bash ...]" written as prose, work claimed, nothing
done). gruntly can only add a detector after the fact because the harness owns inference; they fixed it at the sampler.

### 3.2 Context cost for the small model: cache reuse, compression, aging
- **Stable prefix**: persona, rules, tools, skills and instructions are byte-identical within a session, tests pin the
  bytes (`src/prompt/stable-prefix.ts`, `src/prompt/docs/assembly.md`), and every request is sent with
  `cache_prompt: true` to a pinned llama-server slot (`src/llm/slot-manager.ts`, `src/llm/llama-server-client.ts:1662`), so
  the KV cache is reused instead of re-encoding the prompt each step. This is the local equivalent of Anthropic's prompt
  cache, and they treat it as an invariant.
- **Bounded tail**: conversation, memory, world state and loaded skills are clipped into a budget
  (`src/prompt/token-budget.ts`); history is capped by **task count**, not tokens (`agent.conversationMaxPairs`, 200).
- **Tool results are compressed at ingestion** to a signature plus the last 12 lines, 400 characters by default
  (`src/compressor/result-compressor.ts`); the full output is spilled to a session file with its path in the summary.
- **Results age**: a result renders at up to 8,000 characters while its turn is live and **400 once the turn closes**
  (`src/session/conversation-turn.ts:256-302`); a repeated read of unchanged lines becomes a pointer to the earlier one;
  a cut read names the exact `offset` to ask for next instead of sending the model back to re-read.
- **Compaction** at 90% of the window to 65%, extractive fallback without a model call, a smaller kept tail when the
  model has no prefix reuse (`src/runtime/docs/compaction.md`).
- **Compact scaffold** for windows of 64k or less: authored short tool forms, rare tools behind `tool.view`; the default
  prompt drops "from about 9.6k to 3.7k tokens" (`src/prompt/compact-prompt.ts`, `compact-tool-forms.ts`).

Compare Hermes under gruntly: its full prompt and about 18 tool schemas on every request, no compression, 31 to 45
requests and 0.5 to 1.1M tokens per step with Laguna. Free on NVIDIA's tier, but it is why a step took 2 to 13 minutes and
why the idle guard once killed it.

### 3.3 Progress control
- A per-turn **loop detector** keyed on argument hashes, outcome hashes, no-progress streaks, "wandering" across distinct
  queries, read coverage per file version, and repeated test runs (`src/agent/loop-detector.ts`,
  `src/agent/progress/read-coverage.ts`); warnings first, then a veto.
- **Ceilings** on steps, time and money, each ending in a reserved summary step rather than a cut (`src/agent/turn/turn-spend.ts`).
- For an orchestrator, a **review stall** rule: after 6 read-only steps without delegating it is told to choose; after 12
  its tool set is cut to delegate, reply or finish (`src/agent/review-stall.ts`).

gruntly has an idle timeout, an attempt count, and a same-output repeat guard.

### 3.4 Verification
- `verify.syntax` checks files by type and "never reports an unchecked file as passing"; `verify.run` runs a command,
  service or page against a **throwaway copy of the working directory** (`src/tools/verify/`).
- In Fusion, every task carries a **contract**: `checks` (commands), `provides` (symbols or ids that must exist), declared
  files. After the work, "failed checks, missing provides and missing files are red whatever any model says", then an
  optional **judge in a fresh context** reads the files and rules on the rest, and "can only add red: it never turns a
  failed fact green" (`src/tools/fusion/judge.ts`, `contract-checks.ts`). A red list re-runs the task once with the findings.

gruntly's gates (acceptance tests, scope, diff size, test weakening, new dependencies, holdout) are the same philosophy and
stronger on tests; theirs are stronger on structure and on the rule that a model may only add red.

### 3.5 Fusion: their version of parent and child
| | atomic-agent Fusion | gruntly (`--supervised` as built this week) |
|---|---|---|
| Who plans | the orchestrator (usually cloud), "plan in the open, then delegate in the same turn" | the child drafts, a reviewer approves |
| Orchestrator mutating | **refused for the whole turn**: "Read, delegate, reply." A worker that needs more scope is sent out again, "not a takeover" (`src/agent/policies/fusion-orchestrator-mode.ts`) | the parent may take over; measured takeovers were the cost killer |
| Fan-out | one `fusion.delegate` call carries many tasks, run in parallel (up to 16), **all replies return inside that one call** as a compact table | parts run in parallel since yesterday; one block returns |
| Worker context | a fresh throwaway session; sees the operator's request plus its instructions, never the chat; cannot delegate, ask, schedule or write memory | the same: task, plan, its step, rules |
| Worker limits | time limit sized from the brief and the measured tokens/s, reply cap fitted to the time left (`worker-runner.ts`) | 600 s per step, idle guard |
| Checking | contract facts, then a judge that only adds red | gates, then a reviewer |
| Stuck worker | one hint from a stronger model, capped at $0.25 (`escalation: "advisor"`); optional re-run on that model | up to 2 fixes by a fresh child |
| Isolation | optional git worktree per task, three-way merge back, conflicts become merge tasks | one worktree per run |
| Budgets | per-turn USD and time caps, "local tokens count as $0", cache discount applied | none |
| Resume | checkpoint after every task and wave; `/fusion resume` | none |
| Honesty in accounting | local calls shown as "local", unpriced calls never as $0 (`src/session/usage-meter.ts`) | child tokens reported as free |

### 3.6 Evaluation discipline
A small-model release gate (`eval-agents/small-models/`): 16 tasks with deterministic checkers and fixtures generated per
run, pass-rate minimums per model size (4B ≥ 80%, 9B ≥ 90%, 27B ≥ 95% on the core set, 3 repeats), stress tasks for
needles in 32k to 1M-token logs and a multi-turn task that must survive compaction. The GAIA run holds the model, quant,
window, step budget and timeout constant and publishes the traces.

## 4. What is not different, and the caveats
- Their orchestrator still re-reads its own context every step, like any agent; what they did is make the orchestrator's
  turn count small by design (plan and delegate in one turn, results back in the same call, the stall rule) and move the
  bulk to free local workers. That is the same lever our measurements point at: the parent's turns.
- GAIA L1 is question answering with browsing and files, not code editing. There is no coding benchmark against a
  frontier model alone, and no measurement of a Fusion turn's bill against a cloud-only turn.
- Their own plan `docs/plans/cloud-model-adaptation.md` (in Russian) says the small-model constraints hurt large models:
  "a large model gets the same limits even when it can use more information and do longer research", so they are
  building a separate `cloud` model mode with full context, no result aging, and longer review. The compression that
  makes a 9B model work is not what a Sonnet orchestrator wants.
- It is a developer preview (0.7.0), huge (a 1,132-line loop, 20k lines in `src/agent` alone), Node 25, its own
  `llama.cpp` fork. That is the price of being the harness.

## 5. What gruntly should take from it

Mapped to the backlog in `docs/investigation-2026-11-11.md`.

1. **One call, all results inside it.** Their fan-out never returns "running"; everything comes back in the one tool
   result. gruntly's measured advantage over Claude Code's own sub-agent (2 calls against 7 to 11) is exactly this
   shape. Keep it absolute: no `running` block when a long call is allowed, and a compact per-part table like theirs.
2. **The parent never takes over inside a delegated run.** In `--supervised`, adopt their rule: a failed part goes back
   out, the parent only reads, delegates and replies. Takeovers were the largest cost in every losing arm.
3. **A model may only add red.** Gates decide facts; a reviewer can fail a passed step but never pass a failed gate; the
   acceptance list is written before the work. That is the holdout item, with a sharper rule.
4. **Byte-stable reviewer prefix** (backlog item 5): the same invariant they test for, applied to our Sonnet calls.
5. **Fail fast on fabricated work.** A child whose trace shows no edit calls but whose report claims success is failed at
   once, with a notice naming the pattern. gruntly can do this from OpenCode and Qwen traces; Hermes gives no trace.
6. **Account honestly.** Report local or free child tokens as "local", never as a dollar saving, and show the reviewer's
   dollars beside the parent's.
7. **Worker time sized from measured speed, reply caps fitted to time left.** Our fixed 600 s step budget killed
   Laguna mid-work once and wastes time on fast children.
8. **Result aging** is irrelevant for a two-turn parent; it matters only if the parent ever reads several blocks in one
   session, where old blocks could be shortened to a line.

Not takeable: grammar-constrained calls, KV-slot pinning, compaction and the compact scaffold belong to the harness. gruntly
gets them only by using a harness that has them.

## 6. The strategic question this raises

atomic-agent already does, at the harness level, what gruntly set out to do at the plugin level, including driving the
plan from a Claude subscription. Three honest options:

- **Use it as a gruntly child.** `atomic-agent run --cwd <worktree>` with `bypass permissions` mode, AGENTS.md read, verify
  tools, a loop built for 4B to 35B models. It would likely be a better local child than Hermes or OpenCode on small
  models, and gruntly keeps what it adds: the Claude Code session as the parent, the two-turn shape, test gates and
  holdouts, hidden-test benchmarks. This is the cheapest way to get grammar-locked calls and KV reuse into gruntly's child.
- **Compete.** gruntly's edge is being inside Claude Code (skill, mode, live diff, the user's existing session) and its
  test-first gates. Their edge is everything in section 3. On the small-model loop they are years of work ahead.
- **Adopt their Fusion as the product** and make gruntly the Claude Code bridge to it. That gives up the "any child
  harness" principle.

I would try the first: an `atomic` child adapter is a day's work, and the small-model benchmark would say within an
afternoon whether their loop does for Laguna and Qwen 9B what it did for GAIA.
