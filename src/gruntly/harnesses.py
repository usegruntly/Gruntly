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


HARNESSES: dict[str, Harness] = {h.name: h for h in (
    Harness("opencode", "OpenCode",
            "Best supported: full tool trace, token counts and session resume.",
            "Light: about 10.8k input tokens on the first request of a trivial task.",
            "npm i -g opencode-ai", "https://opencode.ai/docs", "sst/opencode", True),
    Harness("qwen", "Qwen Code",
            "Built around Qwen models, so a good match for local Qwen. Tool trace, token counts and resume.",
            "Heavier: about 14k input tokens plus a ~7k memory-extractor request on a trivial task.",
            "npm i -g @qwen-code/qwen-code", "https://qwenlm.github.io/qwen-code-docs/en/users/overview", "QwenLM/qwen-code", True),
    Harness("hermes", "Hermes Agent",
            "Broadest agent: about 18 built-in tools, memory and skills. In gruntly it runs with its tools as shipped.",
            "Heaviest per request (large prompt, about 18 tools). No tool trace, token counts or live view yet.",
            "uv tool install hermes-agent  (Windows: the Hermes installer, or WSL2)",
            "https://hermes-agent.nousresearch.com", "NousResearch/hermes-agent", False),
    Harness("claude", "Claude Code",
            "A cheaper Claude (Haiku by default) does the work a dearer parent hands over. Paid: it runs in your Claude usage and the block says how much.",
            "Haiku measured at $0.004 to $0.009 for a small task; a call has no local model server to start. Never picked by auto.",
            "already installed if you use Claude Code", "https://docs.claude.com/en/docs/claude-code", "anthropics/claude-code", False),
    Harness("codex", "Codex CLI",
            "OpenAI's agent, run as shipped. It speaks only the Responses API, so gruntly puts a small bridge in front of your endpoint (any chat provider or local server) that translates; a provider that serves Responses is used directly. Token counts; no resume.",
            "Heavy: about 19,500 characters of instructions and nine tools on every request.",
            "npm i -g @openai/codex", "https://developers.openai.com/codex/cli", "openai/codex", False),
    Harness("gemini", "Gemini CLI",
            "Google's agent. gruntly runs it as shipped through a small local bridge that turns its Gemini-API requests into chat completions for your endpoint (local server or hosted provider), tool calls included. Token counts; no resume.",
            "Heavy: about 30,400 characters of system prompt and 15 tools on every request; wants a 32k context or more.",
            "npm i -g @google/gemini-cli", "https://geminicli.com/docs", "google-gemini/gemini-cli", False),
    Harness("aider", "Aider",
            "Edits the files it is given with a plain chat, so it works with small models that cannot call tools. In gruntly its history, repo map and commits are kept out of the tree. Token counts; no resume.",
            "Light: no tool list; the repo map is off, so the brief has to name the files.",
            "python -m pip install aider-chat", "https://aider.chat/docs", "Aider-AI/aider", False),
    Harness("generic", "Any other agent CLI",
            "Bring your own: gruntly runs the command you give (child_cmd) and checks the result. No resume or trace.",
            "Whatever that tool costs.", "set child_cmd in the spec", "https://github.com/usegruntly/Gruntly/blob/main/docs/adapters.md", "", False),
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
