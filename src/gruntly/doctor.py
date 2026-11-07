"""Environment checks and the model-server probe used by preflight."""
from __future__ import annotations

import json
import shutil
import sys
import urllib.request
from urllib.parse import urlparse

from . import sandbox
from .adapters.base import get_adapter
from .profiles import FLOORS

MIN_CTX = 32_768


def probe_endpoint(endpoint: str, timeout: float = 3.0) -> dict:
    """Returns {ok, models, ctx, error}. ctx comes from LM Studio's /api/v0/models when available."""
    base = endpoint.rstrip("/")
    try:
        with urllib.request.urlopen(base + "/models", timeout=timeout) as r:
            models = [m.get("id") for m in json.load(r).get("data", [])]
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "models": [], "ctx": {}, "error": f"model server unreachable at {endpoint}: {e}"}
    ctx: dict = {}
    u = urlparse(base)
    try:
        with urllib.request.urlopen(f"{u.scheme}://{u.netloc}/api/v0/models", timeout=timeout) as r:
            for m in json.load(r).get("data", []):
                if m.get("state") == "loaded" and m.get("loaded_context_length"):
                    ctx[m["id"]] = m["loaded_context_length"]
    except Exception:  # noqa: BLE001 - not LM Studio; context size stays unknown
        pass
    return {"ok": True, "models": models, "ctx": ctx, "error": None}


def run(endpoint: str, model: str | None = None) -> dict:
    checks: list[dict] = []

    def add(name, ok, detail="", warn=False):
        checks.append({"check": name, "ok": ok, "warn": warn, "detail": detail})

    add("git", bool(shutil.which("git")), shutil.which("git") or "git not found")
    add("python", sys.version_info >= (3, 11), sys.version.split()[0])
    for h in ("qwen", "opencode", "hermes"):
        d = get_adapter(h).detect()
        add(f"child:{h}", d.installed, (d.version or "") + (f" {d.detail}" if d.detail else ""), warn=not d.installed)
    p = probe_endpoint(endpoint)
    add("model_server", p["ok"], endpoint if p["ok"] else p["error"])
    if p["ok"]:
        if model:
            add("model_available", model in p["models"], model if model in p["models"] else f"{model} not listed: {p['models']}")
        for mid, n in p["ctx"].items():
            if model and mid != model:
                continue
            ok = n >= FLOORS["typist"]
            note = "" if n >= FLOORS["default"] else (
                f" (enough for the typist and worker profiles; the stock harness wants {FLOORS['default']})" if ok
                else f" (< {FLOORS['typist']}: too small even for the typist profile)")
            add("context_size", ok, f"{mid}: {n} tokens{note}", warn=n < FLOORS["default"])
    ok1, why1 = sandbox.level_available(1)
    add("sandbox", True, f"level 0 always; level 1: {why1}", warn=not ok1)
    add("isolation_note", True, "level 0 is not a security boundary; auto-approve flags run shell unattended", warn=True)
    return {"ok": all(c["ok"] or c["warn"] for c in checks), "checks": checks}
