"""The models an account (or the local server) offers, as the endpoint itself reports them.

Nothing here is a curated list: it is fetched live with the person's key, and every field the endpoint gives is kept in `raw`.
What an endpoint says about a model differs a lot (Gemini's native listing has descriptions and token limits; NVIDIA's has an
id, a creation date and an owner; LM Studio has size, quantization and loaded context), so `info` holds whatever is available
and a missing field is simply absent. A model being listed does not mean the account can call it, or that it is free: that is
for the person to check in the provider's docs (gruntly prints the links).
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from urllib.parse import urlparse

from . import keys, providers

TIMEOUT = 20


class ModelsError(RuntimeError):
    pass


@dataclass
class Model:
    id: str
    context: int | None = None
    info: dict = field(default_factory=dict)     # human-readable facts, in display order
    raw: dict = field(default_factory=dict)      # everything the endpoint sent


def _get(url: str, headers: dict) -> dict:
    req = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
            return json.load(r)
    except urllib.error.HTTPError as e:
        raise ModelsError(f"{urlparse(url).netloc} answered HTTP {e.code}" +
                          (" (is the API key right?)" if e.code in (400, 401, 403) else "")) from None
    except (urllib.error.URLError, OSError, ValueError) as e:
        raise ModelsError(f"could not reach {urlparse(url).netloc}: {getattr(e, 'reason', e)}") from None


def _strip(model_id: str) -> str:
    return model_id[len("models/"):] if model_id.startswith("models/") else model_id


def _openai(data: dict) -> list[Model]:
    out = []
    for m in data.get("data", []):
        info = {}
        if m.get("owned_by"):
            info["owner"] = m["owned_by"]
        if m.get("display_name"):
            info["name"] = m["display_name"]
        # NVIDIA sends 1993 for models that are not that old: a wrong date is worse than none (it stays in `raw`)
        if isinstance(m.get("created"), (int, float)) and m["created"] > 1_420_070_400:
            info["created"] = _date(m["created"])
        ctx = next((m[k] for k in ("context_length", "context_window", "max_context_length") if isinstance(m.get(k), int) and not isinstance(m.get(k), bool)), None)
        price = _price(m.get("pricing"))
        if price:
            info["price"] = price
        out.append(Model(_strip(str(m.get("id", "?"))), ctx, info, m))
    return out


def price_numbers(p) -> tuple[float, float] | None:
    """(input, output) dollars per million tokens from a listing's pricing object, or None. OpenRouter gives dollars per token as text,
    Together and others give per-million numbers."""
    if not isinstance(p, dict):
        return None
    def num(*keys):
        for k in keys:
            try:
                return float(p[k])
            except (KeyError, TypeError, ValueError):
                continue
        return None
    i, o = num("prompt", "input"), num("completion", "output")
    if i is None or o is None:
        return None
    return (i * 1e6, o * 1e6) if "prompt" in p else (i, o)           # OpenRouter: dollars per token


def _price(p) -> str | None:
    """"in $0.15 / out $0.60 per Mtok" from a listing that gives per-token or per-Mtok prices."""
    n = price_numbers(p)
    return f"in ${n[0]:g} / out ${n[1]:g} per Mtok" if n else None


def _gemini(data: dict) -> list[Model]:
    out = []
    for m in data.get("models", []):
        info = {}
        if m.get("displayName"):
            info["name"] = m["displayName"]
        if m.get("description") and m.get("description") != m.get("displayName"):
            info["about"] = m["description"]
        if m.get("outputTokenLimit"):
            info["max output"] = m["outputTokenLimit"]
        if m.get("thinking"):
            info["thinking"] = True
        if m.get("supportedGenerationMethods"):
            info["methods"] = ", ".join(m["supportedGenerationMethods"])
        out.append(Model(_strip(str(m.get("name", "?"))), m.get("inputTokenLimit"), info, m))
    return out


def _lmstudio(data: dict) -> list[Model]:
    out = []
    for m in data.get("data", []):
        info = {k: m[k] for k in ("publisher", "arch", "quantization", "type", "state") if m.get(k)}
        ctx = m.get("loaded_context_length") or m.get("max_context_length")
        if m.get("loaded_context_length") and m.get("max_context_length"):
            info["max context"] = m["max_context_length"]
        out.append(Model(str(m.get("id", "?")), ctx, info, m))
    return out


def _lms_exe() -> str | None:
    exe = shutil.which("lms")
    if exe:
        return exe
    for name in ("lms.exe", "lms"):                       # LM Studio's installer puts it here without touching PATH
        p = os.path.join(os.path.expanduser("~"), ".lmstudio", "bin", name)
        if os.path.isfile(p):
            return p
    return None


def _lms_downloaded() -> list[Model] | None:
    """Every model LM Studio has downloaded, loaded or not, from its own CLI (`lms ls --json`). It reads the local model
    folder, so it works with the server off and without loading anything. None when `lms` is missing or fails."""
    exe = _lms_exe()
    if not exe:
        return None
    try:
        r = subprocess.run([exe, "ls", "--json"], capture_output=True, text=True, encoding="utf8", errors="replace", timeout=30)
        data = json.loads(r.stdout)
    except (OSError, ValueError, subprocess.SubprocessError):
        return None
    out = []
    for m in data if isinstance(data, list) else []:
        info = {}
        if m.get("displayName"):
            info["name"] = m["displayName"]
        if m.get("type") and m["type"] != "llm":
            info["type"] = m["type"]
        if m.get("paramsString"):
            info["params"] = m["paramsString"]
        if m.get("architecture"):
            info["arch"] = m["architecture"]
        q = m.get("quantization")
        if isinstance(q, dict) and q.get("name"):
            info["quant"] = q["name"]
        if m.get("sizeBytes"):
            info["size"] = f"{m['sizeBytes'] / 1e9:.1f} GB"
        if m.get("trainedForToolUse"):
            info["tool use"] = True
        if m.get("vision"):
            info["vision"] = True
        out.append(Model(str(m.get("modelKey") or m.get("path") or "?"), m.get("maxContextLength"), info, m))
    return out


def _date(ts) -> str:
    import time
    try:
        return time.strftime("%Y-%m-%d", time.gmtime(int(ts)))
    except (ValueError, OverflowError, OSError):
        return str(ts)


def fetch(name: str, endpoint: str = "http://127.0.0.1:1234/v1") -> list[Model]:
    """Live model list for a provider name, or for `local` (the server at `endpoint`)."""
    if name == "local":
        base = endpoint.rstrip("/")
        u = urlparse(base)
        downloaded = _lms_downloaded()              # everything on disk, without loading or even starting the server
        try:                                        # LM Studio's server listing adds what is loaded now, and the loaded context
            served = _lmstudio(_get(f"{u.scheme}://{u.netloc}/api/v0/models", {}))
        except ModelsError:
            try:
                served = _openai(_get(base + "/models", {}))
            except ModelsError as e:
                if downloaded is None:
                    raise ModelsError(f"{e}; and LM Studio's `lms` command was not found, so the downloaded models cannot be listed either") from None
                return downloaded
        if downloaded is None:
            return served
        live = {m.id: m for m in served}
        for m in downloaded:
            if m.id in live and live[m.id].info.get("state") == "loaded":
                m.info["state"] = "loaded"
                if live[m.id].context:
                    m.context = live[m.id].context
        return downloaded
    if name in providers.LOCAL:
        srv = providers.LOCAL[name]
        return fetch("local", srv.base_url) if name == "lmstudio" else _openai(_get(srv.base_url.rstrip("/") + "/models", {}))
    p = providers.get(name)
    key, _ = keys.lookup(name, p.key_env)
    if not key:
        raise ModelsError(f"no API key for {name}: run `gruntly auth set {name}` (or set {p.key_env})")
    if p.models_api == "gemini":
        root = p.base_url.split("/v1beta")[0]
        return _gemini(_get(f"{root}/v1beta/models?pageSize=1000", {"x-goog-api-key": key}))
    return _openai(_get(p.base_url.rstrip("/") + "/models", {"Authorization": f"Bearer {key}"}))


CACHE_S = 24 * 3600


def cache_path(name: str):
    from .store import state_dir
    return state_dir() / "models" / f"{name}.json"


def fetch_cached(name: str, endpoint: str = "http://127.0.0.1:1234/v1", refresh: bool = False, max_age_s: int = CACHE_S,
                 now: float | None = None) -> tuple[list[Model], float | None]:
    """A hosted provider's list, from a day-old copy when there is one (model lists change slowly and cost a call), else live. Returns
    (models, age in seconds or None for a live list). Local servers are always live: what is loaded changes by the minute."""
    import time
    now = time.time() if now is None else now
    if name == "local" or name in providers.LOCAL:
        return fetch(name, endpoint), None
    path = cache_path(name)
    if not refresh and path.is_file():
        try:
            d = json.loads(path.read_text(encoding="utf8"))
            if now - d["ts"] < max_age_s:
                return [Model(m["id"], m.get("context"), m.get("info") or {}, m.get("raw") or {}) for m in d["models"]], now - d["ts"]
        except (OSError, ValueError, KeyError, TypeError):
            pass
    ms = fetch(name, endpoint)
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({"ts": now, "models": [{"id": m.id, "context": m.context, "info": m.info, "raw": m.raw} for m in ms]}), encoding="utf8")
    except OSError:
        pass                                  # a cache that cannot be written is not an error
    return ms, None


def line(m: Model, width: int = 100, price: str | None = None) -> str:
    """One display line: id, context, then the facts the endpoint gave, then the price when it is known (the listing's own price fact is
    replaced by it, so it is not said twice)."""
    ctx = f"{m.context:,} ctx" if m.context else ""
    facts = " · ".join(f"{k}: {v}" if not isinstance(v, bool) else k for k, v in m.info.items() if not (price and k == "price"))
    return (f"{m.id}" + (f"  [{ctx}]" if ctx else "") + (f"  {facts}" if facts else "")[:width + 60]
            + (f"  | {price}" if price else ""))
