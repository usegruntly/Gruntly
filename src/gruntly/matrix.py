"""The harness x role x provider matrix: what each harness can be, what has been checked, and which providers each can use.

`gruntly harness matrix [--json]` prints it. It is built from the parent registry (`parents/`), the child adapters (`adapters/`) and the provider
catalog (`providers`), plus the small table of facts below that no code can know: which wire protocol a harness speaks, and what was checked, against
which version, and how. Nothing here says more than that: "stub" means the real binary was run against a stub model server (`gruntly/probe.py`:
no key, no cost) and its system prompt, tools and key were read off the requests it sent; "live" means a real model answered.
A test (`tests/unit/test_matrix.py`) fails when a registered harness has no row, so a new harness cannot be added without saying what it is.
"""
from __future__ import annotations

from . import parents, providers
from .adapters.base import get_adapter

# The wire protocol each harness speaks to its model. chat = OpenAI chat completions; responses = OpenAI Responses (Codex dropped the chat API);
# gemini = the Gemini API; anthropic = Anthropic's own (Claude Code, through your login); any = whatever the command you give uses.
PROTOCOL = {"claude": "anthropic", "opencode": "chat", "qwen": "chat", "hermes": "chat", "codex": "responses", "gemini": "gemini", "aider": "chat",
            "direct": "chat", "generic": "any"}

CHILD_NAMES = ("claude", "opencode", "qwen", "hermes", "codex", "gemini", "aider", "generic")
# Why a harness has no child role, where it has none.
NO_CHILD = {"direct": "the direct parent is a loop of gruntly's own with one tool, not an agent that edits files"}

# What was checked, against which version. (harness, role) -> text. "live" = a real model answered; "stub" = the real binary against probe.py.
CHECKED = {
    ("claude", "parent"): "live (Claude Code, many runs)", ("claude", "child"): "live 2026-11-12 (Haiku child, $1.54)",
    ("opencode", "parent"): "stub 1.19.5", ("opencode", "child"): "live 1.19.5 (docs/adapters.md)",
    ("qwen", "parent"): "stub 0.26.9", ("qwen", "child"): "live 0.26.9 (docs/adapters.md)",
    ("hermes", "parent"): "stub 0.23.0 (key delivery to a hosted provider unchecked)", ("hermes", "child"): "live 0.19.0 on Linux/WSL2 (docs/adapters.md)",
    ("codex", "parent"): "stub 0.167.2", ("codex", "child"): "stub 0.167.2",
    ("gemini", "parent"): "stub 0.68.0", ("gemini", "child"): "stub 0.68.0 through the bridge",
    ("aider", "parent"): "stub 0.86.2 (working mode only)", ("aider", "child"): "stub 0.86.2",
    ("direct", "parent"): "stub (the loop and the refusals; no live model yet)",
    ("generic", "parent"): "stub (a python one-liner as the harness)", ("generic", "child"): "unit tests",
}


def delegating_level(caps) -> str:
    """lean when the harness could be given the whole lean setup, else what is missing."""
    if "delegating" not in caps.modes:
        return "no"
    missing = [label for ok, label in ((caps.replace_system_prompt, "own prompt stays"), (caps.restrict_tools, "more than a shell tool"),
                                       (caps.restrict_shell, "any command can run"), (caps.disable_extensions, "extensions not switched off")) if not ok]
    return "lean" if not missing else "partial: " + ", ".join(missing)


def compatible(harness: str, provider: providers.Provider) -> str:
    """yes / no / unknown / own login: can `harness` use a model from `provider`?"""
    proto = PROTOCOL.get(harness, "any")
    if proto == "chat":
        return "yes"
    if proto == "responses":
        return {True: "yes", False: "no", None: "unknown"}[provider.responses_api]
    if proto == "gemini":
        return "yes" if provider.name == "gemini" else "no"
    if proto == "anthropic":
        return "no"                                    # only your own Claude login
    return "unknown"


def build() -> dict:
    names = list(dict.fromkeys([*parents.names(), *CHILD_NAMES]))
    rows = []
    for n in names:
        row: dict = {"harness": n, "protocol": PROTOCOL.get(n, "?")}
        if n in parents.names():
            a = parents.get_parent(n)
            c = a.capabilities()
            d = a.detect()
            row["parent"] = {"installed": d.installed, "version": d.version, "delegating": delegating_level(c), "working": "working" in c.modes,
                             "experimental": c.experimental, "reports_usage": c.reports_usage, "notes": list(c.notes), "checked": CHECKED.get((n, "parent"), "")}
        else:
            row["parent"] = None
        if n in CHILD_NAMES and n not in NO_CHILD:
            d = get_adapter(n).detect()
            row["child"] = {"installed": d.installed, "version": d.version, "checked": CHECKED.get((n, "child"), "")}
        else:
            row["child"] = None
            if n in NO_CHILD:
                row["child_reason"] = NO_CHILD[n]
        rows.append(row)
    grid = {p.name: {"kind": p.kind, "responses_api": p.responses_api, "verified": p.verified,
                     "harnesses": {n: compatible(n, p) for n in names}} for p in providers.ALL.values()}
    return {"harnesses": rows, "providers": grid}


def render(m: dict) -> str:
    out = ["Harness roles (parent = reads the task; child = does the edit). `lean` = the whole lean setup; checked = what was run, not what was read.", ""]
    w = max(len(r["harness"]) for r in m["harnesses"])
    out.append(f"{'HARNESS':{w}}  {'PROTOCOL':9} {'PARENT: delegating':62} {'working':8} {'CHILD':6} {'INSTALLED':12} CHECKED (parent | child)")
    for r in m["harnesses"]:
        p, c = r["parent"], r["child"]
        deleg = (p["delegating"] + (" (experimental)" if p["experimental"] else "")) if p else "-"
        inst = "/".join(x for x in (("parent" if p and p["installed"] else ""), ("child" if c and c["installed"] else "")) if x) or "no"
        out.append(f"{r['harness']:{w}}  {r['protocol']:9} {deleg[:62]:62} {('yes' if p and p['working'] else '-'):8} {('yes' if c else 'no'):6} {inst:12} "
                   f"{(p or {}).get('checked') or '-'} | {(c or {}).get('checked') or '-'}")
    out += ["", "Which providers each harness can use (yes / no / unknown / from the catalog's `responses_api`, which is documentation, not a live check):", ""]
    names = [r["harness"] for r in m["harnesses"]]
    out.append(f"{'PROVIDER':11} {'KIND':7} " + " ".join(f"{n[:8]:8}" for n in names))
    for pn, g in m["providers"].items():
        out.append(f"{pn:11} {g['kind']:7} " + " ".join(f"{g['harnesses'][n]:8}" for n in names))
    out += ["", "No child role: " + "; ".join(f"{n} ({why})" for n, why in NO_CHILD.items())]
    return "\n".join(out)
