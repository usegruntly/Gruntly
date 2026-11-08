"""Gaps found in a review of the merged slim-profile code."""
import os
import stat
import sys
from pathlib import Path

import pytest

from gruntly import cli, doctor, profiles, runner, sandbox, store, worktree
from gruntly.adapters.base import Command, get_adapter
from gruntly.spec import build_spec


def repo_with(tmp_path, files):
    import subprocess
    for rel, text in files.items():
        p = tmp_path / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text)
    subprocess.run(["git", "init", "-q", "-b", "main"], cwd=tmp_path, check=True)
    subprocess.run(["git", "add", "-A"], cwd=tmp_path, check=True)
    return tmp_path


def spec_for(**over):
    d = {"brief": "Fix add().", "allowed_paths": ["calc.py"], "acceptance": ["python -m pytest -q test_calc.py"]}
    d.setdefault("profile", "auto")
    d.update(over)
    return build_spec(d)


FILES = {"calc.py": "def add(a, b):\n    return a - b\n", "test_calc.py": "from calc import add\n\ndef test_add():\n    assert add(2, 3) == 5\n"}


# ---- the child sees what is checked
def test_acceptance_test_file_is_shown_read_only(tmp_path):
    t = repo_with(tmp_path, FILES)
    s = spec_for()
    rp = profiles.resolve(s, t)
    block = profiles.inline_block(s, rp, t)
    assert "FILE calc.py" in block and "FILE test_calc.py" in block and "assert add(2, 3) == 5" in block
    assert rp.targets == ["calc.py"]  # shown, but not editable


def test_acceptance_directory_shows_its_test_files_but_never_holdout(tmp_path):
    t = repo_with(tmp_path, {"calc.py": "x = 1\n", "tests/test_a.py": "def test_a():\n    pass\n",
                            "tests/holdout_b.py": "HELD = 1\n", "tests/helper.py": "H = 2\n"})
    s = spec_for(acceptance=["python -m pytest -q tests"], holdout={"files": ["tests/holdout_b.py"], "cmd": "pytest -q tests/holdout_b.py"})
    block = profiles.inline_block(s, profiles.resolve(s, t, "typist"), t)
    assert "FILE tests/test_a.py" in block and "HELD" not in block and "helper.py" not in block


def test_acceptance_files_do_not_push_a_small_task_out_of_typist(tmp_path):
    t = repo_with(tmp_path, {"calc.py": "x = 1\n", "test_calc.py": "t = 1\n" * 400})
    assert profiles.resolve(spec_for(), t).name == "typist"


def test_symlinks_cannot_pull_outside_text_into_the_prompt(tmp_path):
    outside = tmp_path / "outside" / "secret.txt"
    outside.parent.mkdir()
    outside.write_text("TOP SECRET")
    t = tmp_path / "repo"
    t.mkdir()
    repo_with(t, {"calc.py": "x = 1\n"})
    try:
        os.symlink(outside, t / "link.py")
    except (OSError, NotImplementedError):
        pytest.skip("symlinks not permitted here")
    s = spec_for(allowed_paths=["calc.py", "link.py"], acceptance=["true"])
    assert "TOP SECRET" not in profiles.inline_block(s, profiles.resolve(s, t, "typist"), t)


# ---- prompts only ask for what the harness can do
def test_rewrite_in_full_only_for_harnesses_with_a_write_tool(tmp_path):
    t = repo_with(tmp_path, FILES)
    s = spec_for()
    oc = runner.pick_profile(s, t, get_adapter("opencode"))
    qw = runner.pick_profile(s, t, get_adapter("qwen"))
    assert oc.rewrite_only and not qw.rewrite_only
    from gruntly import prompt
    assert "Rewrite each file you change in full" in prompt.first(s, prompt.Ctx(oc, ""))
    assert "Rewrite each file you change in full" not in prompt.first(s, prompt.Ctx(qw, ""))
    assert "edit" in qw.tools  # Qwen's bare mode has no write tool, so edit must stay


# ---- cleanup
def test_remove_deletes_per_run_harness_state_even_with_readonly_files(repo, run_task, make_spec):
    res, root = run_task(make_spec("pass"))
    state = root / ".gruntly" / "child-state" / res["run_id"] / "opencode" / "data"
    state.mkdir(parents=True)
    ro = state / "pack.idx"
    ro.write_text("x")
    os.chmod(ro, stat.S_IREAD)  # git packs are read-only on Windows
    worktree.remove(root, res["run_id"])
    assert not (root / ".gruntly" / "child-state" / res["run_id"]).exists()


def test_gc_removes_orphaned_harness_state(repo):
    root = worktree.preflight(repo)
    orphan = root / ".gruntly" / "child-state" / "r_gone" / "opencode"
    orphan.mkdir(parents=True)
    (orphan / "db").write_text("x")
    removed = store.gc(root, lambda rid: worktree.remove(root, rid))
    assert "child-state/r_gone" in removed and not orphan.exists()


# ---- sandbox
def test_sandbox_keeps_the_harness_state_dir_writable(monkeypatch, tmp_path):
    monkeypatch.setattr(sandbox, "level_available", lambda lvl: (True, "ok"))
    state = tmp_path / ".gruntly" / "child-state" / "r_x" / "opencode" / "data"
    cmd = Command(["opencode"], env={"XDG_DATA_HOME": str(state), "OTHER": "1"})
    wrapped = sandbox.wrap(cmd, 1, tmp_path / "wt", tmp_path, "http://127.0.0.1:1234/v1")
    i = wrapped.argv.index(str(state))
    assert wrapped.argv[i - 1] == "--bind" and wrapped.argv[i + 1] == str(state)


# ---- doctor
def test_doctor_no_longer_demands_32k(monkeypatch):
    monkeypatch.setattr(doctor, "probe_endpoint", lambda *_a, **_k: {"ok": True, "models": ["m"], "ctx": {"m": 15000}, "error": None})
    c = next(x for x in doctor.run("http://x/v1", "m")["checks"] if x["check"] == "context_size")
    assert c["ok"] and "typist" in c["detail"]
    monkeypatch.setattr(doctor, "probe_endpoint", lambda *_a, **_k: {"ok": True, "models": ["m"], "ctx": {"m": 4000}, "error": None})
    c = next(x for x in doctor.run("http://x/v1", "m")["checks"] if x["check"] == "context_size")
    assert not c["ok"] and "too small" in c["detail"]
