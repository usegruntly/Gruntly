"""Hosted OpenAI-compatible endpoints the child agent can use instead of the local model server.

The child never sees the real API key: gruntly starts a small local proxy (proxy.py) that adds the key, spaces requests to
stay inside the provider's limits and retries a 429. The child talks to http://127.0.0.1:PORT/v1 with a dummy key.
Limits are conservative defaults, not promises: providers change them, and `rate_limits` in a spec or `.gruntly.toml`
overrides them (keys: rpm, tpm, rpd).
"""
from __future__ import annotations

import os
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


PROVIDERS: dict[str, Provider] = {
    # Gemma 4 through the Gemini API (AI Studio key). Gemma 3 is no longer listed in Google's Gemma-on-Gemini docs, and the
    # small Gemma sizes are not offered there. 26B-A4B activates about 4B parameters per token. Measured (a 429 named it):
    # 16,000 input tokens per minute on the free tier. The requests/min and daily numbers are not published: rpm is a guess.
    # The API also answers 500 INTERNAL on about half the calls; the proxy retries those.
    "gemini": Provider("gemini", "https://generativelanguage.googleapis.com/v1beta/openai", "GEMINI_API_KEY",
                       "gemma-4-26b-a4b-it", rpm=15, tpm=15000, note="Gemma 4 via the Gemini API"),
}


def get(name: str) -> Provider:
    try:
        return PROVIDERS[name]
    except KeyError:
        raise ValueError(f"unknown provider {name!r}; known: local, {', '.join(PROVIDERS)}") from None


def api_key(p: Provider) -> str | None:
    return os.environ.get(p.key_env) or None
