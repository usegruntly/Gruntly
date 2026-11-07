"""Evaluate & fix end to end with the scripted child: gruntly runs the tests and hands failures back itself."""
import json

from gruntly import runner, worktree
from gruntly.spec import build_spec


def attempt_file(root, rid, n, name):
    return (root / ".gruntly" / "runs" / rid / "attempts" / str(n) / name).read_text(encoding="utf8")


def test_typist_prompt_inlines_the_file_and_forbids_running_tests(repo, make_spec):
    root = worktree.preflight(repo)
    spec = make_spec("pass", profile="typist")
    res = runner.execute(root, runner.prepare(build_spec(spec, root), root))
    assert res["status"] == "passed"
    prompt = attempt_file(root, res["run_id"], 1, "prompt.txt")
    assert "Do not run tests" in prompt and "FILE calc.py" in prompt and "return a - b" in prompt
    assert "pytest" not in prompt  # the child never sees the command; gruntly runs it


def test_a_failed_check_goes_straight_back_to_the_child_not_the_parent(repo, make_spec):
    """Attempt 1 changes nothing; gruntly runs the tests itself and sends the failure into attempt 2, which fixes it.
    The parent sees one passed result and no intermediate step."""
    root = worktree.preflight(repo)
    spec = make_spec("fix_on_retry", profile="typist", max_attempts=3)
    res = runner.execute(root, runner.prepare(build_spec(spec, root), root))
    assert res["status"] == "passed" and res["attempts"] == 2
    retry = attempt_file(root, res["run_id"], 2, "prompt.txt")
    assert "The system ran the checks and 'acceptance' failed" in retry
    assert "assert" in retry and "Do not run tests" in retry
    assert len(json.dumps(res)) < 600  # the parent paid for none of this


def test_default_profile_keeps_the_original_prompt_for_generic_children(repo, make_spec):
    root = worktree.preflight(repo)
    res = runner.execute(root, runner.prepare(build_spec(make_spec("pass"), root), root))  # profile auto + generic = default
    assert "Before you finish, run:" in attempt_file(root, res["run_id"], 1, "prompt.txt")


def test_slim_profile_needs_less_context_than_default(repo, make_spec, monkeypatch):
    from gruntly import doctor
    from gruntly.adapters.base import Command, Detection
    monkeypatch.setattr(doctor, "probe_endpoint", lambda *_a, **_k: {"ok": True, "models": ["m"], "ctx": {"m": 15000}, "error": None})
    monkeypatch.setattr("gruntly.adapters.qwen.QwenAdapter.detect", lambda self: Detection(True, "x"))
    import conftest
    monkeypatch.setattr("gruntly.adapters.qwen.QwenAdapter.command",
                        lambda self, t, w, p, r, profile=None: Command([__import__("sys").executable, str(conftest.FAKE), "pass"]))
    root = worktree.preflight(repo)
    base = make_spec("pass", harness="qwen", child_cmd=None, model="m")
    slim = runner.execute(root, runner.prepare(build_spec(base, root), root))  # auto -> typist, floor 8k
    assert slim["status"] == "passed"
    refused = runner.execute(root, runner.prepare(build_spec({**base, "profile": "default"}, root), root))
    assert refused["status"] == "error" and "15000" in refused["error"]
