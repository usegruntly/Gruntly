import json

import pytest

from gruntly import result as resmod
from gruntly.gates import glob_match
from gruntly.redact import redact
from gruntly.spec import SpecError, build_spec


@pytest.mark.parametrize("path,pat,ok", [
    ("src/api/client.py", "src/api/**", True),
    ("src/other/x.py", "src/api/**", False),
    (".env.local", ".env*", True),
    ("deep/dir/.env", ".env*", True),
    ("a.lock", "**/*.lock", True),
    ("x/y/a.lock", "**/*.lock", True),
    (".github/workflows/ci.yml", ".github/**", True),
    ("calc.py", "calc.py", True),
    ("sub/calc.py", "calc.py", True),
    ("anything/at/all", "**", True),
])
def test_glob(path, pat, ok):
    assert glob_match(path, pat) is ok


def test_redact_patterns_and_env_values():
    t = "k=sk-abcdefghijklmnopqrstuvwxyz and ghp_" + "a" * 30 + " and hunter2secret"
    out = redact(t, ["hunter2secret"])
    assert "sk-abc" not in out and "ghp_" not in out and "hunter2secret" not in out


def _big_result():
    return resmod.build(
        run_id="r_x", status="escalate", attempts=3,
        gates={"acceptance": {"ok": False, "cmd": "pytest", "tail": "line\n" * 5000}},
        diff_stat={"files": 1, "insertions": 1, "deletions": 0, "paths": ["a"] * 20},
        failure_bundle={"reason": "r", "gate": "acceptance", "files_touched": ["a"] * 20,
                        "attempts": [{"n": i} for i in range(4)]},
        untrusted={"gate_output": "fail\n" * 5000, "handoff": "h" * 5000, "summary": "x" * 5000},
        wall_s=1, child_tokens=5, next_cmds=["a"] * 3)


def test_result_is_capped_and_keeps_failing_tail():
    r = _big_result()
    assert len(json.dumps(r)) <= resmod.MAX_CHARS
    assert set(r["untrusted"]) <= {"gate_output", "handoff", "summary"}  # child text lives only here
    assert "line" not in json.dumps({k: v for k, v in r.items() if k != "untrusted"})


def test_tail_truncates_from_front():
    text = "\n".join(f"l{i}" for i in range(500)) + "\nAssertionError: boom"
    out = resmod.tail_lines(text, 10)
    assert out.endswith("AssertionError: boom") and "l0" not in out


def test_spec_requires_brief_and_acceptance():
    with pytest.raises(SpecError):
        build_spec({"acceptance": ["true"]})
    with pytest.raises(SpecError):
        build_spec({"brief": "x"})
    s = build_spec({"brief": "x", "acceptance": ["true"]})
    assert s.acceptance[0]["timeout_s"] == 300 and s.gates["diff_max_lines"] == 400


def test_project_config_overrides_defaults_and_spec_overrides_project(tmp_path):
    (tmp_path / ".gruntly.toml").write_text('max_attempts = 5\nbudget_s = 100\n[gates]\ndiff_max_lines = 50\n')
    s = build_spec({"brief": "x", "acceptance": ["true"], "budget_s": 7}, tmp_path)
    assert (s.max_attempts, s.budget_s, s.gates["diff_max_lines"], s.gates["scope"]) == (5, 7, 50, True)


def test_qwen_parser_on_real_fixture():
    from pathlib import Path
    from gruntly.adapters.qwen import QwenAdapter
    fx = Path(__file__).parents[1] / "fixtures" / "qwen"
    out = QwenAdapter().parse((fx / "headless_json_success.json").read_text(encoding="utf8"),
                              (fx / "headless_json_success.stderr").read_text(encoding="utf8"), 0)
    assert "a + b" in out.final_message
    assert out.session_id and out.usage["available"] and out.usage["total_tokens"] > 0
    assert not out.is_error


def test_scrubbed_env_drops_parent_secrets(monkeypatch):
    from gruntly.adapters.base import scrub_env
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-secret")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-secret")
    monkeypatch.setenv("GITHUB_TOKEN", "ghp_x")
    env = scrub_env({"OPENAI_API_KEY": "local"})
    assert env["OPENAI_API_KEY"] == "local"
    assert "ANTHROPIC_API_KEY" not in env and "GITHUB_TOKEN" not in env


def test_bwrap_wrap_builds_readonly_command(monkeypatch, tmp_path):
    from gruntly import sandbox
    from gruntly.adapters.base import Command
    monkeypatch.setattr(sandbox, "level_available", lambda lvl: (True, "ok"))
    c = sandbox.wrap(Command(["qwen"]), 1, tmp_path / "wt", tmp_path, "http://127.0.0.1:1234/v1")
    assert c.argv[0] == "bwrap" and "--ro-bind" in c.argv and c.argv[-1] == "qwen"
    assert "--unshare-net" not in c.argv  # model server is local to the host
    c2 = sandbox.wrap(Command(["qwen"]), 1, tmp_path / "wt", tmp_path, "https://example.com/v1")
    assert "--unshare-net" in c2.argv


def test_opencode_parser_on_real_fixture():
    from pathlib import Path
    from gruntly.adapters.opencode import OpenCodeAdapter
    fx = Path(__file__).parents[1] / "fixtures" / "opencode"
    out = OpenCodeAdapter().parse((fx / "run_json_success.jsonl").read_text(encoding="utf8"), "", 0)
    assert "a + b" in out.final_message
    assert out.session_id.startswith("ses_")
    assert out.usage["available"] and out.usage["total_tokens"] > 40000
    assert not out.is_error


def test_same_size_same_second_edit_is_not_hidden_by_stale_bytecode(tmp_path):
    """Regression: 'a - b' -> 'a + b' keeps size and mtime second, so a cached .pyc made a correct fix look broken."""
    import os
    import sys
    from gruntly.gates import acceptance
    (tmp_path / "m.py").write_text("def f():\n    return 1 - 1\n")
    (tmp_path / "t.py").write_text("from m import f\nassert f() == 2\n")
    cmd = f'"{sys.executable}" t.py'
    # warm a .pyc the way an earlier attempt would have (without our flag)
    env = {k: v for k, v in os.environ.items() if k != "PYTHONDONTWRITEBYTECODE"}
    import subprocess
    subprocess.run([sys.executable, "t.py"], cwd=tmp_path, env=env, capture_output=True)
    st = (tmp_path / "m.py").stat()
    (tmp_path / "m.py").write_text("def f():\n    return 1 + 1\n")
    os.utime(tmp_path / "m.py", (st.st_atime, st.st_mtime))  # same mtime, same size
    assert acceptance.run_cmd(cmd, tmp_path, 30)["ok"] is True


def test_bare_strings_are_one_item_lists_not_characters():
    """Regression from a real session: `acceptance: "pytest -q"` ran the command `p`."""
    s = build_spec({"brief": "x", "acceptance": "python -m pytest -q", "allowed_paths": "calc.py", "deny_paths": ".env*"})
    assert s.acceptance == [{"cmd": "python -m pytest -q", "timeout_s": 300}]
    assert s.allowed_paths == ["calc.py"] and s.deny_paths == [".env*"]
    s2 = build_spec({"brief": "x", "acceptance": {"cmd": "true", "timeout_s": 5}})
    assert s2.acceptance == [{"cmd": "true", "timeout_s": 5}]


def test_a_child_that_repeats_a_long_line_is_stopped_as_a_loop(tmp_path):
    import sys
    from gruntly.adapters.generic import GenericAdapter
    from gruntly.runner import run_child
    code = "import time\nfor _ in range(200):\n print('the same long tool call repeated again and again ' * 3, flush=True)\n time.sleep(0.05)\n"
    cr = run_child(GenericAdapter(), [sys.executable, "-c", code], {}, None, tmp_path, 30, 30)
    assert cr.breach == "loop"


def test_auto_harness_picks_the_first_installed_child(monkeypatch):
    from gruntly.adapters import base
    seen = {"opencode": False, "qwen": True, "hermes": True}
    class D:  # noqa: D401
        def __init__(self, ok): self.installed = ok
    class A:
        def __init__(self, n): self.n = n
        def detect(self): return D(seen[self.n])
    monkeypatch.setattr(base, "get_adapter", lambda n, spec=None: A(n))
    assert base.pick_installed() == "qwen"
    seen["qwen"] = False
    seen["hermes"] = False
    assert base.pick_installed() is None
