# bench: the research harness

This folder is how the author measured whether handing work from a big agent to a small one pays off. **It is not part of the product**: `src/gruntly` imports nothing from here, and the wheel and the source distribution leave out the run data. It is kept so that the numbers in `docs/where-delegation-wins.md` and `docs/benchmarks/` can be traced to the code and tasks that produced them.

## How far to trust the numbers

These are **internal measurements**: small samples, tasks that the author wrote or picked, one machine, one period (2026-11-07 to 2026-11-13), run by the people who built the tool. They explain why gruntly is designed the way it is (for example: delegating pays on longer tasks and does not on short ones). They are **not** a basis for headline claims, and the project's public claims are meant to come from published benchmarks that anyone can run and compare, not from this folder. That work is tracked in issue #22 (the Python exercises of Aider's polyglot benchmark, and a probe of SWE-bench Verified Mini). When it exists, a result should state: the same agent and prompt for the baseline and the delegated run, pass rate **and** total cost (big agent plus small agent), the number of tasks, the model versions and dates, and the command and raw logs to reproduce it.

## What is in here

| Folder | What it holds |
|---|---|
| `tasks/` | synthetic coding tasks: a starter that fails its visible test, hidden tests, and a reference solution |
| `tasks-real/` | tasks built from real fix commits of `click` (the fix commit's own tests are the hidden tests); `LICENSE-click.txt` applies to the copied test files |
| `tasks-agent/` | non-coding agent tasks (research, file work) with deterministic graders; no model judges anything |
| `runs*/`, `.cache/` | raw run records and caches; git-ignored |
| results | not here: reports and raw JSON are in `docs/benchmarks/` (start with its `README.md`) |

## The scripts

Run them from the repository root, for example `python bench/run_matrix.py --help`. Several read the author's own setup (Windows, LM Studio, a logged-in Claude Code, their session logs), so they are not promised to run unchanged elsewhere. **Anything that spends money is marked paid**; read the script's header and use its budget flags before you start one.

**Runners**

| Script | What it does | Cost |
|---|---|---|
| `run_matrix.py` | any parent harness x child harness x provider, from a TOML file of cells (`cells.example.toml`); a dry run prints the plan and starts nothing without `--run` | free unless a cell is marked paid, which also needs `--yes-paid` and `--max-usd` |
| `run_bench.py` | Claude Code as the parent in three arms, judged by hidden tests | **paid** (Claude usage) |
| `run_agent_bench.py` | the non-coding agent tasks, parent alone against delegating | **paid** |
| `run_deep_bench.py` | does delegating beat Claude alone when the session is already long | **paid** |
| `run_child_bench.py` | child-only: runs `gruntly run` against the local model server and judges with hidden tests, to compare child profiles | free of Claude; written for a local model server |
| `run_local_alone.py` | the small model alone on the tasks, through OpenCode: no Claude, no gruntly gates or retries | free of Claude |

**Reports and exports** (read existing run data; start nothing)

| Script | What it does |
|---|---|
| `cost_report.py`, `decision_report.py` | cost and decision tables from the rows `run_bench.py` writes |
| `cost_model.py` | modelled cost of delegating against doing it alone, by session length, from measured parameters (a model, not a run) |
| `trace.py`, `turn_breakdown.py` | a verbatim timeline of one delegated task; what each big-agent turn was and what it cost |
| `delegation_export.py` | builds `docs/benchmarks/delegation-export/` (one row per run) from the existing results and logs; numbers and short labels only |
| `gold_doc.py` | regenerates `docs/where-delegation-wins.md` |
| `persistence_check.py` | the pre-registered rule for whether a persistent child session was worth building (historical) |

**Task builders** (run once; the output is committed)

`make_tasks.py`, `make_large_tasks.py`, `make_xl_tasks.py`, `make_agent_tasks.py` generate `tasks/` and `tasks-agent/`. `real_tasks.py` builds `tasks-real/` from a repository's fix commits. `validate_tasks.py` checks a task set (the starter fails, the reference solution passes). `graders.py` holds the deterministic graders for the agent tasks.

## What is tested

The tests in `tests/` import and exercise `delegation_export`, `gold_doc`, `graders`, `real_tasks`, `run_bench`, `run_matrix` and `trace`. The other scripts were used for the experiments and are not covered, so treat them as lab notes.
