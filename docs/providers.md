# Hosted providers for the child agent

## Choosing a provider and a model

```
gruntly setup               # first-time guide: what is installed, provider, key, model, and a tour of the commands
gruntly use                 # picker: choose provider, then a model from the live list; saved to this project or globally
gruntly use gemini gemma-4-26b-a4b-it --project      # or in one line (--global for all projects)
gruntly models gemini       # every model the account offers, with what the endpoint reports (--filter TEXT, --json)
gruntly models local        # the local server's models (size, quantization, loaded context for LM Studio)
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
