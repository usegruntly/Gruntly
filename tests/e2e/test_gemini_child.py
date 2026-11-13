"""Gemini CLI as the child, end to end through the runner: the runner starts the bridge in front of the endpoint, the real CLI edits the file in the run's worktree,
the gates and the acceptance test pass. The endpoint is a stub model server that plays a model calling write_file. Offline, no key, no money; skipped when
Gemini CLI is not installed (set GRUNTLY_TEST_GEMINI to a gemini executable)."""
import os
import shutil

import pytest

from gruntly import probe
from gruntly.adapters import gemini as gchild

REAL = os.environ.get("GRUNTLY_TEST_GEMINI") or shutil.which("gemini")
FIXED = "def add(a, b):\n    return a + b\n"


@pytest.mark.skipif(not REAL, reason="Gemini CLI is not installed (set GRUNTLY_TEST_GEMINI to a gemini executable)")
def test_a_gemini_child_fixes_a_file_through_the_bridge_and_the_run_passes(run_task, make_spec, monkeypatch):
    monkeypatch.setattr(gchild, "which", lambda n: REAL)
    if os.name == "nt":                                                  # the .cmd shim needs chcp, the shell tool powershell
        root = os.environ.get("SystemRoot", r"C:\Windows")
        monkeypatch.setenv("PATH", os.pathsep.join([os.environ["PATH"], os.path.join(root, "System32"), os.path.join(root, "System32", "WindowsPowerShell", "v1.0")]))
    with probe.StubServer(script=[{"tool": "write_file", "args": {"file_path": "calc.py", "content": FIXED}}, "fixed add()"]) as up:
        raw = make_spec("unused", harness="gemini", model="stub-model", endpoint=up.base_url, api_key="local", budget_s=240, no_progress_s=120)
        raw.pop("child_cmd", None)
        res, root = run_task(raw)
        assert res["status"] == "passed", (res.get("error"), res.get("summary"), res.get("failure_bundle"))
        assert res["child"]["harness"] == "gemini" and res["child"]["model"] == "stub-model"
        assert up.chat()[0].tools and "write_file" in up.chat()[0].tools and up.chat()[0].model == "stub-model"
        assert any("calc.py" in r for s in up.chat() for r in s.tool_results)
    bridge_records = list((root / ".gruntly" / "runs").glob("*/bridge.json"))
    assert bridge_records and '"requests": 2' in bridge_records[0].read_text(encoding="utf8")
