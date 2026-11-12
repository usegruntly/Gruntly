# gruntly benchmark (v2)

Local child: `claude` / `haiku` at 32k context. Parent: Claude Code (sonnet). Run 2026-11-13. Pass = hidden tests (never shown to the parent or the child) pass afterwards. S = ten small tasks the parent solves in ~4 turns; L = three larger tasks (six bugs, a 15-file rename, a CLI feature); R = real fix commits of public repositories (hidden tests = the fix's own). Arms: `alone`; `forced` (told to delegate through the one-call flow); `policy` (may delegate if the skill's triage rule says so).

## Totals by bucket (means over tasks and repetitions)

| bucket | arm | runs | pass rate | cost $/run | reviewer $ | vs alone | marginal $ (after the $0.045 floor) | vs alone, marginal | cost of a pass $ | turns | takeover edits | session splits | wall s | parent output tok | tool-output KB in context | delegated | child tok |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| L | lean_esc | 10 | 100% | 0.102 | 0.0000 | - | 0.057 | - | 0.102 | 8.4 | 1.2 | 0.0 | 88 | 2285 | 9.3 | 10/10 | 2378258 |

## Escalation A/B (`lean_esc`: a stuck task goes to a full session with the normal system prompt and tools)

Measured inside every run: the hidden tests run after the lean phase (what `lean` alone would have delivered) and again after the escalation, so each run carries both outcomes and both costs. Needless = the run was already passing when it escalated.

| runs | escalated | rescued (fail to pass) | needless | still failed | pass before | pass after | lean phase $ | escalation $ | escalation $ per rescued pass | $ per correct task before | $ per correct task after |
|---|---|---|---|---|---|---|---|---|---|---|---|
| 10 | 5 | 2 | 3 | 0 | 8/10 | 10/10 | $0.470 | $0.553 | $0.277 | $0.059 | $0.102 |

Escalations: cli_json #1 (The first run only added `list`, `show`, `stats` and `users` to `JSON_COMMANDS` in `tool/cli.py`. It added no JSON output code for those commands and no tests. ): not rescued, +$0.134, 5 turns; settings_refactor #1 (The first run only added `Settings` and `load()` to `app/config.py`. The other 7 modules in `app/` still read `APP_*` variables from the environment. The follow): rescued, +$0.112, 20 turns; cli_json #2 (The first run only added `list`, `show`, `stats` and `users` to `JSON_COMMANDS` in `tool/cli.py`. I could not confirm that those commands actually print JSON th): not rescued, +$0.077, 5 turns; inventory_reorder #2 (The first run passed and added the reorder level feature: store, `Inventory.add`, `low_stock()`, and the CLI `add ... [LEVEL]` and `low` commands. The follow-up): not rescued, +$0.118, 4 turns; settings_refactor #2 (The first run only added `Settings` and `load()` to `app/config.py`. The other 7 modules in `app` still read the environment directly. The follow-up run failed ): rescued, +$0.113, 20 turns

## Share of runs that passed within a cost cap (parent + reviewers per run; a run over the cap counts as not solved)

| arm | runs | <= $0.05 | <= $0.10 | <= $0.20 | <= $0.50 | <= $1.00 |
|---|---|---|---|---|---|---|
| lean_esc | 10 | 20% | 50% | 100% | 100% | 100% |

## Per task (mean over repetitions)

| task | arm | pass | cost $ | turns | wall s | gruntly (status, attempts) | false pass |
|---|---|---|---|---|---|---|---|
| bugs_batch | lean_esc | 2/2 | 0.062 | 3.0 | 118 | passed+applied (1); passed+applied (1); passed+applied (1); passed+applied (1); passed+applied (1); passed+applied (1); passed+applied (1); passed+applied (1); passed+applied (1); passed+applied (1); passed+applied (1); passed+applied (1); passed+applied (1); passed+applied (1) | - |
| cli_json | lean_esc | 2/2 | 0.133 | 8.0 | 60 | escalate (1); passed+applied (1); passed+applied (1); escalate (1) | - |
| inventory_reorder | lean_esc | 2/2 | 0.127 | 5.0 | 121 | passed+applied (2); passed+applied (2); passed+applied (2); escalate (2) | - |
| rename_domain | lean_esc | 2/2 | 0.046 | 3.0 | 68 | passed+applied (1); passed+applied (1); passed+applied (1); passed+applied (1) | - |
| settings_refactor | lean_esc | 2/2 | 0.144 | 23.0 | 74 | passed+applied (1); escalate (1); passed+applied (1); escalate (1) | - |

Accounting: cost = Claude Code's own `total_cost_usd` for the whole session (cache reads included, so any takeover after an escalation is counted) plus the reviewers gruntly called outside it. Marginal = cost minus the $0.045 every fresh `claude -p` session pays before doing anything (it is the same in every arm, so it hides the differences). Cost of a pass = mean cost / pass rate. Takeover edits = the parent's own Edit/Write calls after its first gruntly call. Local child tokens are free of paid cost but cost wall time. False pass = gruntly reported `passed` but the hidden tests failed. Transcripts are in `bench/runs/`.
