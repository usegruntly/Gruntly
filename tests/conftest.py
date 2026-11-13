import json
import subprocess
import sys
from pathlib import Path

import pytest

FAKE = str(Path(__file__).parent / "fake_child" / "fake_child.py")


@pytest.fixture(autouse=True)
def never_start_the_real_claude(monkeypatch):
    """Claude Code runs on your own login, so starting it is a paid call. A test that reaches the real one (a mock that no longer matches the code under
    test, a missing PATH stand-in) must fail instead of spending money: this once cost a Sonnet call when the parent runner moved from `subprocess.run`
    to `Popen` and a test still patched `run`. Stand-ins live under the temp folder and are allowed; set GRUNTLY_ALLOW_REAL_CLAUDE=1 for a deliberate live test."""
    import os
    import tempfile
    real_init = subprocess.Popen.__init__
    temp = os.path.normcase(os.path.realpath(tempfile.gettempdir()))

    def guarded(self, args, *a, **kw):
        argv = args if isinstance(args, (list, tuple)) else str(args).split()
        exe = str(argv[0]) if argv else ""
        if (not os.environ.get("GRUNTLY_ALLOW_REAL_CLAUDE") and os.path.splitext(os.path.basename(exe))[0].lower() == "claude"
                and not os.path.normcase(os.path.realpath(exe)).startswith(temp)):
            raise RuntimeError(f"a test tried to start the real Claude Code ({exe}): that is a paid call. Fake it (Popen or a stand-in `claude` under tmp_path).")
        real_init(self, args, *a, **kw)
    monkeypatch.setattr(subprocess.Popen, "__init__", guarded)


@pytest.fixture(autouse=True)
def never_open_a_browser(monkeypatch):
    """A harness run with `--yes-always` (Aider) says yes to every "Open URL for more info?", and a fresh HOME makes each run the first run of a version, so a
    test of the real binary opened Aider's release-notes page in the user's browser every time (the tabs filled the machine's memory, 2026-11-13). Every
    test runs with `BROWSER` set to a program that does nothing; see gruntly/nobrowser.py."""
    from gruntly import nobrowser
    monkeypatch.delenv(nobrowser.ALLOW, raising=False)
    monkeypatch.setenv("BROWSER", nobrowser.command())


@pytest.fixture
def browser_stand_in(tmp_path, monkeypatch):
    """Swaps the do-nothing program gruntly hands a harness as its browser for one that writes down each URL it is asked to open, and returns a function
    that lists them: proves a real binary's attempt to open a page was caught by gruntly's stand-in and reached no browser."""
    from gruntly import nobrowser
    rec = tmp_path / "stand in" / "record_url.py"
    rec.parent.mkdir()
    log = tmp_path / "opened-urls.txt"
    rec.write_text("import sys\nopen(sys.argv[1], 'a').write(' '.join(sys.argv[2:]) + '\\n')\n")
    real = nobrowser.command
    monkeypatch.setattr(nobrowser, "command", lambda argv=None: real(argv or [sys.executable, str(rec), str(log)]))
    return lambda: log.read_text().split() if log.exists() else []


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
