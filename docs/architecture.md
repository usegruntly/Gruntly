# How gruntly is put together

Two roles, one boundary. The **parent** is the agent that reads your task. The **child** is the cheaper agent that does the edit. gruntly sits between them: it runs the child in a throwaway git worktree, checks what it did, and gives the parent one small result.

```
                 task                          brief                              edit
  you ------> PARENT harness ----------> gruntly (runner) ----------> CHILD harness ----> model
              (Claude Code, OpenCode,      worktree, gates,             (OpenCode, Qwen,    (local server, or a
               Qwen, Hermes, Codex,        retries, result              Hermes, Codex,       hosted provider
               Gemini CLI, Aider,             |                         Gemini CLI, Aider,   through gruntly's
               direct, generic)               +--- ~1.5k-token result    Claude Code,         proxy)
                                                    block back to the     generic)
                                                    parent
```

Any parent can be paired with any child and any provider, subject to what each harness speaks (`gruntly harness matrix`).

## The parent side (`parents/`)

A parent adapter knows how to build a launch (`command`), read what came back (`parse`), and say honestly what the harness can do of the **lean setup** (`capabilities`). There are two prompt categories (`parents/prompts.py`): **delegating**, in which the parent is shown only a short prompt and one shell tool and may run only `gruntly` commands, so its own context stays small; and **working**, the harness as shipped, which does the job itself (the baseline, and what an escalation uses).

Each harness gets the lean setup through its own options (a replaced system prompt, an allowed-tools list, a sandbox plus one execution-policy rule, an allowlist with a command prefix), and none of that is trusted until it is measured: `probe.py` is a stub model server that speaks the chat, Responses and Gemini protocols, records the system prompt, the tool names and the key header the real binary sends, and can play a model that calls a tool, so a test can ask for `echo` and for `gruntly --help` and see which one the harness refuses. Where a harness cannot do part of it, `ParentCaps` and the launch's `note:` lines say so; nothing is claimed that was only read from documentation. `parents/direct.py` + `direct.py` are the one parent that is not a harness: a loop of gruntly's own with one tool, which also lets gruntly price the parent's tokens itself.

`gruntly agent` (`agent.py`) is the launcher: it resolves harness, mode, provider and model from flags and the `[parent]` table (`gruntly parent`), launches the adapter, and when a delegating parent reports `GRUNTLY-FALLBACK` follows with a working session told what the child tried.

## The child side (`runner.py`, `adapters/`)

`runner.py` takes a spec, makes a worktree (`worktree.py`), asks the child adapter for a command, runs it with an idle guard and a budget, then runs the **gates** (acceptance command, file scope, diff size, test weakening, new dependencies) and the optional holdout, retries with the failure fed back, and writes the result (`result.py`, `markers.py`) that the parent reads. Nothing is committed; `gruntly apply` brings a passing patch into your tree. Secrets are redacted from everything stored or returned (`redact.py`). Stuck children are caught by `escalation.py`; `coverage.py` counts how much of a request a diff covers.

Every child adapter is the same shape (`detect`, `command`, `parse`, `capabilities`, `cancel`). The endpoint a child talks to is always OpenAI-compatible:

- **Local:** the model server on your machine (LM Studio, Ollama, llama.cpp, vLLM), no key, no proxy.
- **Hosted:** gruntly starts `proxy.py` for the run. The child sees a loopback URL and a placeholder key; the proxy adds the real key, spaces requests to the provider's limits, retries a 429, and meters every response's `usage` (`usage.py`), so tokens and dollars are known whatever harness runs (`pricing.py`, `accounting.py`; an unknown price is unknown, never zero).
- **Gemini CLI** speaks only the Gemini API, so the runner puts `geminibridge.py` in front of the endpoint for the run: a local server that turns Gemini requests into chat completions and back, tool calls included.
- **Codex CLI** speaks only the Responses API, so `responsesbridge.py` does the same for it (the runner starts it for a child; a parent launch runs it as a wrapper), unless the provider serves Responses itself. Both bridges carry Gemini 3's `thought_signature` on tool calls so that Google's own endpoint accepts the conversation.

## Providers and keys

`providers.py` reads the catalog `data/providers.toml` (eleven hosted, four local; user and project files override it field by field) with each provider's base URL, limits, free tier and whether it serves the Responses API. `keys.py` keeps API keys in one private file (or the environment); a key only ever reaches a harness through its environment, never a command line, spec, log or result. `models.py` lists what an account offers; `verify.py` makes one tiny live call per provider (`gruntly verify`).

## Choosing and comparing

`matrix.py` builds the harness x role x provider table from the registries (`gruntly harness matrix`); `onboard_parent.py` and `onboard.py` are the guided setup and `gruntly parent` (including the suggestion from what is installed). `bench/run_matrix.py` runs any parent x child x provider cell against the same hidden tests, with one results store, a dry run by default and a stated cap for anything that can cost money.

## What to read next

| To understand | Read |
|---|---|
| what each parent can do and how it was checked | `docs/parents.md` |
| each child harness and its quirks | `docs/adapters.md` |
| providers, keys, limits | `docs/providers.md` |
| why things are the way they are | `docs/decisions.md` |
| what was measured | `docs/benchmarks/`, `docs/where-delegation-wins.md` |
