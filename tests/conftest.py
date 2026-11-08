import json
import subprocess
import sys
from pathlib import Path

import pytest

FAKE = str(Path(__file__).parent / "fake_child" / "fake_child.py")


def sh(cwd, *args):
    return subprocess.run(args, cwd=cwd, check=True, capture_output=True, text=True)


@pytest.fixture
def repo(tmp_path, monkeypatch):
    monkeypatch.setenv("GRUNTLY_STATE_DIR", str(tmp_path / "state"))
    monkeypatch.setenv("GRUNTLY_CONFIG_DIR", str(tmp_path / "cfg"))
    r = tmp_path / "proj"
    r.mkdir()
    sh(r, "git", "init", "-q", "-b", "main")
    sh(r, "git", "config", "user.email", "t@t")
    sh(r, "git", "config", "user.name", "t")
    (r / "calc.py").write_text("def add(a, b):\n    return a - b\n")
    (r / "test_calc.py").write_text("from calc import add\n\ndef test_add():\n    assert add(2, 3) == 5\n")
    sh(r, "git", "add", "-A")
    sh(r, "git", "commit", "-qm", "init")
    return r


@pytest.fixture
def make_spec():
    def _make(scenario, **over):
        d = {
            "brief": "Fix add() in calc.py.",
            "harness": "generic",
            "profile": "auto",
            "child_cmd": [sys.executable, FAKE, scenario, "{prompt}"],
            "allowed_paths": ["calc.py"],
            "acceptance": [{"cmd": f'"{sys.executable}" -m pytest -q', "timeout_s": 60}],
            "max_attempts": 2,
            "budget_s": 60,
            "no_progress_s": 20,
        }
        d.update(over)
        return d
    return _make


@pytest.fixture
def run_task(repo):
    from gruntly import runner, worktree
    from gruntly.spec import build_spec

    def _run(raw):
        root = worktree.preflight(repo)
        rid = runner.prepare(build_spec(raw, root), root)
        return runner.execute(root, rid), root

    return _run
