# Investigation protocol: can gruntly ever be cheaper than Claude alone?

Written 2026-11-11 before the investigation, so that the result cannot be shaped by what I hoped to find.

## The question
Can a system where a paid parent agent (Claude Code) hands coding work to a cheap child agent be **cheaper than the parent
working alone, at the same quality**? If yes: under which conditions, with which design, and by how much. If no: show why
the floor is where it is, so the user can stop.

## Rules I hold myself to
1. **Measure before believing.** Every number is labelled *measured* (from a transcript or a run), *derived* (computed from
   measured numbers by a stated formula) or *estimate* (my reasoning). Earlier claims in this project count as estimates
   until re-derived from data here.
2. **Price what is actually billed.** Fit Claude Code's own `total_cost_usd` against the token kinds it reports, instead
   of assuming list prices and cache multipliers.
3. **Separate the regimes.** A fresh `claude -p` session and a long interactive session cost very differently per turn.
   Report both, and say which one the user's real sessions are in, from the user's own transcripts (aggregate numbers only,
   no content).
4. **Separate the bills.** Parent session cost, out-of-session reviewer cost, child cost (free or priced as a what-if), and
   wall time are four different numbers. Never net them silently.
5. **Count turns.** The parent's cost is turns times context. For every path (agent-run, /gd, supervised, MCP, subagent)
   count the minimum parent turns, the measured parent turns, and why they differ.
6. **Quality is hidden tests**, never "the gates passed". Report pass rates with the sample size next to them.
7. **Look for the disconfirming case.** For every design that looks good, find the condition under which it loses, and
   check whether that condition is the common one.
8. **Alternatives on equal footing.** Compare the current concept against: a Claude Code sub-agent on a cheap model; gruntly
   as the primary interface with Claude only reviewing; read-only delegation; a deterministic patcher; and stopping.
9. **Spend little without asking.** New measurements under about $1 in total; propose anything larger with its cost.
10. **Say what would change my mind**, and state confidence.

## Steps, in order
1. **Billing model.** From every `claude -p` transcript in `bench/runs/` (per-message usage plus Claude Code's own total):
   fit effective prices for fresh input, cache write (5-minute and 1-hour), cache read and output. Decompose a turn's cost.
2. **Real usage.** From the user's own Claude Code session files: context size per turn, cost per turn at that size, the
   share of context that is tool output (file reads, searches, command output), turns per user message. This fixes the
   regime that matters.
3. **Repo audit.** Read every module. List every token gruntly adds to the parent's context on every turn (skill
   description, mode hint, MCP schemas) and per use (result blocks, errors). List the parent turns each path needs. List
   child-side waste (retries, prompts, wall time, idle kills) and code-level problems.
4. **Economic model.** Cost(alone) and cost(delegated) as functions of context size, turns, review cost and carried
   context, with the fitted prices. Validate it against the measured benchmarks (it must reproduce +4%, +45%, +28%). Then
   predict the deep-session regime and the break-even surface.
5. **Fill the gaps cheaply.** (a) The cheapest in-harness child: Haiku 5.5 alone in Claude Code on the same tasks, cost and
   hidden-test pass rate. (b) The parent's turn count with the current one-call flow, on a few tasks. (c) The one-turn
   `/gd` path from existing transcripts. (d) Deep-session per-turn cost from real transcripts, not a new experiment.
6. **Literature**, with primary sources, on: strong/weak cascades and routing for agent tasks; local/cloud collaboration
   (Minions); architect/editor splits (Aider); advisor/executor APIs; verification without a strong judge and the limits of
   self-correction; weak-to-strong oversight; decomposition for small models; context economics of agent loops; sub-agents;
   production write-ups; the pricing and usage-limit facts the model depends on.
7. **Designs and verdict.** For each alternative: expected cost by regime, quality risk, build effort, and the condition
   under which it loses. Then the verdict, its confidence, the experiment that would settle what is still open, and its cost.

## Output
`docs/investigation-2026-11-11.md`: findings with sources, the model with its parameters, the designs, the verdict.
