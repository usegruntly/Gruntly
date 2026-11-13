"""Git plumbing: preflight, snapshot, worktrees, diffs and main-tree fingerprints."""
from __future__ import annotations

import os
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path

# Generated noise that should never count as a change by the child.
NOISE = [
    ":(exclude,glob)**/__pycache__/**",
    ":(exclude,glob)**/*.pyc",
    ":(exclude,glob)**/.pytest_cache/**",
    ":(exclude,glob)**/.mypy_cache/**",
    ":(exclude,glob)**/.ruff_cache/**",
    ":(exclude).gruntly-handoff.md",
]
IDENT = {
    "GIT_AUTHOR_NAME": "gruntly",
    "GIT_AUTHOR_EMAIL": "gruntly@localhost",
    "GIT_COMMITTER_NAME": "gruntly",
    "GIT_COMMITTER_EMAIL": "gruntly@localhost",
}


class GitError(RuntimeError):
    pass


def git(args: list[str], cwd: Path | str, env: dict | None = None, check: bool = True,
        input: str | None = None) -> subprocess.CompletedProcess:
    e = {**os.environ, **(env or {})}
    p = subprocess.run(["git", *args], cwd=str(cwd), env=e, capture_output=True, text=True,
                       encoding="utf8", errors="replace", input=input)
    if check and p.returncode != 0:
        raise GitError(f"git {' '.join(args)} failed: {p.stderr.strip() or p.stdout.strip()}")
    return p


def repo_root(start: Path | str) -> Path:
    p = git(["rev-parse", "--show-toplevel"], start, check=False)
    if p.returncode != 0:
        raise GitError("not a git repository (gruntly v1 needs one)")
    return Path(p.stdout.strip())


def preflight(start: Path | str) -> Path:
    root = repo_root(start)
    if git(["rev-parse", "--verify", "HEAD"], root, check=False).returncode != 0:
        raise GitError("repository has no commits yet; make an initial commit first")
    exclude = Path(git(["rev-parse", "--git-path", "info/exclude"], root).stdout.strip())
    if not exclude.is_absolute():
        exclude = root / exclude
    exclude.parent.mkdir(parents=True, exist_ok=True)
    cur = exclude.read_text(encoding="utf8") if exclude.exists() else ""
    if ".gruntly/" not in cur.split():
        with exclude.open("a", encoding="utf8") as f:
            f.write(("" if cur.endswith("\n") or not cur else "\n") + ".gruntly/\n")
    return root


def _temp_index_tree(cwd: Path, from_head: bool, exclude: list[str] | None = None) -> str:
    fd, idx = tempfile.mkstemp(prefix="gruntly-idx-")
    os.close(fd)
    os.unlink(idx)
    env = {"GIT_INDEX_FILE": idx}
    try:
        if from_head:
            git(["read-tree", "HEAD"], cwd, env=env)
        git(["add", "-A", "--", ".", *NOISE], cwd, env=env)
        if exclude:
            git(["rm", "-r", "--cached", "-q", "--ignore-unmatch", "--", *exclude], cwd, env=env)
        return git(["write-tree"], cwd, env=env).stdout.strip()
    finally:
        if os.path.exists(idx):
            os.unlink(idx)


def fingerprint(root: Path) -> str:
    """Tree hash of everything not ignored in the main working tree."""
    return _temp_index_tree(root, from_head=False)


def changed_between(root: Path, a: str, b: str) -> list[str]:
    if a == b:
        return []
    return [x for x in git(["diff-tree", "-r", "--name-only", a, b], root).stdout.splitlines() if x]


def snapshot_commit(root: Path, base: str, exclude: list[str] | None = None) -> str:
    head = git(["rev-parse", "HEAD"], root).stdout.strip()
    if base == "head" and not exclude:
        return head
    tree = _temp_index_tree(root, from_head=(base == "head"), exclude=exclude)
    return git(["commit-tree", tree, "-p", head, "-m", "gruntly snapshot"], root, env=IDENT).stdout.strip()


@dataclass
class Worktree:
    path: Path
    branch: str
    base: str


def create(root: Path, run_id: str, base: str, exclude: list[str] | None = None) -> Worktree:
    commit = snapshot_commit(root, base, exclude)
    path = root / ".gruntly" / "worktrees" / run_id
    path.parent.mkdir(parents=True, exist_ok=True)
    branch = f"gruntly/{run_id}"
    # Check files out exactly as stored: with core.autocrlf=true a plain checkout would turn an LF file into CRLF, and the child's
    # edits (which quote LF text) would then fail to find their target.
    git(["-c", "core.autocrlf=false", "worktree", "add", "-q", "-b", branch, str(path), commit], root)
    return Worktree(path, branch, commit)


def remove(root: Path, run_id: str) -> None:
    path = root / ".gruntly" / "worktrees" / run_id
    git(["worktree", "remove", "--force", str(path)], root, check=False)
    git(["branch", "-D", f"gruntly/{run_id}"], root, check=False)
    git(["worktree", "prune"], root, check=False)
    state = root / ".gruntly" / "child-state" / run_id
    if state.is_dir():
        from .store import force_rmtree
        force_rmtree(state)


def keep_main_tree(root: Path, run_id: str, before: str, after: str) -> None:
    """Hold on to your tree as it was before a run and as the scope gate saw it after the child had changed it, as refs (a bare tree hash is not
    reachable, so `git gc` may drop it): `gruntly restore` works from these (issue #6)."""
    for kind, tree in (("before", before), ("after", after)):
        commit = git(["commit-tree", tree, "-m", f"gruntly main tree {kind}"], root, env=IDENT).stdout.strip()
        git(["update-ref", f"refs/gruntly/main-{kind}/{run_id}", commit], root)


def prune_main_trees(root: Path, days: int) -> int:
    """Drop the refs `keep_main_tree` made once they are older than the run retention."""
    import time
    cutoff = time.time() - days * 86400
    out = git(["for-each-ref", "--format=%(refname) %(committerdate:unix)", "refs/gruntly/"], root, check=False).stdout
    n = 0
    for line in out.splitlines():
        ref, _, when = line.rpartition(" ")
        if when.isdigit() and int(when) < cutoff:
            git(["update-ref", "-d", ref], root, check=False)
            n += 1
    return n


def files_beside(root: Path) -> set[str] | None:
    """Names of the files directly in the folder that holds the repository (a child that walks up out of its worktree lands there), or None when
    the folder is too big to be worth listing. Only a warning is made from this: gruntly never touches anything outside the repository."""
    try:
        names: set[str] = set()
        with os.scandir(Path(root).parent) as it:
            for i, e in enumerate(it):
                if i >= 5000:
                    return None
                if e.is_file(follow_symlinks=False):
                    names.add(e.name)
        return names
    except OSError:
        return None


def stage_all(wt: Path) -> None:
    git(["add", "-A", "--", ".", *NOISE], wt)


def numstat(wt: Path, base: str) -> list[tuple[str, int | None, int | None]]:
    """(path, insertions, deletions); None counts mean binary."""
    stage_all(wt)
    out = git(["diff", "--cached", "--numstat", "--no-renames", base, "--", ".", *NOISE], wt).stdout
    rows = []
    for line in out.splitlines():
        a, d, path = line.split("\t", 2)
        rows.append((path, None if a == "-" else int(a), None if d == "-" else int(d)))
    return rows


def name_status(wt: Path, base: str) -> dict[str, str]:
    stage_all(wt)
    out = git(["diff", "--cached", "--name-status", "--no-renames", base, "--", ".", *NOISE], wt).stdout
    res = {}
    for line in out.splitlines():
        st, path = line.split("\t", 1)
        res[path] = st[0]
    return res


def patch(wt: Path, base: str, paths: list[str] | None = None) -> str:
    stage_all(wt)
    spec = paths if paths else [".", *NOISE]
    return git(["diff", "--cached", "--binary", "--no-renames", base, "--", *spec], wt).stdout


def live_patch(wt: Path, base: str) -> str:
    """The worktree's changes so far as a text diff, for the live view (and the stall clock, which counts new diffs). Uses a throwaway
    copy of the index so the child's own git state is never touched while it is running. Git for Windows compares modification times to
    the second, so an edit to a file of the same size within the second of its checkout reads as unchanged here until the file changes
    again; a child's edits come seconds after its worktree is made, so this only shows up in tests that write twice in a row."""
    import tempfile
    idx = git(["rev-parse", "--git-path", "index"], wt, check=False).stdout.strip()
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td) / "index"
        src = Path(idx) if Path(idx).is_absolute() else Path(wt) / idx
        try:
            tmp.write_bytes(src.read_bytes())
        except OSError:
            pass
        env = {"GIT_INDEX_FILE": str(tmp)}
        git(["add", "-A", "--", ".", *NOISE], wt, env=env, check=False)
        return git(["diff", "--cached", "--no-renames", "--no-color", "-U2", base, "--", ".", *NOISE], wt, env=env, check=False).stdout


def file_at_base(wt: Path, base: str, path: str) -> str:
    p = git(["show", f"{base}:{path}"], wt, check=False)
    return p.stdout if p.returncode == 0 else ""
