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
| Hermes 0.23.0 | identity only (`SOUL.md`, the tool-calling variant of our prompt); about 3,200 characters of its own help pointer and environment notes stay | 6 tools: gruntly's two MCP tools and four inert MCP helpers; no shell, no file tool (20 tools by default) | yes, by construction: there is no shell to restrict (gruntly's MCP server is its only tool source) | memory, tool search and the optional prompt sections off | tokens | live on a hosted provider (NVIDIA free tier) |
| Codex CLI 0.167.2 | yes (`model_instructions_file`), 19,500 characters to exactly ours | 9 tools to 4 (the two shell tools, `request_user_input`, `view_image`: no switch for the last two) | yes: read-only sandbox, approvals `never`, one execution-policy rule allows `gruntly`, which runs outside the sandbox; everything else is `blocked by policy` | features, web search, skills and AGENTS.md off | tokens | checked against the binary; needs a provider that serves the Responses API |
| Gemini CLI 0.68.0 | yes (`GEMINI_SYSTEM_MD`), 30,400 characters to exactly ours | yes (8 tools to 1) | yes (`tools.core = ["run_shell_command(gruntly)"]`; anything else is `denied by policy`) | MCP servers in a project's settings not tried | tokens | checked against the binary; Gemini API only |
| Aider 0.86.2 | no | no | no | no | tokens | working mode only: it has no tool loop, so it cannot be a delegating parent |
| direct (built in) | yes: gruntly's own loop sends only the delegating prompt | yes (one `bash` tool) | yes: one `gruntly` command, run without a shell | n/a | tokens, and dollars from the provider or the price table | stub; delegating only; any provider whose model calls tools |
| generic (your settings) | what you declare | what you declare | what you declare | what you declare | none | experimental: nothing is assumed |

Notes on setup:

- **Your own login and default model** are used unless you name a provider. A catalog provider (`gruntly providers`) is given to the harness as an OpenAI-compatible endpoint; its key goes in the environment, never on the command line or in a config file.
- **Hermes** gets no shell at all in delegating mode: its only tools are gruntly's own, through `gruntly mcp` (`gruntly_delegate`, `gruntly_manage`), so "only gruntly" holds by construction. It runs from a private data folder (`GRUNTLY_HERMES_PARENT_HOME`; on Windows the default is the short `~/.ghp/d`, because Hermes nests its environment about 200 characters deep and Windows stops at 260), one per mode so the working one never carries the delegating `SOUL.md`. Set it up once with `gruntly parent prepare hermes` (`hermes pm repair` for that folder). Three things about how Hermes works matter here, all found live: it runs the agent inside a background gateway process that later chats share, so (1) a provider's key is read from that process's environment and a stale gateway from a run with another provider answered with a 401, which is why the config makes the gateway exit two seconds after its last client; (2) the MCP server lives in that gateway, so nothing per run can go through its environment: the prompt names the repository (written fresh at each launch) and gruntly's server, told to require it, refuses a call without `repo`; (3) it adds four inert MCP helper tools (list and read prompts and resources) that cannot be switched off. Delegating needs `--provider`: the folder holds none of your own logins.
- **Codex** speaks only the Responses API (`wire_api = "chat"` is refused) and almost no provider outside OpenAI serves it, so gruntly puts a bridge between them (`gruntly/responsesbridge.py`): a small local server that translates Codex's requests into chat completions for your provider and the answers back, tool calls included. A provider the catalog marks `responses_api = true` (documentation, not a live check: OpenAI, OpenRouter, Groq, Fireworks, xAI, LM Studio, Ollama, vLLM) is used directly; every other provider, local or hosted, goes through the bridge, which needs only chat completions. A parent launch runs it as a wrapper (`python -m gruntly.responsesbridge --upstream URL -- codex ...`), so nothing has to own its lifetime. Delegating runs from a private `CODEX_HOME` (`GRUNTLY_CODEX_PARENT_HOME`) with your prompt and the one rule written into it, so it uses an API key, not your ChatGPT login. Working is Codex as shipped with the workspace-write sandbox and no approval prompts. Gemini 3 models need a `thought_signature` echoed with each tool call; the bridge remembers it by call id and puts it back.
- **Gemini CLI** speaks only the Gemini API, so the provider is `gemini`; delegating runs from a private `GEMINI_CLI_HOME` (`GRUNTLY_GEMINI_PARENT_HOME`) holding the prompt and the tool allowlist. `GOOGLE_GEMINI_BASE_URL` can point it at another server of that API.
- **Aider** can be a child (`harness = "aider"`) or the parent in `--mode working`. `--mode delegating` stops with the reason, and an automatic choice of parent never lands on it for delegating.
- **OpenCode** on a Gemini 3 model as the *parent* fails after the first tool call: Gemini 3 refuses a conversation in which a tool call comes back without its `thought_signature`, and OpenCode's HTTP layer drops it; as a *child* it works, because gruntly's proxy remembers the signature and puts it back. Use another provider for an OpenCode parent (NVIDIA's free tier worked), or another harness for Gemini 3 (Qwen Code, Codex through its bridge and Gemini CLI all work). Launching any parent with a working folder now also sets `PWD` to it: OpenCode takes its project folder from `$PWD`, so a script or benchmark runner started from another repository would otherwise have had it run (and edit) there; seen live, refused by gruntly's ambiguity check, nothing changed. OpenCode makes one extra small request per session to title it, and still reads `AGENTS.md`.
- Windows: harnesses installed with npm are `.cmd` shims; gruntly starts them in their own process group and ends the whole tree on a timeout.

## Quick start per harness

Set a provider's key once with `gruntly auth set NAME` (it is kept in a private file and only ever reaches the harness through its environment), pick a model with `gruntly models NAME`, then either run `gruntly agent --parent HARNESS --provider NAME --model ID "your task"` or save the choice with `gruntly parent set HARNESS --provider NAME --model ID` and run `gruntly agent "your task"`. Check what a setup will really do with `gruntly harness matrix` first.

| Harness | Install | Provider | Notes |
|---|---|---|---|
| Claude Code | already installed if you use it | its own login (`--provider` is ignored with a note) | the plugin is the usual way in; `gruntly agent` is the same lean setup from a terminal |
| OpenCode | `npm i -g opencode-ai` | any catalog provider, or its own login | the most complete lean setup |
| Qwen Code | `npm i -g @qwen-code/qwen-code` | any catalog provider, or its own login | `echo` is the one command that still runs besides `gruntly` |
| Hermes | the Hermes installer (WSL2 or Windows), then `gruntly parent prepare hermes` once | a provider is required (its key is passed by environment variable) | delegating has no shell, only gruntly's MCP tools |
| Codex CLI | `npm i -g @openai/codex` | any provider (a chat-only one goes through gruntly's Responses bridge); a provider is required for delegating | uses an API key, not your ChatGPT login |
| Gemini CLI | `npm i -g @google/gemini-cli` | `gemini` (a Gemini API key) | delegating needs `--provider gemini` |
| Aider | `python -m pip install aider-chat` | any catalog provider, or its own configuration | `--mode working` only |
| direct | nothing: built in | any catalog provider or local server; the model must support tool calls | prices its own tokens |
| generic | whatever your tool needs | whatever it supports | describe it in `[parent.generic]` |

For an agent harness you use by hand (not through `gruntly agent`), `gruntly init --snippet --for HARNESS` prints the block to paste into the file that harness reads (`CLAUDE.md`, `AGENTS.md` for OpenCode, Codex and Hermes, `QWEN.md`, `GEMINI.md`): it tells the agent to hand a bounded change to `gruntly agent-run` and read the result block, with the timeout wording that fits that harness (`--for any` for an unlisted one). Aider has no shell tool the model chooses to call, so it gets a pointer to `--mode working` instead.

## Two parents that are not a harness

- **direct** (`--parent direct --provider P --model M`): no harness at all. A short loop of gruntly's own (`gruntly/direct.py`) calls any OpenAI-compatible chat API with exactly the delegating prompt and one tool that runs `gruntly` commands. The command is parsed, not given to a shell: chaining (`&&`, `;`), pipes, redirection and substitution are refused with the reason, and the model sees the refusal; one heredoc is accepted, as the body that becomes the command's standard input (a holdout test). It is the only parent whose dollars gruntly can work out by itself, since it sees every response's `usage`: the provider's own figure, else the price table, else unknown, never zero. Delegating only. It needs a model that supports tool calls. It is never picked for you automatically.
- **generic** (`--parent generic`): any command-line harness gruntly has no adapter for, described in `[parent.generic]` in your settings (the command template, how the task and the delegating prompt are delivered, how to read the answer, and what the tool really does of the lean setup). Whatever you do not declare is reported as not done; it is marked experimental and returns no usage. See the docstring of `gruntly/parents/generic.py`. The child side of generic (`harness = "generic"`, `child_cmd`) now also knows `{endpoint}` and sets `OPENAI_BASE_URL`, `OPENAI_API_BASE` and `OPENAI_API_KEY`.

## As a child

The same harnesses can do the edit instead of directing it. Codex (through the Responses bridge unless the provider serves that API), Aider and Gemini CLI are children too, checked with the real binary against a stub (see `docs/adapters.md`). Gemini CLI speaks only the Gemini API, so a Gemini child runs behind a bridge that gruntly starts for the run (`geminibridge.py`): it turns the CLI's requests into chat completions for your endpoint, tool calls included. `gruntly harness matrix` shows all of it.

## Benchmarking any combination

`bench/run_matrix.py` ran a parent harness x child harness x provider grid from a TOML file of cells, with a dry run by default, `--yes-paid` and a stated `--max-usd` for a cell that costs money, and a price that is unknown reported as unknown, never as zero. It was removed from the tree on 2026-11-15 (it is at commit `91a53ae`); the public benchmark harness that replaces `bench/` will cover this.
