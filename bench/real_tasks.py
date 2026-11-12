"""Benchmark tasks taken from real repositories: a bug-fix commit, with the fix commit's own tests as the hidden tests.

A synthetic task is a folder with `repo/` (the starter), `task.yaml` and `hidden/test_hidden.py`. A real task is smaller on disk and
harder in kind: `task.yaml` holds `source: {url, base, fix}` instead of a starter, `hidden/` holds the fix commit's version of the test
files it changed (paths kept), and the starter is rebuilt from the repository at the parent commit (`git archive`) when a run starts.
The parent sees the parent commit's tests, which pass; the hidden tests, which fail there and pass on the fix, judge the work.
Fix commits from after a model's training cutoff cannot have been memorised.

  python bench/real_tasks.py make --repo PATH --url URL --src src/click --tests tests --prefix click c53d373 f67c2bb ...
  python bench/real_tasks.py check NAME ...        # the hidden tests fail on the starter and pass on the fix commit

`--repo` is a full local clone (blobless clones make `git log --numstat` crawl). Tasks go to bench/tasks-real/NAME/.
"""
from __future__ import annotations

import argparse
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import yaml

HERE = Path(__file__).resolve().parent
TASKS = HERE / "tasks-real"
CACHE = HERE / ".cache"


def sh(args, cwd=None, **kw):
    return subprocess.run(args, cwd=cwd, capture_output=True, text=True, encoding="utf8", errors="replace", **kw)


def slug(url: str) -> str:
    return re.sub(r"[^A-Za-z0-9]+", "_", url.removeprefix("https://github.com/").removesuffix(".git")).strip("_")


def clone(url: str) -> Path:
    """The repository's full clone, cached under bench/.cache (git-ignored): cloned once, fetched when a commit is missing."""
    dest = CACHE / slug(url)
    if not dest.is_dir():
        CACHE.mkdir(exist_ok=True)
        sh(["git", "clone", "-q", url, str(dest)], check=True)
    return dest


def materialize(source: dict, work: Path, repo: Path | None = None) -> None:
    """The starter: the repository as it was at the parent commit, without its history."""
    repo = repo or clone(source["url"])
    if sh(["git", "cat-file", "-e", source["base"]], repo).returncode != 0:
        sh(["git", "fetch", "-q", "origin"], repo)
    work.mkdir(parents=True, exist_ok=True)
    tar = subprocess.run(["git", "archive", source["base"]], cwd=repo, capture_output=True, check=True).stdout
    subprocess.run(["tar", "-x", "-C", str(work)], input=tar, check=True)
    # a src layout: let plain `python -m pytest` import the package without installing it, for the parent, gruntly and the child
    ini, pyproject = "[tool.pytest.ini_options]", work / "pyproject.toml"
    if pyproject.is_file() and (work / "src").is_dir():
        text = pyproject.read_text(encoding="utf8")
        if "pythonpath" not in text:
            text = (text.replace(ini, ini + '\npythonpath = ["src"]', 1) if ini in text
                    else text.rstrip() + f'\n\n{ini}\npythonpath = ["src"]\n')
            pyproject.write_text(text, encoding="utf8")


def hidden_files(task_dir: Path) -> list[Path]:
    root = task_dir / "hidden"
    return [p for p in sorted(root.rglob("*")) if p.is_file()]


def judge_files(task_dir: Path, work: Path, python: str | None = None) -> bool:
    """Copy the hidden tests over the starter's, run them, put the starter's versions back."""
    python = python or sys.executable
    root = task_dir / "hidden"
    backups: dict[Path, bytes | None] = {}
    rels = [p.relative_to(root) for p in hidden_files(task_dir)]
    try:
        for rel in rels:
            dest = work / rel
            backups[dest] = dest.read_bytes() if dest.exists() else None
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(root / rel, dest)
        env = {**os.environ, "PYTHONPATH": str(work / "src"), "PYTHONDONTWRITEBYTECODE": "1"}
        tests = [r.as_posix() for r in rels if r.suffix == ".py"]
        p = sh([python, "-m", "pytest", "-q", "-p", "no:cacheprovider", *tests], work, env=env, timeout=300)
        judge_files.last = p            # the caller may want more than pass/fail: how many cases, and which failed
        return p.returncode == 0
    finally:
        for dest, old in backups.items():
            if old is None:
                dest.unlink(missing_ok=True)
            else:
                dest.write_bytes(old)


# ---------------------------------------------------------------------------------------------- make and check
def make(a, tasks_dir: Path | None = None) -> None:
    tasks_dir = tasks_dir or TASKS
    repo = Path(a.repo)
    for h in a.commits:
        full = sh(["git", "rev-parse", h], repo, check=True).stdout.strip()
        base = sh(["git", "rev-parse", f"{h}^"], repo, check=True).stdout.strip()
        subject, body = sh(["git", "log", "-1", "--format=%s%n%x00%b", h], repo).stdout.split("\n\x00", 1)
        changed = sh(["git", "diff", "--name-only", base, full], repo).stdout.split()
        src = [c for c in changed if c.startswith(a.src) and c.endswith(".py")]
        tests = [c for c in changed if c.startswith(a.tests) and c.endswith(".py")]
        if not src or not tests:
            print(f"skip {h}: needs changed source and tests")
            continue
        name = a.prefix + "_" + "_".join(re.sub(r'[^a-z0-9 ]+', ' ', subject.lower()).replace('fix ', '', 1).split()[:5])
        d = tasks_dir / name
        # The problem statement: the subject, plus what the maintainers wrote about the behaviour in the changelog entry that
        # came with the fix (their words, no code); a commit that explains nothing is skipped, because nobody could solve it.
        entry = [ln[1:] for ln in sh(["git", "diff", base, full, "--", ":(glob)CHANGE*", ":(glob)HISTORY*"], repo).stdout.splitlines()
                 if ln.startswith("+") and not ln.startswith("+++")]
        entry = [re.sub(r"\s*\{(?:pr|issue)\}`\d+`|\s*:(?:pr|issue):`\d+`", "", ln).rstrip() for ln in entry]
        entry = [ln for ln in entry if ln.strip() and not re.match(r"\s*(#+ |Version |Unreleased|Released)", ln)]
        said = "\n".join(entry).strip() or re.sub(r"\n{3,}", "\n\n", body.strip())
        if not said:
            print(f"skip {h}: the commit explains nothing beyond its subject ({subject})")
            continue
        shutil.rmtree(d, ignore_errors=True)
        for t in tests:                               # the fix commit's version of each changed test file
            dest = d / "hidden" / t
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_text(sh(["git", "show", f"{full}:{t}"], repo).stdout, encoding="utf8")
        text = re.sub(r"\(#\d+\)", "", subject).strip() + "\n\nWhat the maintainers wrote about the intended behaviour:\n" + said
        # What the parent can run: the changed test files as they were before the fix; a test file the fix adds does not exist yet,
        # so its folder stands in for it (the neighbouring tests of the same area)
        visible = list(dict.fromkeys(t if sh(["git", "cat-file", "-e", f"{base}:{t}"], repo).returncode == 0
                                     else (t.rsplit("/", 1)[0] if "/" in t else ".") for t in tests))
        check = f"python -m pytest -q -p no:cacheprovider {' '.join(visible)}"
        spec = {"brief": text[:1800], "source": {"url": a.url, "base": base, "fix": full}, "allowed_paths": [a.src + "/**"],
                "acceptance": [{"cmd": check, "timeout_s": 300}], "tests_writable": False,
                # a one-line changelog entry is a vague bug report: kept, but left out of benchmark runs unless asked for
                "vague": len(said) < 90, "fix_size": {"source_files": len(src), "test_files": len(tests)}}
        (d / "task.yaml").write_text(yaml.safe_dump(spec, sort_keys=False, allow_unicode=True), encoding="utf8")
        print(f"made {name}  ({h}: {', '.join(src)})")


def check(a, tasks_dir: Path | None = None) -> None:
    for name in a.names:
        d = (tasks_dir or TASKS) / name
        spec = yaml.safe_load((d / "task.yaml").read_text(encoding="utf8"))
        results = {}
        for label, rev in (("starter", spec["source"]["base"]), ("fix", spec["source"]["fix"])):
            with tempfile.TemporaryDirectory(prefix="real-", ignore_cleanup_errors=True) as tmp:
                work = Path(tmp) / "w"
                materialize({**spec["source"], "base": rev}, work, Path(a.repo) if a.repo else None)
                results[label] = judge_files(d, work)
        ok = results["starter"] is False and results["fix"] is True
        print(f"{'OK ' if ok else 'BAD'} {name}: hidden tests on the starter {'pass' if results['starter'] else 'fail'}, "
              f"on the fix {'pass' if results['fix'] else 'fail'}", flush=True)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    m = sub.add_parser("make")
    m.add_argument("--repo", required=True, help="a full local clone")
    m.add_argument("--url", required=True)
    m.add_argument("--src", required=True, help="source folder, e.g. src/click")
    m.add_argument("--tests", default="tests")
    m.add_argument("--prefix", required=True)
    m.add_argument("commits", nargs="+")
    m.set_defaults(fn=make)
    c = sub.add_parser("check")
    c.add_argument("--repo", help="a local clone to build the starter from (default: a cached clone of the task's url)")
    c.add_argument("names", nargs="+")
    c.set_defaults(fn=check)
    a = ap.parse_args()
    a.fn(a)


if __name__ == "__main__":
    main()
