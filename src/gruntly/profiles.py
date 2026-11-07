"""Child profiles: how much of the harness a task gets.

A coding-agent CLI ships a large system prompt and a dozen tool schemas (~11k input tokens per request for a
trivial task), which a 9B local model pays for on every request. A profile replaces that with just what the task
needs:

  typist   the parent supplied everything. Small prompt; the target files are inlined so the model's first action
           is a write; the whole-file write tool replaces the edit tool when the files are small.
  worker   the child may explore (list, search, read), plan and edit. Longer prompt, more tools.
  default  the harness as shipped (the control arm).
  auto     typist when the scope is a few small, literally named files; otherwise worker.

Tool names here are logical (read, write, edit, list, search, test); each adapter maps them to its harness's tools.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

from . import worktree as wtmod
from .gates import matches_any

PROFILES = ("auto", "typist", "worker", "default")
GLOB = re.compile(r"[*?\[]")
MAX_TYPIST_FILES = 3          # target files for auto -> typist
MAX_TYPIST_LINES = 240        # total lines of target + context files for auto -> typist
REWRITE_MAX_LINES = 80        # per file; above this the edit tool stays (a whole-file rewrite can drop content)
INLINE_MAX_CHARS = 12_000     # ~3k tokens of file text in the prompt
FLOORS = {"typist": 8_192, "worker": 16_384, "default": 32_768}  # minimum model context per profile


@dataclass
class ResolvedProfile:
    name: str                                   # typist | worker | default
    tools: list[str] = field(default_factory=list)   # logical tool names; empty means "harness defaults"
    targets: list[str] = field(default_factory=list)  # files the child may change (existing or to be created)
    context: list[str] = field(default_factory=list)  # extra files to show
    rewrite_only: bool = False                  # whole-file write instead of edit
    inline: bool = False                        # embed file contents in the prompt
    self_check: bool = False                    # child may run the acceptance command (else gruntly evaluates and feeds errors back)


def _denied(spec, path: str) -> bool:
    return matches_any(path, spec.deny_paths) or path.split("/")[-1].startswith(".env")


def _files(tree: Path) -> list[str]:
    out = wtmod.git(["ls-files", "-co", "--exclude-standard"], tree, check=False).stdout.splitlines()
    return [p for p in out if p]


def _lines(path: Path) -> int:
    try:
        return len(path.read_text(encoding="utf8").splitlines())
    except (OSError, UnicodeDecodeError):
        return 10**9  # binary or unreadable: never counts as small


def targets_of(spec, tree: Path) -> list[str]:
    """Files the child may change: tracked/untracked files matching allowed_paths, plus literal paths to create."""
    found = [p for p in _files(tree) if matches_any(p, spec.allowed_paths) and not _denied(spec, p)]
    for pat in spec.allowed_paths:
        if not GLOB.search(pat) and pat not in found and not _denied(spec, pat):
            found.append(pat)
    return found


def tools_for(name: str, rewrite_only: bool, inline: bool, self_check: bool) -> list[str]:
    test = ["test"] if self_check else []
    if name == "typist":
        return ["write"] + test + ([] if inline else ["read"]) + ([] if rewrite_only else ["edit"])
    if name == "worker":
        return ["read", "write", "edit", "list", "search"] + test
    return []


def resolve(spec, tree: Path, name: str | None = None) -> ResolvedProfile:
    """Pick the profile for this task. `name` forces one (used when continuing a run)."""
    want = name or getattr(spec, "profile", "auto")
    if want == "default":
        return ResolvedProfile("default")
    targets = targets_of(spec, tree)
    context = [f for f in spec.context_files if (tree / f).is_file() and not _denied(spec, f) and f not in targets]
    sizes = {f: _lines(tree / f) for f in targets + context if (tree / f).is_file()}
    if want == "auto":
        literal = all(not GLOB.search(p) for p in spec.allowed_paths)
        small = len(targets) <= MAX_TYPIST_FILES and sum(sizes.values()) <= MAX_TYPIST_LINES
        want = "typist" if (literal and targets and small) else "worker"
    rewrite_only = want == "typist" and all(sizes.get(t, 0) <= REWRITE_MAX_LINES for t in targets)
    flag = getattr(spec, "inline_files", "auto")
    inline = (want == "typist") if flag == "auto" else bool(flag)
    check = bool(getattr(spec, "self_check", False))
    return ResolvedProfile(want, tools_for(want, rewrite_only, inline, check), targets, context, rewrite_only, inline, check)


def context_floor(spec, name: str) -> int:
    return spec.min_context if spec.min_context else FLOORS.get(name, FLOORS["default"])


def inline_block(spec, rp: ResolvedProfile, tree: Path) -> str:
    """The current text of the files the child needs, so it can write immediately. Never denied/.env paths."""
    if not rp.inline:
        return ""
    parts, used = [], 0
    for f in [x for x in rp.targets if (tree / x).is_file()] + rp.context:
        p = tree / f
        if _denied(spec, f) or not p.is_file():
            continue
        try:
            text = p.read_text(encoding="utf8")
        except (OSError, UnicodeDecodeError):
            continue
        if used + len(text) > INLINE_MAX_CHARS:
            continue
        used += len(text)
        parts.append(f"FILE {f}\n```\n{text.rstrip()}\n```")
    new = [t for t in rp.targets if not (tree / t).is_file()]
    if new:
        parts.append("FILES TO CREATE: " + ", ".join(new))
    return "\n\n".join(parts)
