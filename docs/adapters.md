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

**Verified live** on 2026-11-09: Linux (WSL2 Ubuntu 24.04), a hosted endpoint (NVIDIA `nemotron-3.5-bolt-e4b`) through gruntly's local proxy.
Two one-line fixes through `gruntly run`: passed on attempt 1 in 30 s (9 model requests, default permissions) and in 18 s with the file-tools-only mode.

Windows: Hermes 0.23.0 also installs natively (`%LOCALAPPDATA%/hermes/bin/hermes.exe`; gruntly looks there when `hermes` is not on PATH). Verified 2026-11-10 with `poolside/laguna-xs-2.1` on NVIDIA through gruntly's proxy: a one-line fix passed on attempt 1 in 54 s, and 9 of 10 benchmark tasks delegated from Claude Code passed. Two things to know on native Windows: 0.23 prepares its own dependency environment for every new data folder, which fails on paths over 260 characters, so prepare one short folder once (`set HERMES_HOME=C:/hb`, `hermes pm repair`) and point gruntly at it with `GRUNTLY_HERMES_HOME=C:/hb`; and Laguna answers HTTP 400 "duplicate field `reasoning_content`" when Hermes replays a turn that carries both `reasoning` and `reasoning_content`, which gruntly's proxy now repairs. Hermes reports no token usage, so `child_tokens` is empty.

Set-up on Linux or WSL2 (older 0.19.0 verified there; gruntly, Hermes and its rate-limit proxy share one loopback and a hosted provider just works):

```
uv tool install hermes-agent
uv tool install "gruntly[mcp] @ git+https://github.com/usegruntly/Gruntly"   # inside WSL2 too
gruntly auth set nvidia            # or gemini; a local server on the Windows host needs "Serve on Local Network" in LM Studio
gruntly use nvidia nvidia/nemotron-3.5-bolt-e4b --project
```

How gruntly drives it (`adapters/hermes.py`):
- Headless mode is `hermes chat -Q -q PROMPT`: the final answer on stdout, `session_id: ID` on stderr, and `--resume ID` continues that session (checked: the second call remembered the edit).
- Hermes reads its endpoint from `$HERMES_HOME/config.yaml`. gruntly keeps one home per project (`.gruntly/child-state/hermes-home`) and rewrites `custom_providers` and `model` there before each attempt, because the proxy port changes per run. A config without a `model:` section is ignored with a warning.
- `--ignore-rules` keeps Hermes from injecting AGENTS.md, SOUL.md and memory. Permission mode `bypass` passes `--yolo`; `accept-edits` and `plan` pass `-t file` (read, search, patch, write; no shell). Hermes cannot make edits read-only, so plan equals accept-edits.
- `LANG=C.UTF-8` is set for the child: under an ASCII locale Hermes silently strips non-ASCII characters from the request.

Limits:
- Quiet mode prints no tool trace, so a Hermes run has no `child_trace` line and nothing from the child in the live feed (gruntly's own steps still appear). Non-quiet mode prints `┊` tool previews that could be parsed; not done.
- No token usage is reported. Every request carries Hermes's own system prompt and about 18 tool schemas (the `default`-profile cost; there are no slim profiles for it).
- `-v` (verbose) prints a masked fragment of the API key: gruntly never uses it.
- Context length for a custom endpoint defaults to 131072 in Hermes; for a local model with a smaller window, set it in the model's entry (not wired yet).
- One run measured per permission mode. No long-task or repeated benchmark has been done for Hermes.

## Environment notes

- WSL2 Ubuntu cannot reach `127.0.0.1:1234` on the Windows host (needs mirrored networking or the host IP) and has no Node of its own. M0 ran natively on Windows.
- Loaded context is 15000. Raising it needs `lms load qwen/qwen3.5-9b --context-length 32768`, with RAM at 15.7 GB.

## Verified through gruntly (M2, 2026-11-07)

- Prompt on stdin works with `qwen --auth-type openai --approval-mode yolo -o json` (no positional prompt); this avoids the Windows `.cmd` shim mangling multi-line arguments.
- A real two-bug task passed on attempt 2: attempt 1 failed a gate, the retry used `-r <session_id>` and fixed it. Cost about 145k child tokens and 100 s on the 9B model. The result JSON was about 1.6 KB.
- An impossible task (acceptance always exits 1) escalated after 2 attempts via stuck detection, with a 1.4 KB result.
- Real usage numbers from `result.usage` populate `child_usage`.

## Slim profiles (measured 2026-11-07)

Both children ship a large system prompt and many tool schemas (OpenCode ~10.8k input tokens on the first request of a trivial task, Qwen Code ~14k plus a ~7k "memory extractor" request). `profiles.py` replaces that with just what a task needs.

**OpenCode 1.19.5**
- A custom `agent` in `OPENCODE_CONFIG_CONTENT` with its own `prompt` replaces the default system prompt; select it with `--agent`. `--title x` should skip the hidden title-generation request (not verified).
- Each tool in the `tools` map set to `false` is removed from the request. A tool is only offered if its **permission is also granted explicitly**; with the tools map alone the first request was 355 tokens, no tools were offered and the model pasted its code into the reply (found by the child smoke test; now covered by a unit test).
- `edit`, `write` and `patch` share one `edit` permission, so `write` cannot be offered without `edit`. The prompt asks for whole-file rewrites; both tools exist.
- For bash, permission rules are ordered and the last match wins, so the catch-all `"*": "deny"` has to come first.
- `OPENCODE_DISABLE_PROJECT_CONFIG`, `OPENCODE_DISABLE_CLAUDE_CODE` and `OPENCODE_DISABLE_EXTERNAL_SKILLS` stop it reading AGENTS.md and `~/.claude` skills into the prompt.
- Result: slugify task with the typist profile: 2 requests of 1,235 and 1,488 input tokens, 3,136 child tokens in total, passed on attempt 1. Default profile: ~4 requests of ~11k, ~47-60k tokens.

**Qwen Code 0.26.9** (measured 2026-11-08)
- `--bare` skips auto-discovery and turns off the managed-memory extractor (the ~7k-token extra request). It forces the core tools to read_file, edit, notebook_edit and run_shell_command and ignores `--core-tools`, so unwanted tools are removed with `--exclude-tools`. There is no whole-file write tool in bare mode (`edit` with an empty `old_string` creates files).
- `--system-prompt` replaces the default system prompt. Whether `--exclude-tools` drops a tool's schema from the request is not verified.
- Measured on the slugify task, typist profile: **passed on attempt 1 with 3 requests of ~2.2k input tokens (7,329 child tokens, 40 s)**, against ~14k per request and ~77k tokens for the stock setup.
- Qwen's `edit` tool refuses to edit a file that was not first read with `read_file`. The first slim config excluded `read_file` (the file was inlined), so the model could never edit: 27 requests, 131k input tokens, no result. `read_file` now stays whenever editing is allowed; `get_goal` and `update_goal`, which bare mode offers and the model wandered into, are excluded.

- `self_check: true` on Qwen Code gives the child its full `run_shell_command` (there is no per-command allowlist in bare mode); only OpenCode can restrict the shell to the acceptance command. The benchmark found self-checking bought nothing, so the default (no shell) is also the safer choice.
