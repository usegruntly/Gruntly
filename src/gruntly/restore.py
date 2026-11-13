"""`gruntly restore RUN`: put back what a child changed in your own working tree (issue #6).

A child works in a worktree, but a model that finds the path of the checkout the worktree came from (a worktree's `.git` file names it) sometimes edits that
checkout instead: seen twice with the full OpenCode harness. The scope gate catches it (`main tree modified: <path>`) and fails the run, but the change used to stay
in your tree. gruntly keeps three trees for such a run, as refs so that `git gc` cannot drop them: your tree before the run, and your tree when the gate saw
it. This command compares those with your tree now and, for each path the child changed, puts back the version from before the run **only if the file is still
exactly as the child left it**. A file you (or anything else) edited afterwards is never touched, because it cannot be told apart from the child's work any other
way: that is why this is a command you run, not something gruntly does on its own while you may be editing.
"""
from __future__ import annotations

import os
import re
import tempfile
from pathlib import Path

from . import worktree as wtmod
from .worktree import git

BEFORE = "refs/gruntly/main-before/"
AFTER = "refs/gruntly/main-after/"
RUN_ID = re.compile(r"[A-Za-z0-9_.-]+")


def _tree(root: Path, ref: str) -> str | None:
    p = git(["rev-parse", "--verify", "-q", f"{ref}^{{tree}}"], root, check=False)
    return p.stdout.strip() if p.returncode == 0 and p.stdout.strip() else None


def _changed(root: Path, a: str, b: str) -> list[str]:
    out = git(["diff-tree", "-r", "--name-only", "-z", a, b], root).stdout
    return [p for p in out.split("\0") if p]


def _entries(root: Path, tree: str, paths: list[str]) -> dict[str, tuple[str, str]]:
    """{path: (mode, blob)} for the given paths in a tree; a path the tree lacks is absent."""
    if not paths:
        return {}
    out = git(["--literal-pathspecs", "ls-tree", "-r", "-z", tree, "--", *paths], root).stdout
    res = {}
    for rec in out.split("\0"):
        if rec:
            meta, path = rec.split("\t", 1)
            mode, _kind, sha = meta.split()
            res[path] = (mode, sha)
    return res


def _drop_empty_parents(root: Path, path: Path) -> None:
    d = path.parent
    while d != root and root in d.parents:
        try:
            d.rmdir()                  # only an empty folder goes; rmdir refuses anything else
        except OSError:
            return
        d = d.parent


def restore(root: Path, run_id: str, dry_run: bool = False) -> dict:
    root = Path(root)
    if not RUN_ID.fullmatch(run_id):
        return {"run_id": run_id, "error": "not a run id"}
    before, after = _tree(root, BEFORE + run_id), _tree(root, AFTER + run_id)
    if not before or not after:
        return {"run_id": run_id, "restored": [], "error": "nothing to restore: this run did not change your working tree, or `gruntly gc` already dropped the record"}
    paths = _changed(root, before, after)
    now = wtmod.fingerprint(root)
    b, a, c = (_entries(root, t, paths) for t in (before, after, now))
    back, gone, left = [], [], []
    for p in paths:
        if c.get(p) == b.get(p):
            left.append({"path": p, "why": "already as it was before the run"})
        elif c.get(p) != a.get(p):
            left.append({"path": p, "why": "edited again since the run; left alone"})
        elif p in b:
            back.append(p)
        else:
            gone.append(p)
    if not dry_run:
        for p in gone:                 # the child created it: take it away
            target = root / p
            try:
                target.unlink()
            except FileNotFoundError:
                pass
            _drop_empty_parents(root, target)
        if back:                       # the child changed or deleted it: write the earlier version, with the repository's own line-ending rules
            fd, idx = tempfile.mkstemp(prefix="gruntly-restore-")
            os.close(fd)
            os.unlink(idx)
            env = {"GIT_INDEX_FILE": idx}
            try:
                git(["read-tree", before], root, env=env)
                git(["checkout-index", "-f", "-z", "--stdin"], root, env=env, input="\0".join(back) + "\0")
            finally:
                if os.path.exists(idx):
                    os.unlink(idx)
    done = sorted(back + gone)
    out = {"run_id": run_id, "dry_run": dry_run, ("would_restore" if dry_run else "restored"): done}
    if left:
        out["left_alone"] = left
    return out
