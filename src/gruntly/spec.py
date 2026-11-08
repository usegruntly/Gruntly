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
        "regression": None,
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
    "apply_on_pass": False,
    "holdout": None,
    "min_context": None,           # None = the profile's floor (typist 8k, worker 16k, default 32k)
    "allow_small_ctx": False,
    "profile": "auto",             # auto | typist | worker | default (see profiles.py)
    "inline_files": "auto",        # embed the target files in the prompt: auto | true | false
    "followup": False,             # a follow-up on work already in the tree: the tests are expected to pass before the change
    "self_check": False,           # True lets the child run the acceptance command itself; False = evaluate & fix
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
    apply_on_pass: bool = False
    holdout: Any = None            # {files: [...], cmd: "..."}: parent-written tests the child never sees
    min_context: int | None = None
    allow_small_ctx: bool = False
    profile: str = "auto"
    inline_files: Any = "auto"
    self_check: bool = False
    followup: bool = False

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
    merged.pop("do", None)  # the `[do]` table in .gruntly.toml configures `gruntly do`, not a task spec
    brief = merged.pop("brief", None)
    if not isinstance(brief, str) or not brief.strip():
        raise SpecError("'brief' is required")
    unknown = set(merged) - set(Spec.__dataclass_fields__)
    if unknown:
        raise SpecError(f"unknown spec fields: {sorted(unknown)}")
    spec = Spec(brief=brief.strip(), **merged)
    _validate(spec)
    if spec.holdout and repo_root is not None:
        _check_holdout(spec.holdout, repo_root)
    return spec


def _check_holdout(h: dict, repo_root: Path) -> None:
    """Fail before the child runs, not at gating: a bad holdout path would waste the whole attempt."""
    root = Path(repo_root).resolve()
    for f in h["files"]:
        p = (root / f).resolve()
        if not p.is_relative_to(root):
            raise SpecError(f"holdout file {f!r} is outside the repo. Put it inside the repo (untracked is fine, "
                            f"e.g. tests/holdout_x.py): gruntly keeps it out of the child's worktree and removes it after gating.")
        if not p.is_file():
            raise SpecError(f"holdout file {f!r} does not exist")


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
    if s.profile not in ("auto", "typist", "worker", "default"):
        raise SpecError("profile must be auto, typist, worker or default")
    if s.inline_files not in ("auto", True, False):
        raise SpecError("inline_files must be auto, true or false")
    if s.holdout is not None:
        h = s.holdout
        if not isinstance(h, dict) or not h.get("cmd") or not _as_list(h.get("files")):
            raise SpecError("holdout needs {files: [...], cmd: '...'}")
        s.holdout = {"files": [str(f) for f in _as_list(h["files"])], "cmd": str(h["cmd"])}
    if s.harness == "generic" and not s.child_cmd:
        raise SpecError("harness 'generic' needs child_cmd")
