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

## OpenCode, Hermes Agent

Not yet installed. Covered in Milestone 3.

## Environment notes

- WSL2 Ubuntu cannot reach `127.0.0.1:1234` on the Windows host (needs mirrored networking or the host IP) and has no Node of its own. M0 ran natively on Windows.
- Loaded context is 15000. Raising it needs `lms load qwen/qwen3.5-9b --context-length 32768`, with RAM at 15.7 GB.

## Verified through gruntly (M2, 2026-11-07)

- Prompt on stdin works with `qwen --auth-type openai --approval-mode yolo -o json` (no positional prompt); this avoids the Windows `.cmd` shim mangling multi-line arguments.
- A real two-bug task passed on attempt 2: attempt 1 failed a gate, the retry used `-r <session_id>` and fixed it. Cost about 145k child tokens and 100 s on the 9B model. The result JSON was about 1.6 KB.
- An impossible task (acceptance always exits 1) escalated after 2 attempts via stuck detection, with a 1.4 KB result.
- Real usage numbers from `result.usage` populate `child_usage`.
