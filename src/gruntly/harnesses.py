"""The child-agent harnesses gruntly can drive, for the picker (`gruntly harness`).

The "in gruntly" lines are what gruntly itself measured or relies on (docs/adapters.md), not the vendors' marketing.
`gruntly harness --fetch` also shows each project's own one-line description, read live from its public GitHub page.
"""
from __future__ import annotations

import json
import urllib.request
from dataclasses import dataclass

from .adapters.base import get_adapter


@dataclass(frozen=True)
class Harness:
    name: str
    title: str
    good_at: str          # what sets it apart, as far as gruntly has seen
    cost: str             # weight, as measured
    install: str
    docs: str
    repo: str             # owner/name for the live description
    traced: bool          # gruntly shows its tool calls (child_trace and the live view)
    profiles: bool        # gruntly can slim its prompt and tools


HARNESSES: dict[str, Harness] = {h.name: h for h in (
    Harness("opencode", "OpenCode",
            "Best supported: full tool trace, token counts, session resume, slim profiles, and a shell limited to the acceptance command.",
            "Light: about 10.8k input tokens on the first request of a trivial task.",
            "npm i -g opencode-ai", "https://opencode.ai/docs", "sst/opencode", True, True),
    Harness("qwen", "Qwen Code",
            "Built around Qwen models, so a good match for local Qwen. Tool trace, token counts, resume, slim profiles.",
            "Heavier: about 14k input tokens plus a ~7k memory-extractor request on a trivial task.",
            "npm i -g @qwen-code/qwen-code", "https://qwenlm.github.io/qwen-code-docs/en/users/overview", "QwenLM/qwen-code", True, True),
    Harness("hermes", "Hermes Agent",
            "Broadest agent: about 18 built-in tools, memory and skills. In gruntly it runs with its tools as shipped.",
            "Heaviest per request (large prompt, no slim profile). No tool trace, token counts or live view yet.",
            "uv tool install hermes-agent  (Windows: inside WSL2, run gruntly there too)",
            "https://hermes-agent.nousresearch.com", "NousResearch/hermes-agent", False, False),
    Harness("generic", "Any other agent CLI",
            "Bring your own: gruntly runs the command you give (child_cmd) and checks the result. No resume, trace or profiles.",
            "Whatever that tool costs.", "set child_cmd in the spec", "https://github.com/usegruntly/Gruntly/blob/main/docs/adapters.md", "", False, False),
)}


def installed(name: str) -> tuple[bool, str | None]:
    d = get_adapter(name).detect()
    return d.installed, d.version


def live_description(h: Harness, timeout: float = 5.0) -> str | None:
    """The project's own description from the public GitHub API; None when offline or unavailable."""
    if not h.repo:
        return None
    req = urllib.request.Request(f"https://api.github.com/repos/{h.repo}", headers={"User-Agent": "gruntly"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return (json.load(r).get("description") or "").strip() or None
    except Exception:  # noqa: BLE001 - offline is fine
        return None
