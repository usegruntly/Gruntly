"""Environment checks and the model-server probe used by preflight."""
from __future__ import annotations

import json
import shutil
import sys
import urllib.request
from urllib.parse import urlparse

from . import sandbox
from .adapters.base import get_adapter
from .spec import MIN_CONTEXT

MIN_CTX = 32_768
NO_SERVER = ("claude", "generic")      # no model server to probe: Claude Code uses your own login, a generic command brings its own model (the runner skips the probe too)


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


def run(endpoint: str, model: str | None = None, hosted: str | None = None, harness: str | None = None) -> dict:
    checks: list[dict] = []

    def add(name, ok, detail="", warn=False):
        checks.append({"check": name, "ok": ok, "warn": warn, "detail": detail})

    add("git", bool(shutil.which("git")), shutil.which("git") or "git not found")
    add("python", sys.version_info >= (3, 11), sys.version.split()[0])
    for h in ("qwen", "opencode", "hermes"):
        if h == harness:                         # the child this project uses gets the stricter check below
            continue
        d = get_adapter(h).detect()
        add(f"child:{h}", d.installed, (d.version or "") + (f" {d.detail}" if d.detail else ""), warn=not d.installed)
    if harness and harness != "generic":         # the child the project actually uses must be there: that is a failure, not a warning
        try:
            d = get_adapter(harness).detect()
            add(f"child:{harness}", d.installed, ((d.version or "") + (f" {d.detail}" if d.detail else "")).strip() or f"{harness} is not installed")
        except Exception as e:  # noqa: BLE001 - an unknown harness name is reported, not raised
            add(f"child:{harness}", False, f"unknown harness: {e}")
    p = {"ok": False}
    if harness in NO_SERVER:
        add("model_server", True, "not needed: " + ("Claude Code uses your own login" if harness == "claude" else "a generic child runs the command you gave it"))
    elif hosted:                                 # the project uses a hosted provider: the local server is not part of the run
        add("model_server", True, f"not needed: this project uses {hosted}" + (f" ({model})" if model else ""))
    else:
        p = probe_endpoint(endpoint)
        add("model_server", p["ok"], endpoint if p["ok"] else p["error"])
    if p["ok"]:
        if model:
            add("model_available", model in p["models"], model if model in p["models"] else f"{model} not listed: {p['models']}")
        for mid, n in p["ctx"].items():
            if model and mid != model:
                continue
            ok = n >= MIN_CONTEXT
            note = "" if ok else (f" (< {MIN_CONTEXT}: the child harness's own prompt and tools nearly fill it; reload the "
                                  "model with a larger context)")
            add("context_size", ok, f"{mid}: {n} tokens{note}", warn=not ok)
    ok1, why1 = sandbox.level_available(1)
    add("sandbox", True, f"level 0 always; level 1: {why1}", warn=not ok1)
    add("isolation_note", True, "level 0 is not a security boundary; auto-approve flags run shell unattended", warn=True)
    return {"ok": all(c["ok"] or c["warn"] for c in checks), "checks": checks}
