"""Gaps found in reviews: harness state cleanup, the sandbox, and doctor's context check."""
import os
import stat

from gruntly import doctor, sandbox, store, worktree
from gruntly.adapters.base import Command


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
def test_doctor_warns_below_the_context_the_harness_needs(monkeypatch):
    monkeypatch.setattr(doctor, "probe_endpoint", lambda *_a, **_k: {"ok": True, "models": ["m"], "ctx": {"m": 40000}, "error": None})
    c = next(x for x in doctor.run("http://x/v1", "m")["checks"] if x["check"] == "context_size")
    assert c["ok"] and not c["warn"]
    monkeypatch.setattr(doctor, "probe_endpoint", lambda *_a, **_k: {"ok": True, "models": ["m"], "ctx": {"m": 15000}, "error": None})
    c = next(x for x in doctor.run("http://x/v1", "m")["checks"] if x["check"] == "context_size")
    assert not c["ok"] and c["warn"] and "larger context" in c["detail"]
