# Benchmark results

Raw results of the benchmark runs, one `.md` summary and one `.json` of the rows behind it per run. Written by the scripts in `bench/`.
Runs differ in parent model, child model, settings and date, so numbers from different files are **not** comparable unless the file
says they are. The reasoning that came out of them is in `../decisions.md` and `../lean-long-tasks.md`.

| Files | What it measured |
|---|---|
| `benchmark` | The first benchmark: ten tasks judged by hidden tests, Claude Code (default model) as parent, `qwen3.5-9b` as child. |
| `benchmark-v2`, `benchmark-v2-sonnet` | The reworked benchmark at 32k context, with the default parent and with a Sonnet parent (2026-11-07). |
| `benchmark-gd`, `benchmark-gd2` | The `gruntly do` flow against the parent working alone (2026-11-08). |
| `benchmark-lean`, `benchmark-lean2` | The lean `agent-run` arm on the six small tasks (2026-11-08). |
| `benchmark-lean3` to `benchmark-lean11` | One round each of the longer-task work, with the fixes made between rounds. Narrative in `../lean-long-tasks.md`. |
| `benchmark-local-alone`, `benchmark-local-gruntly` | The local model with no Claude involved: alone, and through gruntly. |
| `benchmark-cost`, `benchmark-cost-laguna`, `benchmark-cost-laguna-summary` | Cost of Claude alone against Claude with gruntly on ten small tasks, paired runs, child counted as free (2026-11-10). `benchmark-cost`: OpenCode with nemotron-bolt (alone, plugin policy, and two lean runs). `benchmark-cost-laguna`: Hermes with Laguna (alone, policy, forced delegation); the summary has the paired comparison. |
| `child-bench`, `child-bench-precise`, `child-bench-vague` | Which child profile (typist, worker, default) does best, with precise and with vague briefs. |

To rerun one, see the matching script in `bench/` (`run_bench.py`, `run_child_bench.py`, `run_local_alone.py`); each writes here by default.
