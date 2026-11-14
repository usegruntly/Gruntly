"""Task spec parsing and config layering: defaults < global < project < spec."""
from __future__ import annotations

import os
import secrets
import time
import tomllib
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any

import yaml

DEFAULTS: dict[str, Any] = {
    "kind": "code",
    "harness": "auto",                 # auto = the first of opencode, qwen, hermes installed on this machine
    "model": None,
    "context_files": [],
    "allowed_paths": ["**"],
    "deny_paths": [".env*", ".github/**"],
    "tests_writable": False,
    "acceptance": [],
    "gates": {
        "scope": True,
        "diff_max_lines": 400,
        "no_test_weakening": True,
        "no_new_deps": True,
        "regression": None,
        "lint": None,
        "typecheck": None,
    },
    "max_attempts": 3,
    "budget_s": 900,
    "no_progress_s": 120,
    # Stuck detection (gruntly.escalation.Stall). Progress means a diff the child has not produced before. The two clocks never run
    # shorter than 2x and 3x no_progress_s, which gruntly already sizes to a slow model's own request time. 0 switches one off.
    "stall_s": 240,                # no new diff for this long after the child's first edit
    "first_edit_s": 420,           # no edit at all for this long (reading is fine, reading for ever is not)
    "max_calls": 80,               # tool calls in one attempt
    "base": "working-tree",
    "child_cmd": None,
    "endpoint": "http://127.0.0.1:1234/v1",
    "api_key": "local",
    "sandbox_level": 0,
    "max_concurrency": 1,
    "env_allow": [],
    "apply_on_pass": False,
    "min_context": None,           # None = MIN_CONTEXT: the child harness's own prompt and tools need that much room
    "allow_small_ctx": False,
    "followup": False,             # a follow-up on work already in the tree: the tests are expected to pass before the change
    "provider": "local",           # local = the model server at `endpoint`; or a hosted preset from providers.py (e.g. gemini)
    "rate_limits": {},             # override a provider preset: rpm, tpm, rpd
    "permissions": "inherit",      # child permission mode: inherit (env GRUNTLY_PARENT_MODE, else bypass) | bypass | accept-edits | plan
}
# The child always runs as its harness ships it: its own system prompt and all its tools. These older spec fields chose
# slimmer prompts and tool sets; they are accepted and ignored so existing configs keep working.
RETIRED_FIELDS = ("profile", "inline_files", "web", "self_check", "holdout", "hide")     # holdout/hide: removed 2026-11-14; old run records may still carry them
MIN_CONTEXT = 32_768
PERMISSION_MODES = ("inherit", "bypass", "accept-edits", "plan")
_CLAUDE_MODES = {"bypasspermissions": "bypass", "acceptedits": "accept-edits", "default": "accept-edits", "plan": "plan",
                "bypass": "bypass", "accept-edits": "accept-edits"}


def permission_mode(spec) -> str:
    """The child's permission mode: the parent's (GRUNTLY_PARENT_MODE, a Claude Code mode name) unless the spec fixes one."""
    import os
    m = getattr(spec, "permissions", "inherit")
    if m == "inherit":
        m = _CLAUDE_MODES.get(os.environ.get("GRUNTLY_PARENT_MODE", "").replace("_", "").lower(), "bypass")
    return m


HARNESSES = ("auto", "qwen", "opencode", "hermes", "claude", "codex", "gemini", "aider", "generic")


class SpecError(ValueError):
    pass


@dataclass
class Spec:
    brief: str
    id: str | None = None
    kind: str = "code"
    harness: str = "auto"
    model: str | None = None
    context_files: list[str] = field(default_factory=list)
    allowed_paths: list[str] = field(default_factory=lambda: ["**"])
    deny_paths: list[str] = field(default_factory=list)
    tests_writable: bool = False
    acceptance: list[dict] = field(default_factory=list)
    gates: dict = field(default_factory=dict)
    max_attempts: int = 3
    budget_s: int = 900
    no_progress_s: int = 120
    stall_s: int = 240
    first_edit_s: int = 420
    max_calls: int = 80
    base: str = "working-tree"
    child_cmd: Any = None
    endpoint: str = "http://127.0.0.1:1234/v1"
    api_key: str = "local"
    sandbox_level: int = 0
    max_concurrency: int = 1
    env_allow: list[str] = field(default_factory=list)
    apply_on_pass: bool = False
    min_context: int | None = None
    allow_small_ctx: bool = False
    followup: bool = False
    provider: str = "local"
    rate_limits: dict = field(default_factory=dict)
    permissions: str = "inherit"

    def to_dict(self) -> dict:
        return asdict(self)


def global_config_path() -> Path:
    base = os.environ.get("GRUNTLY_CONFIG_DIR")
    return (Path(base) if base else Path.home() / ".config" / "gruntly") / "config.toml"


def _toml(path: Path) -> dict:
    if not path.is_file():
        return {}
    try:
        return tomllib.loads(path.read_text(encoding="utf8"))
    except tomllib.TOMLDecodeError as e:
        raise SpecError(f"bad config {path}: {e}") from e


def _merge(base: dict, over: dict) -> dict:
    out = dict(base)
    for k, v in over.items():
        if k == "gates" and isinstance(v, dict):
            out["gates"] = {**out.get("gates", {}), **v}
        else:
            out[k] = v
    return out


def new_run_id() -> str:
    return f"r_{time.strftime('%Y%m%d')}_{secrets.token_hex(2)}"


def parse_spec_text(text: str) -> dict:
    try:
        data = yaml.safe_load(text)
    except yaml.YAMLError as e:
        raise SpecError(f"cannot parse spec: {e}") from e
    if not isinstance(data, dict):
        raise SpecError("spec must be a mapping with at least 'brief'")
    return data


def build_spec(raw: dict, repo_root: Path | None = None) -> Spec:
    merged = _merge(DEFAULTS, _toml(global_config_path()))
    if repo_root is not None:
        merged = _merge(merged, _toml(repo_root / ".gruntly.toml"))
    merged = _merge(merged, raw)
    from . import providers as provmod
    merged["provider"], merged["endpoint"] = provmod.resolve_local(merged.get("provider", "local"), merged.get("endpoint"), DEFAULTS["endpoint"])
    merged.pop("do", None)  # the `[do]` table in .gruntly.toml configures `gruntly do`, not a task spec
    merged.pop("escalate", None)  # likewise `[escalate]`: the policy for handing a stuck task to the caller's own model
    merged.pop("parent", None)    # and `[parent]`: which harness, model and mode `gruntly agent` launches
    for k in RETIRED_FIELDS:
        merged.pop(k, None)
    brief = merged.pop("brief", None)
    if not isinstance(brief, str) or not brief.strip():
        raise SpecError("'brief' is required")
    unknown = set(merged) - set(Spec.__dataclass_fields__)
    if unknown:
        raise SpecError(f"unknown spec fields: {sorted(unknown)}")
    spec = Spec(brief=brief.strip(), **merged)
    _validate(spec)
    return spec


def _as_list(v):
    """A bare string or mapping means a one-item list; iterating a string would split it into characters."""
    if v is None:
        return []
    return [v] if isinstance(v, (str, dict)) else list(v)


def _validate(s: Spec) -> None:
    for f in ("context_files", "allowed_paths", "deny_paths", "env_allow", "acceptance"):
        setattr(s, f, _as_list(getattr(s, f)))
    if s.harness not in HARNESSES:
        raise SpecError(f"harness must be one of {HARNESSES}")
    if s.base not in ("head", "working-tree"):
        raise SpecError("base must be 'head' or 'working-tree'")
    if s.kind not in ("code", "research"):
        raise SpecError("kind must be 'code' or 'research'")
    if s.kind == "research":       # a question makes no edit to wait for and none to stall on: the time budget is its limit
        s.stall_s = s.first_edit_s = 0     # (a research run was stopped 'no edit after 420s' while it was still measuring, 2026-11-14)
    if s.max_attempts < 1:
        raise SpecError("max_attempts must be >= 1")
    norm = []
    for a in s.acceptance:
        if isinstance(a, str):
            a = {"cmd": a}
        if not isinstance(a, dict) or not a.get("cmd"):
            raise SpecError("each acceptance entry needs a 'cmd'")
        norm.append({"cmd": str(a["cmd"]), "timeout_s": int(a.get("timeout_s", 300))})
    s.acceptance = norm
    if s.kind == "code" and not norm:
        raise SpecError("code tasks need at least one acceptance command")
    if s.provider != "local":
        from . import providers
        try:
            providers.get(s.provider)
        except ValueError as e:
            raise SpecError(str(e)) from None
    if not isinstance(s.rate_limits, dict) or set(s.rate_limits) - {"rpm", "tpm", "rpd"}:
        raise SpecError("rate_limits may only hold rpm, tpm and rpd")
    if s.permissions not in PERMISSION_MODES:
        raise SpecError("permissions must be one of " + ", ".join(PERMISSION_MODES))
    if s.harness == "generic" and not s.child_cmd:
        raise SpecError("harness 'generic' needs child_cmd")
