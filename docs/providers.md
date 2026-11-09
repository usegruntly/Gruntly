# Hosted providers for the child agent

Develop and iterate against a hosted OpenAI-compatible endpoint instead of the local model server, then confirm on the local
models at the end. Set `provider` in a spec or `.gruntly.toml`:

```toml
provider = "gemini"          # default model: gemma-4-26b-a4b-it
# rate_limits = { rpm = 10 } # optional override (rpm, tpm, rpd)
```

and put the key in the environment (`GEMINI_API_KEY`), never in the repo.

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

Planned providers (issues #1-#5): NVIDIA NIM and Cloudflare Workers AI (priority), then Groq, OpenRouter; xAI is not planned.
