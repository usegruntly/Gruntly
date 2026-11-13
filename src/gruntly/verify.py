"""A live check of a provider: can this machine list its models and make one tiny call (a few tokens)?

`gruntly verify` runs it for every provider that has a key and every local server that answers, and says in one line each what
happened: ok, or why not (no key, bad key, rate limited, model not found, server unreachable, timeout, other). It sends no code and no
prompt of yours, only "Reply with the single word: ok" with a cap of a few tokens, so a check costs a fraction of a cent. A key is
never printed: it is scrubbed from every message that comes back, which some providers echo.

The result of the last check is kept (`verified.json` in the state directory) so `gruntly providers` can show it. The catalog's own
`verified = true` is a maintainer's statement; this is the user's own machine and key.
"""
from __future__ import annotations

import json
import socket
import ssl
import time
import urllib.error
import urllib.request
from dataclasses import asdict, dataclass
from pathlib import Path

from . import keys, models as mm, providers

TIMEOUT = 30
RETRIES = 2                      # a transient failure (the provider's own 5xx, a call that hangs) is tried again this many times: some APIs answer 500 on about half the calls
RETRY_WAIT = (2.0, 5.0)          # seconds before the first and the second retry
RETRY_ON = ("server", "timeout")
LOCAL_TIMEOUT = 2
PROMPT = "Reply with the single word: ok"
BODY_CHARS = 160


@dataclass
class Check:
    provider: str
    kind: str
    ok: bool
    stage: str                    # skipped | models | chat
    error: str | None = None      # no_key | auth | rate_limit | not_found | bad_request | server | network | timeout | other
    detail: str = ""
    latency_ms: int | None = None
    model: str | None = None
    models: int | None = None
    usage: dict | None = None
    tries: int = 1                # calls made for the chat check; above 1 when a transient failure was retried


def scrub(text: str, key: str | None) -> str:
    return text.replace(key, "***") if key else text


def classify(exc: BaseException) -> tuple[str, str]:
    """(error class, short detail) for an exception from urllib. The detail never includes request headers."""
    if isinstance(exc, urllib.error.HTTPError):
        code = exc.code
        try:
            body = exc.read(BODY_CHARS * 4).decode("utf8", "replace")
        except Exception:  # noqa: BLE001
            body = ""
        body = " ".join(body.split())[:BODY_CHARS]
        cls = ("auth" if code in (401, 403) else "rate_limit" if code == 429 else "not_found" if code == 404 else
               "bad_request" if code in (400, 422) else "server" if code >= 500 else "other")
        return cls, f"HTTP {code}" + (f": {body}" if body else "")
    reason = getattr(exc, "reason", exc)
    if isinstance(exc, (socket.timeout, TimeoutError)) or isinstance(reason, (socket.timeout, TimeoutError)):
        return "timeout", "no answer in time"
    if isinstance(reason, ssl.SSLCertVerificationError) or "CERTIFICATE_VERIFY_FAILED" in str(reason):
        return "tls", ("the provider's TLS certificate could not be verified because this Python has no root certificates to check it against. "
                       "Python from python.org on macOS: run 'Install Certificates.command' (in /Applications/Python 3.x). Otherwise use a Python from uv or Homebrew. "
                       "Behind a company proxy that re-signs traffic, point SSL_CERT_FILE at its root certificate")
    if isinstance(exc, (urllib.error.URLError, ConnectionError, OSError)):
        return "network", f"could not connect: {reason}"
    return "other", f"{type(exc).__name__}: {exc}"[:BODY_CHARS]


def _request(url: str, key: str | None, body: dict | None, timeout: float) -> dict:
    headers = {"Content-Type": "application/json"}
    if key:
        headers["Authorization"] = f"Bearer {key}"
    data = json.dumps(body).encode("utf8") if body is not None else None
    req = urllib.request.Request(url, data=data, headers=headers, method="POST" if body is not None else "GET")
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.load(r)


def _list(p: providers.Provider, key: str | None, timeout: float) -> int:
    if p.models_api == "gemini" and key:
        root = p.base_url.split("/v1beta")[0]
        req = urllib.request.Request(f"{root}/v1beta/models?pageSize=1000", headers={"x-goog-api-key": key})
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return len(mm._gemini(json.load(r)))
    return len(mm._openai(_request(p.base_url.rstrip("/") + "/models", key, None, timeout)))


def check(p: providers.Provider, model: str | None = None, timeout: float | None = None) -> Check:
    """One provider: key, model list, one tiny chat call (when there is a model to call)."""
    local = p.kind == "local"
    key = None if local else keys.lookup(p.name, p.key_env)[0]
    if not local and not key:
        return Check(p.name, p.kind, False, "skipped", "no_key", f"no key: set {p.key_env} or run: gruntly auth set {p.name}")
    t = timeout or (LOCAL_TIMEOUT if local else TIMEOUT)
    out = Check(p.name, p.kind, False, "models")
    t0 = time.monotonic()
    try:
        out.models = _list(p, key, t)
    except Exception as e:  # noqa: BLE001 - every failure becomes a class and a short, scrubbed line
        out.error, detail = classify(e)
        if local and out.error in ("network", "timeout"):       # Windows times out on a closed localhost port instead of refusing: same thing to a person
            out.error, detail = "network", f"not running: nothing answered at {p.base_url}"
        out.detail = scrub(detail, key)
        out.latency_ms = int((time.monotonic() - t0) * 1000)
        return out
    out.latency_ms = int((time.monotonic() - t0) * 1000)
    use = model or p.default_model
    if not use:
        out.ok = True
        out.detail = f"{out.models} models listed; pass --model ID to test a call (this provider has no default model)"
        return out
    out.model, out.stage = use, "chat"
    t1 = time.monotonic()
    earlier: list[str] = []
    try:
        while True:
            try:
                r = _request(p.base_url.rstrip("/") + "/chat/completions", key,
                             {"model": use, "messages": [{"role": "user", "content": PROMPT}], "max_tokens": 8, "temperature": 0}, t)
                break
            except Exception as e:  # noqa: BLE001
                cls = classify(e)[0]
                if cls not in RETRY_ON or out.tries > RETRIES:
                    raise
                earlier.append(cls)
                time.sleep(RETRY_WAIT[min(out.tries - 1, len(RETRY_WAIT) - 1)])
                out.tries += 1
        out.latency_ms = int((time.monotonic() - t1) * 1000)
        if not r.get("choices"):
            out.error, out.detail = "other", f"{use}: the answer had no choices"
            return out
        usage = r.get("usage") or {}
        out.usage = {k: usage[k] for k in ("prompt_tokens", "completion_tokens", "total_tokens") if isinstance(usage.get(k), int)} or None
        out.ok = True
        out.detail = (f"{out.models} models listed; {use} answered" + (f" ({out.usage['total_tokens']} tokens)" if out.usage and "total_tokens" in out.usage else "")
                      + (f" on try {out.tries} (earlier: {', '.join(earlier)})" if earlier else ""))
    except Exception as e:  # noqa: BLE001
        out.error, detail = classify(e)
        out.detail = scrub(f"{use}: {detail}" + (f" (after {out.tries} tries)" if out.tries > 1 else ""), key)
        out.latency_ms = int((time.monotonic() - t1) * 1000)
    return out


def run(names: list[str] | None = None, catalog: dict[str, providers.Provider] | None = None, model: str | None = None) -> list[Check]:
    """Every provider in `names`, or every hosted provider with a key plus every local server (a server that is not running reports it)."""
    cat = providers.ALL if catalog is None else catalog
    if names is None:
        names = [n for n, p in cat.items() if p.kind == "local" or keys.lookup(n, p.key_env)[1]]
    unknown = [n for n in names if n not in cat]
    if unknown:
        raise ValueError(f"unknown provider {unknown[0]!r}; known: {', '.join(cat)}")
    return [check(cat[n], model if len(names) == 1 else None) for n in names]


def record_path() -> Path:
    from .store import state_dir
    return state_dir() / "verified.json"


def record(checks: list[Check], now: float | None = None) -> None:
    """Keep the last result per provider (a skipped provider is not a result)."""
    try:
        path = record_path()
        old = json.loads(path.read_text(encoding="utf8")) if path.is_file() else {}
    except (OSError, ValueError):
        path, old = record_path(), {}
    for c in checks:
        if c.stage != "skipped":
            old[c.provider] = {"ts": time.time() if now is None else now, "ok": c.ok, "stage": c.stage, "model": c.model, "error": c.error}
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(old, indent=1), encoding="utf8")
    except OSError:
        pass


def last_results() -> dict:
    try:
        return json.loads(record_path().read_text(encoding="utf8"))
    except (OSError, ValueError):
        return {}


def as_dicts(checks: list[Check]) -> list[dict]:
    return [asdict(c) for c in checks]
