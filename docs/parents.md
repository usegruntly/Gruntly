# Parent harnesses

A parent is the harness that reads your task. In **delegating** mode it is set up lean (our short prompt, a shell tool only, `gruntly` commands only) and its one job is to hand the work to a cheaper child through `gruntly` and report. In **working** mode it is the harness as shipped, doing the job itself with no gruntly (an escalation, or a baseline).

```
gruntly agent --parent opencode --provider openrouter --model MODEL "fix add() so the tests pass"
gruntly agent --parent qwen --mode working "..."
gruntly harness matrix            # every harness in both roles: what it can be, what was checked, which providers it can use
```

`--parent`, `--mode`, `--model` and `--provider` can be set once in a `[parent]` table (your global `config.toml`, or the project's `.gruntly.toml`, which wins); a flag beats both.

## What each harness can do of the lean setup

Checked with the real binary against a stub model server (`gruntly/probe.py`, no key, no cost). "Not done" means the harness has no option for it; the launch prints a `note:` line and the prompt carries the rule instead.

| Harness | Own prompt replaced | Only a shell tool | Only `gruntly` commands | Extensions off | Usage reported | Status |
|---|---|---|---|---|---|---|
| Claude Code | yes (`--system-prompt`) | yes | yes (`--allowedTools`) | yes | tokens and dollars | live |
| OpenCode 1.19.5 | yes (agent prompt), 21,800 to 1,900 characters | yes (10 tools to 1) | yes (`bash` allows `gruntly *` only) | plugins yes, MCP servers still start with every tool denied | tokens | checked against the binary |
| Qwen Code 0.26.9 | yes (`--system-prompt`, exactly ours) | yes (6 tools to 1) | refuses writes, reads, chained commands and interpreters; a command that touches no file (`echo`) still runs | `--bare`, as documented | tokens | checked against the binary |
| Hermes 0.23.0 | identity only (`SOUL.md`); about 5,300 characters of its own guidance stay | 20 tools to 4 (the shell plus three lookup tools) | no: the shell ran `touch` and `cat` | not checked | tokens | experimental |
| Codex CLI 0.167.2 | yes (`model_instructions_file`), 19,500 characters to exactly ours | 9 tools to 4 (the two shell tools, `request_user_input`, `view_image`: no switch for the last two) | yes: read-only sandbox, approvals `never`, one execution-policy rule allows `gruntly`, which runs outside the sandbox; everything else is `blocked by policy` | features, web search, skills and AGENTS.md off | tokens | checked against the binary; needs a provider that serves the Responses API |
| Gemini CLI 0.68.0 | yes (`GEMINI_SYSTEM_MD`), 30,400 characters to exactly ours | yes (8 tools to 1) | yes (`tools.core = ["run_shell_command(gruntly)"]`; anything else is `denied by policy`) | MCP servers in a project's settings not tried | tokens | checked against the binary; Gemini API only |
| Aider 0.86.2 | no | no | no | no | tokens | working mode only: it has no tool loop, so it cannot be a delegating parent |
| direct (built in) | yes: gruntly's own loop sends only the delegating prompt | yes (one `bash` tool) | yes: one `gruntly` command, run without a shell | n/a | tokens, and dollars from the provider or the price table | stub; delegating only; any provider whose model calls tools |
| generic (your settings) | what you declare | what you declare | what you declare | what you declare | none | experimental: nothing is assumed |

Notes on setup:

- **Your own login and default model** are used unless you name a provider. A catalog provider (`gruntly providers`) is given to the harness as an OpenAI-compatible endpoint; its key goes in the environment, never on the command line or in a config file.
- **Hermes** keeps a private data folder for the parent (`GRUNTLY_HERMES_PARENT_HOME`, or under gruntly's state folder), one per mode so the working one never carries the delegating `SOUL.md`. It needs Hermes's dependency environment once: `HERMES_HOME=<folder> hermes pm repair`. Delegating needs `--provider`, since that folder has none of your logins. Hermes sends a placeholder key to any local endpoint, so passing a hosted provider's key through `key_env` is the documented route and is not yet checked live.
- **Codex** speaks only the Responses API (`wire_api = "chat"` is refused), so the provider has to serve it: `gruntly providers` shows `responses_api` (from documentation, not checked live; OpenAI, OpenRouter, Groq, Fireworks, xAI, LM Studio, Ollama and vLLM are marked true, Gemini and DeepSeek false, the rest unknown). Delegating runs from a private `CODEX_HOME` (`GRUNTLY_CODEX_PARENT_HOME`) with your prompt and the one rule written into it, so it uses an API key, not your ChatGPT login. Working is Codex as shipped with the workspace-write sandbox and no approval prompts.
- **Gemini CLI** speaks only the Gemini API, so the provider is `gemini`; delegating runs from a private `GEMINI_CLI_HOME` (`GRUNTLY_GEMINI_PARENT_HOME`) holding the prompt and the tool allowlist. `GOOGLE_GEMINI_BASE_URL` can point it at another server of that API.
- **Aider** can be a child (`harness = "aider"`) or the parent in `--mode working`. `--mode delegating` stops with the reason, and an automatic choice of parent never lands on it for delegating.
- **OpenCode** makes one extra small request per session to title it, and still reads `AGENTS.md`.
- Windows: harnesses installed with npm are `.cmd` shims; gruntly starts them in their own process group and ends the whole tree on a timeout.

## Quick start per harness

Set a provider's key once with `gruntly auth set NAME` (it is kept in a private file and only ever reaches the harness through its environment), pick a model with `gruntly models NAME`, then either run `gruntly agent --parent HARNESS --provider NAME --model ID "your task"` or save the choice with `gruntly parent set HARNESS --provider NAME --model ID` and run `gruntly agent "your task"`. Check what a setup will really do with `gruntly harness matrix` first.

| Harness | Install | Provider | Notes |
|---|---|---|---|
| Claude Code | already installed if you use it | its own login (`--provider` is ignored with a note) | the plugin is the usual way in; `gruntly agent` is the same lean setup from a terminal |
| OpenCode | `npm i -g opencode-ai` | any catalog provider, or its own login | the most complete lean setup |
| Qwen Code | `npm i -g @qwen-code/qwen-code` | any catalog provider, or its own login | `echo` is the one command that still runs besides `gruntly` |
| Hermes | the Hermes installer (WSL2 or Windows) | a provider is required; the private folder needs `HERMES_HOME=<folder> hermes pm repair` once | experimental: its shell is not limited to `gruntly` |
| Codex CLI | `npm i -g @openai/codex` | a provider that serves the Responses API (OpenAI, OpenRouter, Groq, ...); a provider is required for delegating | uses an API key, not your ChatGPT login |
| Gemini CLI | `npm i -g @google/gemini-cli` | `gemini` (a Gemini API key) | delegating needs `--provider gemini` |
| Aider | `python -m pip install aider-chat` | any catalog provider, or its own configuration | `--mode working` only |
| direct | nothing: built in | any catalog provider or local server; the model must support tool calls | prices its own tokens |
| generic | whatever your tool needs | whatever it supports | describe it in `[parent.generic]` |

For an agent harness you use by hand (not through `gruntly agent`), `gruntly init --snippet` prints the block to paste into its `AGENTS.md`: it tells the agent to hand a bounded change to `gruntly agent-run` and read the result block.

## Two parents that are not a harness

- **direct** (`--parent direct --provider P --model M`): no harness at all. A short loop of gruntly's own (`gruntly/direct.py`) calls any OpenAI-compatible chat API with exactly the delegating prompt and one tool that runs `gruntly` commands. The command is parsed, not given to a shell: chaining (`&&`, `;`), pipes, redirection and substitution are refused with the reason, and the model sees the refusal; one heredoc is accepted, as the body that becomes the command's standard input (a holdout test). It is the only parent whose dollars gruntly can work out by itself, since it sees every response's `usage`: the provider's own figure, else the price table, else unknown, never zero. Delegating only. It needs a model that supports tool calls. It is never picked for you automatically.
- **generic** (`--parent generic`): any command-line harness gruntly has no adapter for, described in `[parent.generic]` in your settings (the command template, how the task and the delegating prompt are delivered, how to read the answer, and what the tool really does of the lean setup). Whatever you do not declare is reported as not done; it is marked experimental and returns no usage. See the docstring of `gruntly/parents/generic.py`. The child side of generic (`harness = "generic"`, `child_cmd`) now also knows `{endpoint}` and sets `OPENAI_BASE_URL`, `OPENAI_API_BASE` and `OPENAI_API_KEY`.

## As a child

The same harnesses can do the edit instead of directing it. Codex (it needs an endpoint that serves the Responses API) and Aider are new children, checked with the real binary against a stub (see `docs/adapters.md`); Gemini CLI has no child role, because a child is handed an OpenAI-compatible endpoint and Gemini CLI speaks only the Gemini API. `gruntly harness matrix` shows all of it.

## Benchmarking any combination

`bench/run_matrix.py` runs a parent harness x child harness x provider grid from a TOML file of cells, with one results store (`results.jsonl`, with the raw material kept beside it) and one report. It does nothing unless you pass `--run`, a cell that costs money needs `--yes-paid` and a stated `--max-usd`, and a price that is unknown is reported as unknown, never as zero. Start with `python bench/run_matrix.py --cells bench/cells.example.toml --tasks slugify` (a dry run).
