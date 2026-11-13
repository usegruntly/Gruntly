# Hosted providers for the child agent

## The catalog

`gruntly providers` lists every provider gruntly knows, whether a key is set (never the key itself), and what the catalog says about it.
The catalog is data: `src/gruntly/data/providers.toml`, with these entries.

| Hosted (needs a key) | Local (no key) |
|---|---|
| gemini, nvidia, openrouter, openai, deepseek, groq, together, fireworks, mistral, cerebras, xai | lmstudio, ollama, llamacpp, vllm |

- **Verified** means a live check has passed against the provider. Today that is `gemini` and `nvidia` only. Every other entry comes from the
  provider's documentation and may be out of date; the limits are conservative defaults, not promises.
- **No model ids are kept in the catalog** (ids change). A provider without a `default_model` asks you to pick one:
  `gruntly models openrouter`, then `gruntly use openrouter MODEL`.
- **Local servers**: `provider = "ollama"` means the local provider at Ollama's address (`http://127.0.0.1:11434/v1`) unless the spec sets
  its own `endpoint`. Same for `lmstudio`, `llamacpp` and `vllm`.
- **Add or override** an entry in `~/.config/gruntly/providers.toml` (all projects) or `<project>/.gruntly/providers.toml` (one project). A later
  file wins field by field, so a one-line override is enough:

```toml
[groq]
rpm = 20                       # your own limit

[my-gateway]                   # a provider gruntly does not know
base_url = "https://llm.example.com/v1"
key_env = "MY_GATEWAY_API_KEY"
```

A file with a mistake is reported by `gruntly providers` and ignored; the packaged catalog keeps working.

## Checking that a provider works

```
gruntly verify                 # every provider that has a key, and every local server that answers
gruntly verify groq            # one provider
gruntly verify openrouter --model meta-llama/llama-3.3-70b-instruct     # a provider with no default model needs one to test a call
```

One line per provider: `ok`, or why not (`no key`, `auth`, `rate_limit`, `not_found`, `bad_request`, `server`, `timeout`, `network`). The check lists the
models and makes one call that sends only "Reply with the single word: ok" and asks for at most 8 tokens: a fraction of a cent, none of your code. A key is
never printed (it is scrubbed from the messages providers send back). The last result per provider shows as `CHECKED HERE` in `gruntly providers`.
A local server that is not running reports `not running`; that is not a failure of the default sweep, but is one when you name it.

`gruntly models PROVIDER` keeps a day-old copy of a hosted provider's list (`--refresh` asks again); local servers are always live.

## What a hosted child costs

For a child on a hosted provider, gruntly's local proxy reads the `usage` in every response, so the tokens are exact whatever the child harness is.
Dollars come from, in this order: the provider's own report in the response (OpenRouter), your price file, the provider's model listing (OpenRouter and
Together list prices; `gruntly models PROVIDER` caches them). If none has the model, the price is **unknown**: the run says so, the benchmark counts it as zero
and lists the run as a lower bound. It is never guessed. A local server costs no API dollars (compute is not priced).

```toml
# ~/.config/gruntly/prices.toml  (or <project>/.gruntly/prices.toml; the project file wins)
[[price]]
provider = "groq"
model = "llama-3.3-70b-versatile"     # an id or a glob
input = 0.59                          # dollars per million tokens
output = 0.79
cache_read = 0.059                    # optional
```

## Choosing a provider and a model

```
gruntly setup               # first-time guide: child agent, provider, key, model, and a tour of the commands
gruntly harness            # choose the child agent (opencode, qwen, hermes, generic); --list, --fetch for their own descriptions
gruntly use                 # picker: choose provider, then a model from the live list; saved to this project or globally
gruntly use gemini gemma-4-26b-a4b-it --project      # or in one line (--global for all projects)
gruntly models gemini       # every model the account offers, with what the endpoint reports (--filter TEXT, --json)
gruntly models local        # every model LM Studio has downloaded, loaded or not, even with its server off (via `lms ls`);
                            # size, parameters, quantization, tool-use support, and which one is loaded when the server runs
```

gruntly does not rank or hide models and does not say which are free: the list is whatever the endpoint reports for your key, and a
listing does not mean the account can call a model (NVIDIA's list includes models that answer 404). Check the provider's docs
(gruntly prints the links whenever you set a key or choose a model) for what is free. Running `gruntly` with no arguments in a terminal
offers the setup guide the first time; it never interrupts Claude calling gruntly.

What each endpoint tells us differs: Gemini's native listing has descriptions and token limits, NVIDIA's has only an id, an owner and
a (sometimes wrong) date, LM Studio has size, quantization and context. `--json` shows everything an endpoint sent.


Develop and iterate against a hosted OpenAI-compatible endpoint instead of the local model server, then confirm on the local
models at the end. Set `provider` in a spec or `.gruntly.toml`:

```toml
provider = "gemini"          # default model: gemma-4-26b-a4b-it
# rate_limits = { rpm = 10 } # optional override (rpm, tpm, rpd)
```

and give gruntly the key one of two ways (never in the repo):

```
gruntly auth set gemini      # hidden prompt; saved to ~/.config/gruntly/keys.toml
gruntly auth list            # which providers have a key, and from where (never shows it)
gruntly auth remove gemini
```

or the environment variable `GEMINI_API_KEY`, which wins when both exist. The keys file is plain text, restricted to your user
(chmod 600, or an owner-only ACL on Windows; if that cannot be applied the command says so). Only the preset's own URL ever
receives the key: a project cannot change a provider's base URL, and the key is not written to a run's spec, logs or result.

**How it works.** gruntly starts a local proxy for the run. The child harness talks to `http://127.0.0.1:PORT/v1` with a dummy
key; the proxy adds the real key, spaces requests to the provider's limits, retries a 429 after the delay it names, and stops
with a clear message when the daily quota is used up. What a run used is saved in `.gruntly/runs/<id>/provider.json`.

**Gemini (Gemma 4).** Gemma 3 and the small Gemma sizes are not offered through the Gemini API any more; the listed models are
`gemma-4-31b-it` and `gemma-4-26b-a4b-it` (about 4B active parameters). Function calling and system instructions are documented
for them. Measured on 2026-11-09 (the 429 body names it): **16,000 input tokens per minute** on the free tier. The requests/min and daily
limits are not published, so the preset paces 15 requests/min as a guess. The full harness sends 11-13k input tokens per
request, so that is about one request a minute: a 4-request task took 15 minutes (11 requests, 15 rate-limit retries, 758 s
waiting) before the preset knew the cap. The API also returns 500 INTERNAL on about half of the calls; the proxy retries them.
Both Gemma 4 models returned tool calls correctly through the OpenAI-compatible endpoint. One real task (a one-line edit in a
700 KB file, which the local 9B/4B models failed on) passed on the first attempt.

**Caveat.** A hosted model is not your local model. Use it to build and test the plumbing; accuracy and token numbers still
have to be measured on the local models.

**NVIDIA NIM** (`provider = "nvidia"`, env `NVIDIA_API_KEY`, default model `nvidia/nemotron-3.5-bolt-e4b`). Checked 2026-11-09 with
a free account: the public model list is not what you can call. `gemma-3-4b-it`, `gemma-3-12b-it`, `nemotron-nano-3-30b-a3b`,
`mistral-nemo-12b-instruct` and `granite-3.0-8b-instruct` return 404 "Function not found for account". Two work and return tool
calls: `nvidia/nemotron-3.5-bolt-e4b` (4B class) and `nvidia/nemotron-3.5-lightning-30b-a3b` (about 3B active).
The long-file edit task (a one-line change in a 700 KB file), full OpenCode harness, one run each:

| Model | Result | Wall | Requests | Notes |
|---|---|---|---|---|
| nemotron-3.5-bolt-e4b | passed, attempt 1 | 13 s | 5 | no 429s, no waiting |
| nemotron-3.5-lightning-30b-a3b | failed, scope gate | 59 s | 14 | edited the main repo's file instead of its worktree; the gate caught it (issue #6) |
| gemma-4-26b-a4b-it (Gemini) | passed, attempt 1 | 901 s | 11 | 758 s waiting on the 16k tokens/min cap |

Cross-check against build.nvidia.com's Free Endpoint filter (45 models, 2026-11-09): the five 404 models are not on it (the API's
`/v1/models` still lists older models that are no longer free endpoints), while the two working ones are. Other small or
mid-size free endpoints on that page, probed with one tool-call request: `poolside/laguna-xs-2.1` (33B MoE for agentic coding)
works (HTTP 200, tool call, 1.9 s); `openai/gpt-oss-20b` and `deepseek-ai/deepseek-v4.1-flash` timed out at 90 s twice (queued or
overloaded); `google/gemma-4-31b-it` and `meta/muse-glimmer-30b` timed out once. Not run on the real task yet.

Single runs on one task: they show the route works, not which model is better.

Planned providers (issues #2-#5; #1 NVIDIA is now built): Cloudflare Workers AI (priority), then Groq, OpenRouter; xAI is not planned.

## Which providers serve which API (`responses_api`)

Most harnesses speak OpenAI chat completions, which every provider here serves. Codex CLI speaks only the Responses API, so each catalog entry may carry `responses_api = true` or `false` (from the provider's documentation; absent when unknown; never checked live): OpenAI, OpenRouter, Groq, Fireworks, xAI, LM Studio, Ollama and vLLM are marked true, the Gemini API and DeepSeek false, the others unknown. For Codex the flag decides one thing: a provider marked true is used directly, every other one goes through gruntly's Responses-to-chat bridge (`responsesbridge.py`), so Codex works with all of them; `gruntly harness matrix` shows `yes` for the first and `bridged` for the rest. `gruntly providers --json` shows the flag. Override it for your own setup in `~/.config/gruntly/providers.toml` (`[mistral]` then `responses_api = true`).
