# Adapter notes (Milestone 0)

Measured 2026-11-07, native Windows 11, LM Studio at `http://127.0.0.1:1234/v1`, model `qwen/qwen3.5-9b` (loaded context 15000, below the 32k target).

## Qwen Code 0.26.9

Install: `npm i -g @qwen-code/qwen-code`.

| Item | Result |
|---|---|
| Headless call | `qwen --auth-type openai -m <model> --approval-mode yolo -o json "<prompt>"` with `OPENAI_BASE_URL` and `OPENAI_API_KEY` (any dummy value for LM Studio) in the env. Exit 0 on success. |
| `-p` | Works but deprecated; positional prompt is the current form. |
| Output | `-o json` prints one JSON array of events: `system/init`, `assistant` (thinking, text, tool_use blocks), `user` (tool results), then a final `result` event. Fixture: `tests/fixtures/qwen/headless_json_success.json`. |
| Final message | `result.result` (string). |
| Session id | `result.session_id`, also in `system/init`. |
| Usage | `result.usage` has `input_tokens`, `output_tokens`, `total_tokens`; `result.stats.models.<model>` has per-request detail. Real tokens are available, so `child_usage.available` can be true. The trivial task cost about 77k prompt tokens over 6 requests. |
| Resume | `-r <session_id>` works: the resumed run kept the same session id and remembered the earlier edit. `-c` resumes the latest session in the project. |
| Limits | `--max-wall-time` (exit code 55 on breach), `--max-tool-calls`, `--max-session-turns` exist. gruntly still enforces its own limits. |
| Approvals | `plan`, `default`, `auto-edit`, `auto`, `yolo`. Only `yolo` was tested. Prints a stderr warning about no sandbox (silence with `QWEN_CODE_SUPPRESS_YOLO_WARNING=1`). Narrower modes (`auto-edit` for edits only, `auto` classifier) are untested; shell access is needed for the child to run the acceptance command. |
| Other | `--acp` starts ACP mode. `--worktree` exists, but gruntly stays the only owner of worktrees. `--bare`/`--safe-mode` skip auto-discovery of customizations; worth using so the child does not load unrelated skills or MCP servers. |

Disagreements with the brief: output formats and resume match. The brief's `--continue` works but `-r <id>` is the better retry mechanism. `--yolo` is the same as `--approval-mode yolo`.

Open items: test `auto-edit`/`auto` modes, `--bare`, `--exclude-tools`, behaviour on a model server that is down, and a failing run's exit code and output.

## OpenCode 1.19.5

Install: `npm i -g opencode-ai`.

| Item | Result |
|---|---|
| Headless call | `opencode run --format json --auto -m lmstudio/<model>` with the prompt on stdin. Exit 0 on success. |
| Local model | No built-in LM Studio provider. gruntly passes a config through `OPENCODE_CONFIG_CONTENT` (`@ai-sdk/openai-compatible`, `baseURL` = spec endpoint). |
| Output | JSONL: `step_start`, `tool_use`, `text`, `step_finish`. Fixture: `tests/fixtures/opencode/run_json_success.jsonl`. |
| Final message | Last non-blank `text` event. |
| Session id | `sessionID` on every event; resume with `-s <id>`. |
| Usage | `step_finish.part.tokens` (`input`, `output`, `total`); gruntly sums them. Trivial task: about 45k tokens against Qwen Code's 77k. |
| Approvals | `--auto` approves everything not explicitly denied. |
| State | Uses a global SQLite DB. This machine had an old one that made it fail with `Database is not empty and has no session table`. gruntly points `XDG_DATA_HOME`, `XDG_CONFIG_HOME`, `XDG_STATE_HOME` and `XDG_CACHE_HOME` at a private per-run dir under `.gruntly/child-state/`, which fixed it and keeps runs from sharing sessions. |
| Through gruntly | The two-bug task passed on attempt 1 in 130 s using 94k tokens. |
| Not used | `opencode serve` plus `run --attach`: only helps MCP cold starts; short tasks do not need it. |

## Hermes Agent 0.19.0

Not verified end to end.
- Native Windows install fails: `pywinpty` needs a build toolchain. It installs with pip in WSL2 Ubuntu.
- Flags confirmed from `hermes chat --help`: `-q` single query, `-Q` quiet, `--yolo`, `-m`, `--provider`, `--resume ID`, `--continue`, `--ignore-rules`, `--ignore-user-config`, `--safe-mode`, `--max-turns`, `-w` (own worktree; gruntly stays the only worktree owner).
- A live run was not possible: WSL2 cannot reach LM Studio, which listens on Windows loopback only. To finish this, enable "Serve on Local Network" in LM Studio (or use WSL mirrored networking), then point a Hermes provider at it and record a fixture.
- The adapter therefore returns the raw quiet-mode stdout as the summary, reports no usage and no resume support.

## Environment notes

- WSL2 Ubuntu cannot reach `127.0.0.1:1234` on the Windows host (needs mirrored networking or the host IP) and has no Node of its own. M0 ran natively on Windows.
- Loaded context is 15000. Raising it needs `lms load qwen/qwen3.5-9b --context-length 32768`, with RAM at 15.7 GB.

## Verified through gruntly (M2, 2026-11-07)

- Prompt on stdin works with `qwen --auth-type openai --approval-mode yolo -o json` (no positional prompt); this avoids the Windows `.cmd` shim mangling multi-line arguments.
- A real two-bug task passed on attempt 2: attempt 1 failed a gate, the retry used `-r <session_id>` and fixed it. Cost about 145k child tokens and 100 s on the 9B model. The result JSON was about 1.6 KB.
- An impossible task (acceptance always exits 1) escalated after 2 attempts via stuck detection, with a 1.4 KB result.
- Real usage numbers from `result.usage` populate `child_usage`.
