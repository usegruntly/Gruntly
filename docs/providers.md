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
for them. Free-tier limits for Gemma 4 were not published where we looked, so the preset only paces 15 requests/min: check
AI Studio and set `rate_limits` if yours differ. The full harness sends 11-13k input tokens per request, which matters if a
tokens-per-minute cap applies.

**Caveat.** A hosted model is not your local model. Use it to build and test the plumbing; accuracy and token numbers still
have to be measured on the local models.

Planned providers (issues #1-#5): NVIDIA NIM and Cloudflare Workers AI (priority), then Groq, OpenRouter; xAI is not planned.
