"""Hosted OpenAI-compatible endpoints the child agent can use instead of the local model server.

The child never sees the real API key: gruntly starts a small local proxy (proxy.py) that adds the key, spaces requests to
stay inside the provider's limits and retries a 429. The child talks to http://127.0.0.1:PORT/v1 with a dummy key.
Limits are conservative defaults, not promises: providers change them, and `rate_limits` in a spec or `.gruntly.toml`
overrides them (keys: rpm, tpm, rpd).
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Provider:
    name: str
    base_url: str
    key_env: str
    default_model: str
    rpm: int | None = None       # requests per minute
    tpm: int | None = None       # tokens per minute (estimated from the request size)
    rpd: int | None = None       # requests per day
    note: str = ""
    models_api: str = "openai"   # how the model list is fetched: openai (GET /models) or gemini (the native, richer listing)
    docs: tuple[tuple[str, str], ...] = ()   # (label, url) pairs shown when a person sets the key or picks a model


PROVIDERS: dict[str, Provider] = {
    # Gemma 4 through the Gemini API (AI Studio key). Gemma 3 is no longer listed in Google's Gemma-on-Gemini docs, and the
    # small Gemma sizes are not offered there. 26B-A4B activates about 4B parameters per token. Measured (a 429 named it):
    # 16,000 input tokens per minute on the free tier. The requests/min and daily numbers are not published: rpm is a guess.
    # The API also answers 500 INTERNAL on about half the calls; the proxy retries those.
    "gemini": Provider("gemini", "https://generativelanguage.googleapis.com/v1beta/openai", "GEMINI_API_KEY",
                       "gemma-4-26b-a4b-it", rpm=15, tpm=15000, note="Gemma 4 via the Gemini API", models_api="gemini",
                       docs=(("Get an API key", "https://aistudio.google.com/apikey"),
                             ("Models", "https://ai.google.dev/gemini-api/docs/models"),
                             ("Rate limits and free tier", "https://ai.google.dev/gemini-api/docs/rate-limits"))),
    # NVIDIA NIM (build.nvidia.com). The live model list (GET /v1/models, no key needed) has google/gemma-3-4b-it, gemma-3-12b-it,
    # nvidia/nemotron-3.5-lightning-30b-a3b (about 3B active), nemotron-3.5-bolt-e4b and mistral-nemo-12b; no Qwen. Listed does
    # not mean usable: on a free account, gemma-3-4b/12b, nemotron-nano-3, mistral-nemo-12b and granite-3.0-8b answered 404
    # "Function not found for account"; only nemotron-3.5-bolt-e4b and nemotron-3.5-lightning-30b-a3b worked (tool calls too). About 40 requests/min on the free tier was reported (your
    # account page shows the real number); no daily cap was found. Needs a phone-verified account.
    "nvidia": Provider("nvidia", "https://integrate.api.nvidia.com/v1", "NVIDIA_API_KEY",
                       "nvidia/nemotron-3.5-bolt-e4b", rpm=30, note="NVIDIA NIM free endpoints",
                       docs=(("Get an API key", "https://build.nvidia.com/settings/api-keys"),
                             ("Models (use the Free Endpoint filter)", "https://build.nvidia.com/models"),
                             ("Docs", "https://docs.api.nvidia.com/"))),
}


def get(name: str) -> Provider:
    try:
        return PROVIDERS[name]
    except KeyError:
        raise ValueError(f"unknown provider {name!r}; known: local, {', '.join(PROVIDERS)}") from None


def api_key(p: Provider) -> str | None:
    """The environment variable first, then the user's keys file (see keys.py)."""
    from . import keys
    return keys.lookup(p.name, p.key_env)[0]


# Shown for the local option, which is not a hosted Provider.
LOCAL_DOCS = (("LM Studio local server", "https://lmstudio.ai/docs/app/api"),
              ("Which local models and context size to use", "https://github.com/usegruntly/Gruntly/blob/main/README.md"))
GRUNTLY_DOCS = (("gruntly docs: providers, keys, limits", "https://github.com/usegruntly/Gruntly/blob/main/docs/providers.md"),
                ("gruntly repository", "https://github.com/usegruntly/Gruntly"))


def docs_for(name: str) -> tuple[tuple[str, str], ...]:
    """Links to print whenever a person sets a key or chooses a model."""
    base = LOCAL_DOCS if name == "local" else (PROVIDERS[name].docs if name in PROVIDERS else ())
    return base + GRUNTLY_DOCS[:1]
