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
    "harness": "qwen",
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
        "lint": None,
        "typecheck": None,
    },
    "max_attempts": 3,
    "budget_s": 900,
    "no_progress_s": 120,
    "base": "working-tree",
    "child_cmd": None,
    "endpoint": "http://127.0.0.1:1234/v1",
    "api_key": "local",
    "sandbox_level": 0,
    "max_concurrency": 1,
    "env_allow": [],
}
HARNESSES = ("qwen", "opencode", "hermes", "generic")


class SpecError(ValueError):
    pass


@dataclass
class Spec:
    brief: str
    id: str | None = None
    kind: str = "code"
    harness: str = "qwen"
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
    base: str = "working-tree"
    child_cmd: Any = None
    endpoint: str = "http://127.0.0.1:1234/v1"
    api_key: str = "local"
    sandbox_level: int = 0
    max_concurrency: int = 1
    env_allow: list[str] = field(default_factory=list)

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
    brief = merged.pop("brief", None)
    if not isinstance(brief, str) or not brief.strip():
        raise SpecError("'brief' is required")
    unknown = set(merged) - set(Spec.__dataclass_fields__)
    if unknown:
        raise SpecError(f"unknown spec fields: {sorted(unknown)}")
    spec = Spec(brief=brief.strip(), **merged)
    _validate(spec)
    return spec


def _validate(s: Spec) -> None:
    if s.harness not in HARNESSES:
        raise SpecError(f"harness must be one of {HARNESSES}")
    if s.base not in ("head", "working-tree"):
        raise SpecError("base must be 'head' or 'working-tree'")
    if s.kind not in ("code", "research"):
        raise SpecError("kind must be 'code' or 'research'")
    if s.max_attempts < 1:
        raise SpecError("max_attempts must be >= 1")
    norm = []
    for a in s.acceptance or []:
        if isinstance(a, str):
            a = {"cmd": a}
        if not isinstance(a, dict) or not a.get("cmd"):
            raise SpecError("each acceptance entry needs a 'cmd'")
        norm.append({"cmd": str(a["cmd"]), "timeout_s": int(a.get("timeout_s", 300))})
    s.acceptance = norm
    if s.kind == "code" and not norm:
        raise SpecError("code tasks need at least one acceptance command")
    if s.harness == "generic" and not s.child_cmd:
        raise SpecError("harness 'generic' needs child_cmd")
