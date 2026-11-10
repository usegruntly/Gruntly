# gruntly: what we tried, what it cost, and what to research next

A self-contained brief for a research session. It records every way we have tried to make a paid "parent" coding agent
(Claude) cheaper by handing work to a cheaper "child" agent, the measured costs and quality, what failed and why, and the
open questions. The last section is the research task.

Everything marked **measured** comes from benchmark runs whose rows are in `docs/benchmarks/` of the gruntly repository.
Everything marked **estimate** is reasoning, not measurement. Samples are small (often 1 to 3 runs per cell); treat single
numbers as indications, not facts.

---

## 1. Instructions for the research session

You are helping the author of gruntly decide where to go next. Read the whole brief first. Then:

1. **Do deep research** (papers, technical reports, credible blog posts, open-source tools) on the questions in section 9.
   For each source, say what it found, how it relates to the numbers here, and whether its setting matches ours
   (an interactive coding agent whose cost is dominated by re-reading its own context each turn).
2. **Verify every paper or tool named in this brief** before relying on it. The names were written from memory and some
   details may be wrong. Prefer primary sources (arXiv, ACL/NeurIPS/ICLR proceedings, official docs).
3. **Propose concrete experiments**, each with a hypothesis, the arms to compare, the metric, the sample size needed to
   tell a real effect from noise, and a cost estimate using the prices in section 3.
4. **Say plainly where the idea cannot win** if the evidence points that way. A negative answer is useful.
5. Output: a ranked list of directions (most promising first) with the evidence for each, a reading list with one-line
   summaries, and the experiment plan.

---

## 2. What gruntly is

- A Python CLI plus a Claude Code plugin. The **parent** (Claude Code, usually Sonnet) delegates a coding task. gruntly
  runs a **child** coding agent in an isolated git worktree, checks the result with **gates**, retries, and returns a
  compact result block. The parent's session is billed; the child is meant to be free or cheap.
- **Child harnesses** (the agent program around the small model): OpenCode, Qwen Code, Hermes Agent (Nous Research), or
  any CLI. Since 2026-11-10 every harness runs **as shipped** (its own system prompt and tools); gruntly adds only a short
  task message (which files may change, the test command, no git, "make real tool calls").
- **Child models tried**:
  - Qwen3.5-9B, local, via LM Studio (32k context).
  - NVIDIA `nemotron-3.5-bolt-e4b`, hosted, free tier, about 4B.
  - Poolside `laguna-xs-2.1`, hosted on NVIDIA, a 33B mixture of experts built for agentic coding.

  Hosted models go through a local proxy in gruntly that holds the API key, paces requests (rate limits) and retries
  errors.
- **Gates** (deterministic checks, free): the tests pass (acceptance), only allowed files changed (scope), diff size,
  no weakened or deleted tests, no new dependencies; optional **holdout** tests the child never sees.
- **Benchmark harness** (`bench/run_bench.py`): runs `claude -p` (Sonnet) on a copy of a task repo in several **arms**,
  records Claude Code's own `total_cost_usd` for the whole session (takeovers after a failed delegation included), then
  judges correctness with **hidden tests**. `bench/cost_report.py` pairs each arm with its baseline by task and repetition.

---

## 3. The cost model (the most important section)

**Prices** (Anthropic list, $ per million tokens):

| Model | Input | Output | Cache read | Cache write |
|---|---|---|---|---|
| Sonnet 5.5 | 2.00 | 10.00 | 0.20 | 2.50 (5 min) |
| Haiku 5.5 | 0.10 | 0.50 | | |

- Claude Code writes its prompt cache with a 1-hour lifetime, which we observed to be billed at about 2x input.
- The user is on a Claude subscription, so "dollars" here stand for usage-limit consumption. We hit the 5-hour usage
  limit once during a benchmark.

**Measured shape of a Claude Code session** (fresh session, Sonnet, per-turn split from transcripts):
- The fixed context (system prompt, tool schemas, skill list) is **about 25k tokens** and is re-read on every turn.
- **Turn 1** costs about **$0.030**: about 11k tokens are written to cache, and about 14.5k are already cached and read.
- **Each later turn** costs **$0.007 to $0.010**: about 25k to 30k cached tokens read, plus the new tokens of that turn.
- **Claude's own output is tiny**: 170 to 250 tokens per task, about $0.002. Writing code is almost free for the parent.
- So **parent cost is roughly the number of turns times the context size**. Delegation only saves money if it removes
  parent turns, or keeps large file contents out of the parent's context, more than it adds.
- **Estimate:** in a deeper session (100k context) a turn costs about $0.02, three to five times more, so the same
  avoided turns are worth more there. Our benchmarks all start from a fresh session, which is the worst case for delegation.

---

## 4. Timeline of approaches, with results

### A. Parent writes a full spec; child implements (2026-11-07 and earlier)
- **How:** the parent writes a YAML spec: brief, allowed paths, acceptance command, optional holdout tests. The child
  implements it; gruntly gates it.
- **Result (measured, older benchmark v2):** no saving on tasks the parent finishes in 3 to 5 turns; near parity on clean
  runs. Writing the spec and reading the result cost about as much as doing the work.

### B. Slim child profiles (2026-11-07; removed 2026-11-10)
- **How:** the harness's own system prompt and tool set were replaced with a minimal one. "typist" was a short prompt
  with the target files inlined and file-writing tools only; "worker" also had list, search and read tools.
- **Result (measured, child-only benchmark, Qwen3.5-9B, 16 runs per arm, precise briefs):**

  | Profile | Child input tokens per request | Child tokens per run | Wall time | Hidden-test pass |
  |---|---|---|---|---|
  | Default (harness as shipped) | 12,991 | 132k | 161 s | 62% |
  | Typist | 2,886 | 40k | 91 s | 69% |
  | Worker | 4,317 | 37k | 106 s | 69% |

- **Why removed:** a user decision. Slimming saves only free child tokens and hides what each harness is good at. The
  cost that matters is the parent's.

### C. "Lean" parent (2026-11-08)
- **How:** Claude was started with a one-paragraph system prompt and a single Bash tool, about 3k base tokens instead of
  about 25k, and directed the child with `gruntly agent-run 'plain words'`.
- **Result (measured):** about 45 to 75% cheaper than a normal Claude Code session working alone, with wall time of 100
  to 540 s against about 17 s.
- **Later, with a matched baseline** (the same lean Claude doing the task itself, no gruntly), nemotron child, 2 tasks:
  lean alone cost **$0.015** per run, lean with gruntly **$0.046** (+212%, 1 of 2 correct). Normal Claude alone cost
  $0.062.
- **So the saving came from the lean setup, not from delegating.** A user cannot easily run Claude Code this way.

### D. Normal Claude Code, plugin installed, Claude decides ("policy" arm)
- **Measured, 10 small tasks, 20 runs:** Claude **never delegated** (0 of 20 distinct runs, across both child setups). Cost was
  **+4%** over alone ($0.0641 vs $0.0619), the price of the skill text sitting in its context.

### E. Claude told to delegate, old spec flow ("forced" arm), Hermes + Laguna child
- **Measured, 10 small tasks:** **+45%** ($0.0896 vs $0.0619), 0 of 10 pairs cheaper, 7.5 turns vs 4.7.
- **Cause, from transcripts:** the prompt pointed at the old spec flow. Claude guessed flags, failed, read `--help` and the
  manual, and wrote YAML: 2 to 3 wasted turns per task.
- **The child itself was fine:** Laguna passed 9 of 9 delegated tasks on the first attempt.

### F. One plain-words entry point everywhere (`agent-run`)
- **Changes:**
  - The skill, the manual, the CLAUDE.md snippet and MCP all teach `gruntly agent-run 'request'`.
  - The skill's always-loaded description carries the call, so no skill-load turn is needed.
  - The result block shows real code before test files and says "nothing to open or rerun".
  - Split parts of a request run in parallel.
- **Measured, 3 larger tasks:** **+28%** ($0.0901 vs $0.0701), 7.3 turns vs 4.3, wall time 159 to 775 s vs 15 to 21 s.
  The remaining turns went to a skill load, a `git diff` (the diff in the block had been cut off by the child's test
  file), and takeovers when a run failed.
- **Finding:** Sonnet finishes even these "larger" tasks alone in 4 to 5 turns for 6 to 8 cents, which leaves almost
  nothing to save.

### G. Parent researches everything and gives exact edits (a real website task, run by the user)
- **How:** Claude did the audit and wrote the exact design as OLD/NEW text pairs; the child (nemotron, about 4B) only
  typed the edits.
- **Measured:**
  - 10 gruntly calls, 1,100 s of child time, about 1.58M child tokens.
  - 3 of 7 fresh runs correct. **0 of 3 follow-ups helped**: each follow-up on the same child session made things worse.
  - Correct runs had 2 to 8 exact edits, the worker profile, and whitespace taken out of the job.
- **Lesson:** once the parent writes the exact edits, a deterministic patcher would do the child's job for free. And the
  parent had already paid for the thinking.

### H. Parent plans, child explores and implements ("planner" arm, `agent-run --explore`)
- **How:** Claude does not read code. It writes a plan of intents, and each step goes to a child that finds the code itself.
- **Measured, 3 tasks with intent-only briefs:**
  - Claude alone: 2/3 correct, $0.0736, 5.3 turns, 118k parent tokens.
  - Planner: **0/3 correct**, $0.0751, 3.3 turns, 92k parent tokens (-22% tokens, but more output).
- **Why it failed:**
  - The child missed requirements the brief left unsaid (edge cases checked by hidden tests).
  - A vague brief failed both arms.
  - One failure was a gruntly bug: explore mode blocked test edits on a rename that must touch tests. Since fixed.
- **Signal:** Claude caught a gap from the diff alone, without reading code.

### I. Child plans, parent's model reviews every step outside the parent's session (`--supervised`, current)
- **Design (the user's):** small models are bad at long plans and do not know when they are wrong. So:
  1. A child explores and drafts a plan of at most 6 steps.
  2. A **reviewer** approves or rewrites the plan. The reviewer is the parent's model, called with `claude -p`, no tools,
     about 1.1k tokens of base context.
  3. A **fresh child** does each step.
  4. The reviewer judges each step from its diff and the child's own report (files read, checks run, assumptions) and
     replies APPROVE, FIX (exactly what was missed) or STOP. At most 2 fixes per step.
  5. The parent's session makes one call and gets one block back.
- **Reviewer context:** the person's rules (`.gruntly/rules.md`, kept by Claude from what the user said in chat) and the
  project's CLAUDE.md and AGENTS.md (followed through `@` imports, capped at about 8k tokens), plus the task, the plan
  and the step.
- **Problems found in real runs, all fixed:**
  - Plans contained read-only steps.
  - A silent Hermes child (no output while thinking) was killed as idle although it was calling its model; model
    requests now count as progress.
  - The reviewer contradicted itself between attempts; it now sees its own earlier feedback.
  - The reviewer made the child undo correct extra work; correct extra work is now kept.
  - A step with nothing left to do looped; the reviewer is now shown the current files.
- **Measured reviewer cost, Sonnet at default effort:** about **$0.011 to $0.015 per review**. One bugs_batch run used 7
  reviews ($0.093) before finishing, more than Claude alone spends on the whole task ($0.075).
- **No full benchmark result yet.** The run was stopped to fix the cost first.

### J. Cheaper reviewers (measured 2026-11-10)
- **Setup:** six realistic step reviews: five planted bugs (off-by-one slice, dropped apostrophes, mutating the caller's
  list, lost last chunk, shrinking interval merge) and one correct change.

  | Reviewer | Right | Cost per review |
  |---|---|---|
  | Sonnet, default effort, caching on | 1/1 tested | $0.011 |
  | Sonnet, low effort | 6/6 | ~$0.010 (cache write) or $0.0072 (caching off) |
  | Sonnet, medium effort, caching off | 1/1 | $0.0077 |
  | Haiku 5.5, low | 6/6 | ~$0.0007 |
  | Haiku 5.5, default | 6/6 | ~$0.0005 |

- **About 70% of a Sonnet review's cost** was the 1-hour cache write of a prompt that is never reused.
- **Committed default right now:** Haiku reviews each step, Sonnet at low effort reviews the plan.
- **The user objects**, and we agree: if Haiku approves, the system's quality ceiling falls toward the small models'.
  The probe only tests whether a reviewer notices a planted local bug, not judgment (cross-file effects, unstated
  requirements, design).

### K. Proposed next, not built: "a weaker model may reject, only the parent-grade model may approve"
- **Design:**
  - Haiku pre-checks each step but can only send it back (FIX).
  - Sonnet (caching off, medium effort) approves the plan, and approves the **whole combined diff** at the end, naming
    which part to redo.
  - Nothing reaches the parent as "passed" without Sonnet's approval.
- **Estimate per small task, fresh session:**
  - Parent session (call and reply): about $0.045.
  - Sonnet plan and final review: about $0.02 to $0.03.
  - Haiku pre-checks: about $0.005.
  - **Total about $0.07 to $0.08, which is parity with Claude alone ($0.06 to $0.09), not a saving.** The expected win
    is in deep sessions and bigger tasks.
- **Rejected idea:** a "decision" or reward model that outputs a confidence score and auto-approves above a threshold.
  The reasons:
  - The failures that matter are confidently wrong (plausible code that passes tests but misses something).
  - Scores are not calibrated to "correct for this task in this repo".
  - A score cannot tell the child what to fix.
  - It would save only a cent or two per task.

---

## 5. Child model and harness findings

| Child | Result |
|---|---|
| Nemotron-bolt (about 4B, hosted) | About 56% pass over 18 runs, 1.5 attempts on average, rated "avoid" by gruntly's stats |
| Laguna-xs-2.1 (33B MoE) | 9 of 9 first-attempt passes on small tasks |
| Qwen3.5-9B (local) | 94% passed gruntly's own checks over 18 runs at 32k context (checks, not hidden tests); 62 to 69% hidden-test pass in the child-only benchmark |

- **Nemotron-bolt** narrates tool calls in text instead of making them ("[runs bash ...]"), and with 7-part briefs
  fails outright.
- **Retries happen inside gruntly** and cost the parent nothing, but a failed run costs the parent 1 to 4 turns of
  takeover.
- **Fresh children beat follow-ups on the same session.** Follow-ups compounded errors: one line pasted 6 times,
  "fix indentation" turned into duplicate inserts.
- **Small children miss unstated requirements** and do not know when they are wrong. Hidden-test failures came from edge
  cases the visible tests did not pin.
- **Hermes** prints nothing in quiet mode (no tool trace, no token counts). Native Windows Hermes 0.23 needs a
  short-path data folder.
- **Wall time** is the child's weak spot: 1 to 13 minutes per step with Laguna, against seconds for Claude alone.

---

## 6. Failure catalogue (things that cost money or quality)

1. **Wrong or unclear entry point:** the parent guesses flags, reads manuals, writes YAML (2 to 3 turns).
2. **A skill-load turn before every delegation.**
3. **A result block the parent does not trust:** a cut-off diff, or a "weak test" flag, leads to re-reading files.
4. **Takeover after a failed delegation:** the parent pays for the attempt and the work.
5. **Sequential parts running out of time**, so the parent finishes the rest.
6. **Scope gate false positives:** a rename that must touch tests, `.gruntly/` files visible to git.
7. **Planner bugs:** a test that only imports the target was missed, so the child was told "no test covers this" and wrote
   its own tests.
8. **Reviewer inconsistency, over-strictness, and looping on "no change".**
9. **Vague briefs:** both Claude and the child failed "where it makes sense".
10. **Process hygiene:** orphan processes after a stopped benchmark. In one cleanup we killed an unrelated user process by
    a loose name match.

---

## 7. What we currently believe

- **Fresh sessions:** on tasks Sonnet finishes in about 4 turns, no delegation setup has been cheaper than Claude alone.
  The parent's minimum delegation cost (about 2 turns, about $0.045) is already most of Claude-alone's cost
  ($0.06 to $0.09).
- **Where it could win:** (a) deep sessions, where each avoided turn costs 3 to 5x more and file contents stay in context
  forever; (b) tasks Claude alone needs 10+ turns for; (c) output-heavy work (writing hundreds of lines); (d) many
  independent edits collapsed into one call. **None of these has been measured yet.**
- **Quality** is decided by whoever approves. Deterministic gates are free and never confidently wrong; LLM review is
  needed for unstated requirements. Small children do the typing well when the target is clear.

---

## 8. Data and code to reproduce

- **Result rows and summaries:**
  - Benchmarks: `docs/benchmarks/benchmark-cost*.json/.md`, `benchmark-planner-smoke*`, `child-bench*`,
    `benchmark-lean*`.
  - Earlier narrative: `docs/lean-long-tasks.md`.
  - Decisions: `docs/decisions.md`.
- **Scripts:** `bench/run_bench.py` (arms: alone, policy, forced, planner, supervised, lean, lean_alone; `--vague`
  briefs; `--provider`), `bench/cost_report.py` (paired comparison, bootstrap interval, the child priced at Sonnet or
  Haiku input as a what-if), `bench/make_xl_tasks.py` (two larger tasks with hidden tests).
- **Tasks:**
  - 10 small tasks (each 1 function).
  - 3 "larger" tasks (6 bugs; a 15-file rename; a CLI feature).
  - 2 new larger tasks (a feature across model, store, service and CLI; environment-variable reads moved into one typed
    Settings).
  - All tasks are synthetic and small. The real target is the user's own repositories.

---

## 9. Research questions

1. **Cascades and routing for agents.** What does the literature say about strong/weak model cascades and routers when the
   unit is a multi-turn agent task, not a single query? Look at FrugalGPT (Chen, Zaharia, Zou, 2023), RouteLLM (Ong et
   al., 2024), AutoMix (Madaan et al., 2023), "Language Model Cascades" (Dohan et al., 2022), and anything newer. Do any
   report wins on coding agents, and what conditions made them win?
2. **Local/cloud collaboration.** The Minions / MinionS work (Narayan et al., Hazy Research, 2025) splits work between an
   on-device model and a cloud model to cut cloud cost. What protocol did they use, what did they save, and does it
   transfer to code changes rather than reading tasks?
3. **Architect/editor splits in coding tools.** Aider's architect/editor mode (a strong model plans, a cheaper model
   edits) and similar features: measured cost and quality? How do they keep the strong model's context small?
4. **Advisor and executor patterns.** Anthropic's API has an "advisor" tool where a cheaper executor model consults a
   stronger advisor. How does it work, what does it cost, and is it a better fit than our out-of-session reviewer?
5. **Verification without a strong judge.**
   - Self-correction limits: "Large Language Models Cannot Self-Correct Reasoning Yet" (Huang et al., 2023); Self-Refine;
     Reflexion; Self-Debug.
   - Test-based selection: CodeT, AlphaCodium.
   - LLM-as-a-judge reliability and calibration (Zheng et al., 2023) and its known biases.
   - What is the best cheap verifier for "this diff does the task", and where do weak judges fail?
6. **Weak-to-strong and scalable oversight** (Burns et al., 2023, and follow-ups): does it say anything about a weaker
   model supervising or filtering a stronger one's work, or the reverse?
7. **Task decomposition for small models.** Plan-and-Solve, ADaPT (as-needed decomposition), and multi-agent coding
   frameworks (MetaGPT, ChatDev, SWE-agent, OpenHands/CodeAct, Agentless). Which decomposition granularity lets small
   models succeed, and who should write the plan?
8. **Context economics of agent loops.**
   - Work on reducing per-turn cost: context pruning, summarisation, keeping tool outputs out of context, sub-agents
     with separate contexts.
   - Is "fewer parent turns" the right objective, or is "smaller parent context" better?
   - How do Claude Code sub-agents compare with an external child agent here?
9. **Benchmarks.** Which benchmark would show the regimes where delegation should win (long sessions, 10+ turn tasks)?
   SWE-bench Verified or Lite subsets, long-horizon or repository-level benchmarks. How to build a "deep session" arm
   (the parent starts with about 100k tokens of prior context) fairly?
10. **Anything else** that tackles "a cheap agent does the work, an expensive agent decides when it is right", including
    production write-ups from coding-agent companies, if credible.

**Constraints to respect in recommendations:**
- The parent must stay any agent (Claude now, others later through MCP).
- The child must run through its own harness, as shipped.
- Quality must not fall toward the small model's level.
- The user values honesty over a positive result.
