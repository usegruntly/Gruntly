"""Benchmark tasks from real repositories (bench/real_tasks.py), against a tiny local repository: no network."""
import argparse
import importlib.util
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

spec = importlib.util.spec_from_file_location("real_tasks", Path(__file__).parents[2] / "bench" / "real_tasks.py")
real_tasks = importlib.util.module_from_spec(spec)
spec.loader.exec_module(real_tasks)


def git(repo, *args):
    return subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@t", *args], cwd=repo, capture_output=True, text=True, check=True).stdout


@pytest.fixture
def upstream(tmp_path):
    """A package with a bug, then the commit that fixes it, adds a test and writes a changelog entry."""
    repo = tmp_path / "up"
    (repo / "src" / "pkg").mkdir(parents=True)
    (repo / "tests").mkdir()
    git(tmp_path, "init", "-q", "-b", "main", "up")
    (repo / "src" / "pkg" / "__init__.py").write_text("def double(x):\n    return x + x if x else 1\n")
    (repo / "tests" / "test_pkg.py").write_text("from pkg import double\n\n\ndef test_double():\n    assert double(2) == 4\n")
    (repo / "CHANGES.md").write_text("# Changes\n\n- first release\n")
    git(repo, "add", "-A")
    git(repo, "commit", "-qm", "start")
    (repo / "src" / "pkg" / "__init__.py").write_text("def double(x):\n    return x + x\n")
    (repo / "tests" / "test_pkg.py").write_text(
        "from pkg import double\n\n\ndef test_double():\n    assert double(2) == 4\n\n\ndef test_double_zero():\n    assert double(0) == 0\n")
    (repo / "CHANGES.md").write_text("# Changes\n\n- double(0) now returns 0 instead of 1 {pr}`7`\n- first release\n")
    git(repo, "add", "-A")
    git(repo, "commit", "-qm", "Fix double() of zero")
    return repo


def make_args(repo, commit):
    return argparse.Namespace(repo=str(repo), url="https://example.test/up", src="src/pkg", tests="tests", prefix="up", commits=[commit])


def test_a_fix_commit_becomes_a_task_with_the_maintainers_words_and_the_fix_commits_tests(upstream, tmp_path):
    tasks = tmp_path / "tasks"
    real_tasks.make(make_args(upstream, "HEAD"), tasks)
    d = next(tasks.iterdir())
    s = yaml.safe_load((d / "task.yaml").read_text(encoding="utf8"))
    assert "double(0) now returns 0 instead of 1" in s["brief"] and "{pr}" not in s["brief"]       # their words, references stripped
    assert s["source"]["base"] == git(upstream, "rev-parse", "HEAD^").strip() and s["allowed_paths"] == ["src/pkg/**"]
    assert "test_double_zero" in (d / "hidden" / "tests" / "test_pkg.py").read_text(encoding="utf8")  # the fix's version of the tests
    assert s["acceptance"][0]["cmd"] == "python -m pytest -q -p no:cacheprovider tests/test_pkg.py"


def test_the_hidden_tests_fail_on_the_starter_and_pass_on_the_fix(upstream, tmp_path, capsys):
    tasks = tmp_path / "tasks"
    real_tasks.make(make_args(upstream, "HEAD"), tasks)
    name = next(tasks.iterdir()).name
    real_tasks.check(argparse.Namespace(repo=str(upstream), names=[name]), tasks)
    assert capsys.readouterr().out.count("OK ") == 1


def test_the_starter_is_the_parent_commit_and_judging_restores_the_starters_tests(upstream, tmp_path):
    tasks = tmp_path / "tasks"
    real_tasks.make(make_args(upstream, "HEAD"), tasks)
    d = next(tasks.iterdir())
    s = yaml.safe_load((d / "task.yaml").read_text(encoding="utf8"))
    work = tmp_path / "work"
    real_tasks.materialize(s["source"], work, upstream)
    assert "else 1" in (work / "src" / "pkg" / "__init__.py").read_text() and not (work / ".git").exists()
    before = (work / "tests" / "test_pkg.py").read_bytes()
    assert real_tasks.judge_files(d, work, sys.executable) is False                      # the bug is still there
    assert (work / "tests" / "test_pkg.py").read_bytes() == before                      # the starter's tests are back


def test_a_commit_that_explains_nothing_is_skipped(upstream, tmp_path, capsys):
    (upstream / "src" / "pkg" / "__init__.py").write_text("def double(x):\n    return 2 * x\n")
    (upstream / "tests" / "test_pkg.py").write_text(
        "from pkg import double\n\n\ndef test_double():\n    assert double(3) == 6\n")
    git(upstream, "add", "-A")
    git(upstream, "commit", "-qm", "Tidy double")
    real_tasks.make(make_args(upstream, "HEAD"), tmp_path / "tasks")
    assert "explains nothing" in capsys.readouterr().out and not (tmp_path / "tasks").exists()
