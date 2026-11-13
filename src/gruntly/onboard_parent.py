"""Choosing the parent: `gruntly parent` (show or set, no terminal needed) and the interactive step `gruntly setup` ends with.

The parent is the harness that reads your task and directs gruntly (delegating) or does the job itself (working). It is saved as the `[parent]` table of
your global settings or the project's `.gruntly.toml`, the table `gruntly agent` reads (`harness`, `mode`, `provider`, `model`). Everything shown comes
from the registries (`parents`, `matrix`, `providers`): which harnesses exist, which are installed, what each can do of the lean setup, and which providers
each can use. Nothing is ranked, and a choice that cannot work is refused with the reason before it is saved.
"""
from __future__ import annotations

import re
import tomllib
from pathlib import Path

from . import keys, matrix, onboard, parents, providers
from .spec import global_config_path

TABLE = "parent"
FIELDS = ("harness", "mode", "provider", "model")


def _fmt(v: str) -> str:
    import json
    return json.dumps(str(v))            # a JSON string is a valid TOML basic string


def set_table_values(path: Path, table: str, values: dict) -> None:
    """Set keys inside `[table]` of a TOML file without disturbing anything else; a value of None removes the key; the table is added at the end if it is missing.
    Only the exact table `[table]` is touched, never `[table.sub]`."""
    lines = path.read_text(encoding="utf8").splitlines() if path.is_file() else []
    hdr = re.compile(rf"^\s*\[\s*{re.escape(table)}\s*\]\s*(#.*)?$")
    start = next((i for i, ln in enumerate(lines) if hdr.match(ln)), None)
    if start is None:
        body = [f"{k} = {_fmt(v)}" for k, v in values.items() if v is not None]
        if body:
            lines += ([""] if lines and lines[-1].strip() else []) + [f"[{table}]"] + body
    else:
        end = next((i for i in range(start + 1, len(lines)) if lines[i].lstrip().startswith("[")), len(lines))
        block = lines[start + 1:end]
        for key, val in values.items():
            pat = re.compile(rf"^\s*{re.escape(key)}\s*=")
            idx = next((i for i, ln in enumerate(block) if pat.match(ln)), None)
            if val is None:
                if idx is not None:
                    del block[idx]
            elif idx is not None:
                block[idx] = f"{key} = {_fmt(val)}"
            else:
                at = len(block)
                while at > 0 and not block[at - 1].strip():
                    at -= 1
                block.insert(at, f"{key} = {_fmt(val)}")
        lines[start + 1:end] = block
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf8")


def validate(harness: str, mode: str | None = None, provider: str | None = None) -> None:
    """Refuse, with the reason, a choice that cannot work."""
    if harness not in parents.names():
        raise ValueError(f"unknown parent harness {harness!r}; known: {', '.join(parents.names())}")
    caps = parents.get_parent(harness).capabilities()
    if mode and mode not in caps.modes:
        raise ValueError(f"{harness} cannot run in {mode} mode (it can: {', '.join(caps.modes)}); {'; '.join(caps.notes[:1])}")
    if provider:
        p = providers.ALL.get(provider)
        if p is None:
            raise ValueError(f"unknown provider {provider!r}; known: {', '.join(providers.ALL)}")
        if matrix.compatible(harness, p) == "no":
            proto = matrix.PROTOCOL.get(harness, "?")
            raise ValueError(f"{harness} cannot use {provider}: it speaks the {proto} API"
                             + (" and only works through your own login" if proto == "anthropic" else f", which {provider} does not serve"))


def save(harness: str, mode: str | None = None, provider: str | None = None, model: str | None = None, scope: str = "project") -> Path:
    validate(harness, mode, provider)
    proj = onboard.project_config()
    path = global_config_path() if scope == "global" or proj is None else proj
    set_table_values(path, TABLE, {"harness": harness, "mode": mode, "provider": provider, "model": model})
    return path


def current(root=None) -> dict:
    """What `gruntly agent` would launch with nothing else said: flags absent, settings applied, the first installed delegating parent otherwise."""
    return parents.resolve(root=root)


def candidates() -> list[dict]:
    rows = []
    for r in matrix.build()["harnesses"]:
        p = r["parent"]
        if p:
            rows.append({"name": r["harness"], "installed": p["installed"], "delegating": p["delegating"], "working": p["working"], "protocol": r["protocol"],
                         "experimental": p["experimental"], "checked": p["checked"]})
    return rows


def show() -> str:
    cur = current(onboard.project_config().parent if onboard.project_config() else None)
    out = [f"Parent: harness = {cur['parent']}, mode = {cur['mode']}, provider = {cur['provider'] or '(the harness\'s own login)'}, model = {cur['model'] or '(its default)'}", ""]
    out.append(f"{'HARNESS':9} {'INSTALLED':10} {'DELEGATING':56} WORKING  CHECKED")
    for c in candidates():
        out.append(f"{c['name']:9} {'yes' if c['installed'] else 'no':10} {(c['delegating'] + (' (experimental)' if c['experimental'] else ''))[:56]:56} "
                   f"{'yes' if c['working'] else '-':8} {c['checked']}")
    out += ["", "Set it:  gruntly parent set HARNESS [--mode delegating|working] [--provider P --model M] [--global|--project]", "Compare everything:  gruntly harness matrix"]
    return "\n".join(out)


# ------------------------------------------------------------------------------------------------------ suggesting
LEAN_PARENTS = ("opencode", "qwen", "codex", "gemini")          # after Claude Code, in the order gruntly has most evidence for them
CHILD_ORDER = ("opencode", "qwen", "hermes")                   # the children gruntly benchmarked; codex, gemini and aider follow when nothing else is there
OTHER_CHILDREN = ("codex", "gemini", "aider")


def gather() -> dict:
    """What is on this machine: which parent and child harnesses are installed, which providers have a key (never the key), whether the local server answers."""
    from . import doctor
    from .adapters.base import get_adapter
    return {"parents": {n: parents.get_parent(n).detect().installed for n in parents.names() if n not in parents.NOT_AUTO},
            "children": {n: get_adapter(n).detect().installed for n in matrix.CHILD_NAMES if n not in matrix.NO_CHILD},
            "keys": {p.name: bool(keys.lookup(p.name, p.key_env)[0]) for p in providers.ALL.values() if p.kind == "hosted"},
            "local_up": bool(doctor.probe_endpoint(onboard.LOCAL_DEFAULT_ENDPOINT, timeout=1.5)["ok"])}


def _usable(harness: str, f: dict) -> list:
    """Providers this harness can use right now: a hosted one with a key, or the local server when it answers; ones whose API support is only unknown come last."""
    out = [p for p in providers.ALL.values() if (f["keys"].get(p.name) if p.kind == "hosted" else (f["local_up"] and p.name == "lmstudio")) and matrix.compatible(harness, p) != "no"]
    return sorted(out, key=lambda p: matrix.compatible(harness, p) != "yes")


def suggest(f: dict) -> dict:
    """A parent and a child that fit what is here, each with the reason, and what is missing when nothing fits. It names evidence, it does not rank models."""
    s: dict = {"parent": None, "child": None, "missing": []}
    if f["parents"].get("claude"):
        s["parent"] = {"harness": "claude", "mode": "delegating", "provider": None,
                       "reason": "Claude Code is installed, and it is the parent gruntly has measured live (the plugin, and `gruntly agent` for the same lean setup)"}
    else:
        for h in LEAN_PARENTS:
            if not f["parents"].get(h):
                continue
            usable = _usable(h, f)
            if usable:
                u = usable[0]
                s["parent"] = {"harness": h, "mode": "delegating", "provider": u.name,
                               "reason": f"{h} is installed and has a lean delegating setup checked against its real binary; {u.name} "
                                         + ("has a key" if u.kind == "hosted" else "is the local server that answers")
                                         + ("" if matrix.compatible(h, u) == "yes" else " (whether it serves this harness's API is not confirmed)")
                                         + f"; pick a model with `gruntly models {u.name}`"}
                break
            s["missing"].append(f"{h} is installed but has no provider it can use: set a key (`gruntly auth set openrouter`, or `gemini` for Gemini CLI) or start the local server")
        if s["parent"] is None:
            keyed = [p for p in providers.ALL.values() if p.kind == "hosted" and f["keys"].get(p.name)]
            if keyed:
                why = "no installed parent harness can use a provider you have a key for" if s["missing"] else "no parent harness is installed"
                s["parent"] = {"harness": "direct", "mode": "delegating", "provider": keyed[0].name,
                               "reason": f"{why}, but {keyed[0].name} has a key: the built-in direct loop needs no install (the model must support tool calls)"}
            else:
                s["missing"].append("no parent: install one (`npm i -g opencode-ai`, `npm i -g @openai/codex`, Claude Code) or set a provider key (`gruntly auth set openrouter`)")
    installed_children = [h for h in (*CHILD_ORDER, *OTHER_CHILDREN) if f["children"].get(h)]
    if f["local_up"] and installed_children:
        s["child"] = {"harness": installed_children[0], "provider": "local",
                      "reason": f"{installed_children[0]} is installed and the local model server answers: the child costs no API dollars (compute is not priced)"}
    else:
        free = [p for p in providers.ALL.values() if p.kind == "hosted" and p.free_tier and f["keys"].get(p.name)]
        usable = [h for h in installed_children if free and matrix.compatible(h, free[0]) != "no"]
        if free and usable:
            s["child"] = {"harness": usable[0], "provider": free[0].name,
                          "reason": f"{usable[0]} is installed and {free[0].name} has a key and a free tier (limited: expect rate limits; a hosted provider counts as possibly paid)"}
        elif f["children"].get("claude"):
            s["child"] = {"harness": "claude", "provider": None,
                          "reason": "Claude Code is installed: a Haiku child works (measured live) but it is paid, it runs in your Claude usage"}
        else:
            s["missing"].append("no child: install one (`npm i -g opencode-ai`, `npm i -g @qwen-code/qwen-code`) and start a local model server (LM Studio), or set a free-tier key (`gruntly auth set gemini`)")
    return s


def render_suggestion(s: dict) -> str:
    out = []
    if s["parent"]:
        p = s["parent"]
        out.append(f"Parent: {p['harness']} ({p['mode']}" + (f", provider {p['provider']}" if p["provider"] else "") + f")\n  why: {p['reason']}")
    if s["child"]:
        c = s["child"]
        out.append(f"Child:  {c['harness']}" + (f" on {c['provider']}" if c["provider"] else "") + f"\n  why: {c['reason']}")
    out += [f"Missing: {m}" for m in s["missing"]]
    return "\n".join(out) if out else "Nothing to suggest."


def apply_suggestion(s: dict, scope: str = "project") -> list[str]:
    """Save what was suggested: the `[parent]` table and the child harness (and the child's provider when it is a hosted one). Returns where it was saved."""
    saved = []
    if s["parent"]:
        p = s["parent"]
        saved.append(str(save(p["harness"], p["mode"], p["provider"], None, scope)))
    if s["child"]:
        c = s["child"]
        saved.append(str(onboard.save_harness(c["harness"], scope)))
        if c["provider"] and c["provider"] != "local":
            onboard.save_choice(c["provider"], None, scope)
    return saved


# ------------------------------------------------------------------------------------------------------ interactive
def choose_harness(cur: str | None) -> str | None:
    rows = candidates()
    onboard.say("\nWhich harness should read your tasks and direct gruntly (the parent)?")
    for i, c in enumerate(rows, 1):
        mark = "  <- current" if c["name"] == cur else ""
        onboard.say(f"  {i}. {c['name']:9} {'installed' if c['installed'] else 'not installed':14} delegating: {c['delegating'][:48]}{mark}")
    while True:
        v = onboard.ask("Number or name (Enter to skip): ")
        if not v:
            return None
        if v.isdigit() and 1 <= int(v) <= len(rows):
            return rows[int(v) - 1]["name"]
        if v in [c["name"] for c in rows]:
            return v
        onboard.say("  Not one of the options.")


def choose_mode(harness: str) -> str:
    modes = parents.get_parent(harness).capabilities().modes
    if len(modes) == 1:
        onboard.say(f"  {harness} can only run in {modes[0]} mode.")
        return modes[0]
    v = onboard.ask("Mode: [d]elegating (the parent directs gruntly: the cheap setup) or [w]orking (the parent does the job itself)? (Enter = d): ", "d").lower()
    return "working" if v.startswith("w") else "delegating"


def choose_provider(harness: str) -> str | None:
    usable = [p for p in providers.ALL.values() if matrix.compatible(harness, p) != "no"]
    own = harness != "direct"                     # every harness but the built-in loop can use its own login (a delegating Codex, Gemini or Hermes will say it needs a provider)
    onboard.say(f"\nWhich provider should the parent's model come from? ({harness} speaks the {matrix.PROTOCOL.get(harness)} API)")
    for i, p in enumerate(usable, 1):
        flag = matrix.compatible(harness, p)
        has = "key found" if p.kind == "local" or keys.lookup(p.name, p.key_env)[0] else "no key yet"
        onboard.say(f"  {i:2}. {p.name:11} {p.kind:7} {has:11} {'(not confirmed: documentation unknown)' if flag == 'unknown' else ''}")
    onboard.say("  Enter = the harness's own login" if own else "  (this harness needs a provider)")
    while True:
        v = onboard.ask("Number or name: ")
        if not v:
            return None
        if v.isdigit() and 1 <= int(v) <= len(usable):
            return usable[int(v) - 1].name
        if v in [p.name for p in usable]:
            return v
        onboard.say("  Not one of the options.")


def step() -> None:
    """The optional last step of `gruntly setup`: pick the parent. Skippable; the same thing is `gruntly parent set`."""
    onboard.say("\nOptional: the parent harness (the agent that reads your tasks and directs gruntly)")
    try:
        onboard.say("Looking at what is here...\n" + render_suggestion(suggest(gather())) + "\n")
    except Exception as e:  # noqa: BLE001 - a suggestion must never stop the guide
        onboard.say(f"(no suggestion: {e})")
    if not onboard.ask("Set it up now? Claude Code is the default. [y/N]: ", "n").lower().startswith("y"):
        onboard.say("Skipped. `gruntly parent` shows and sets it any time.")
        return
    cur = current()["parent"]
    h = choose_harness(cur)
    if h is None:
        return
    mode = choose_mode(h)
    provider = choose_provider(h)
    model = None
    if provider and provider != "local":
        if not onboard.ensure_key(provider):
            onboard.say(f"No key, so {provider} was not set up. Run `gruntly auth set {provider}` when you have one.")
            return
        model = onboard.choose_model(provider, "")
    elif provider:
        model = onboard.ask("Model id (Enter = whatever the server has loaded): ") or None
    try:
        path = save(h, mode, provider, model, onboard.choose_scope())
    except ValueError as e:
        onboard.say(f"Not saved: {e}")
        return
    onboard.say(f"Saved to {path}: [parent] harness = {h}, mode = {mode}" + (f", provider = {provider}" if provider else "") + (f", model = {model}" if model else ""))
    onboard.say("Run it with:  gruntly agent \"your task\"")


# ------------------------------------------------------------------------------------------------------ the command
def cmd_parent(a) -> int:
    import sys
    if a.action in (None, "show"):
        print(show())
        return 0
    if a.action == "set":
        if not a.harness:
            print("usage: gruntly parent set HARNESS [--mode ...] [--provider ...] [--model ...]", file=sys.stderr)
            return 2
        try:
            path = save(a.harness, a.mode, a.provider, a.model, "global" if a.global_ else "project")
        except ValueError as e:
            print(f"not saved: {e}", file=sys.stderr)
            return 2
        print(f"Saved to {path}: [parent] harness = {a.harness}" + (f", mode = {a.mode}" if a.mode else "") + (f", provider = {a.provider}" if a.provider else "")
              + (f", model = {a.model}" if a.model else ""))
        return 0
    if a.action == "suggest":
        s = suggest(gather())
        print(render_suggestion(s))
        if not getattr(a, "apply", False):
            print("\nApply it:  gruntly parent suggest --apply   (saves the parent and the child harness; models stay for you to pick)")
            return 0
        if not (s["parent"] or s["child"]):
            return 2
        for path in apply_suggestion(s, "global" if a.global_ else "project"):
            print(f"Saved to {path}")
        print("Pick models with `gruntly models PROVIDER`, then `gruntly parent set HARNESS --provider P --model M` (and `gruntly use` for the child).")
        return 0
    if a.action == "clear":
        proj = onboard.project_config()
        path = global_config_path() if a.global_ or proj is None else proj
        set_table_values(path, TABLE, {k: None for k in FIELDS})
        print(f"Cleared [parent] in {path}")
        return 0
    return 2


def read_table(path: Path) -> dict:
    try:
        t = tomllib.loads(path.read_text(encoding="utf8")).get(TABLE)
    except (OSError, tomllib.TOMLDecodeError):
        return {}
    return t if isinstance(t, dict) else {}
