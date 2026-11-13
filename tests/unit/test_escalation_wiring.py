"""The stall detector inside run_child, the two-round rule end to end, and the text the lean parent reads and the full session gets."""
import itertools
import json
import sys

from gruntly import agent, escalation as esc, runner
from gruntly.adapters.generic import GenericAdapter

SLEEP = [sys.executable, "-c", "import time; time.sleep(30)"]


def watch(tmp_path, stall, states, **kw):
    it = iter(states) if not isinstance(states, str) else None
    fn = (lambda: next(it)) if it is not None else (lambda: states)
    return runner.run_child(GenericAdapter(), SLEEP, {}, None, tmp_path, 30, 30, stall=stall, diff_state=fn, **kw)


def test_a_child_that_stops_changing_the_code_is_stopped_as_a_stall(tmp_path, monkeypatch):
    monkeypatch.setattr(runner, "DIFF_POLL_S", 0.2)
    cr = watch(tmp_path, esc.Stall(stall_s=1, first_edit_s=0, start="work"), "work")
    assert cr.breach == "stall" and cr.secs < 15


def test_a_child_that_never_edits_is_stopped_after_first_edit_s(tmp_path, monkeypatch):
    monkeypatch.setattr(runner, "DIFF_POLL_S", 0.2)
    cr = watch(tmp_path, esc.Stall(stall_s=0, first_edit_s=1), esc.EMPTY)
    assert cr.breach == "noedit" and cr.secs < 15


def test_edits_that_are_undone_over_and_over_are_a_loop(tmp_path, monkeypatch):
    monkeypatch.setattr(runner, "DIFF_POLL_S", 0.1)
    cr = watch(tmp_path, esc.Stall(stall_s=0, first_edit_s=0), itertools.cycle(["a", esc.EMPTY]))
    assert cr.breach == "loop" and cr.secs < 15


def test_a_child_whose_diff_keeps_changing_is_left_alone(tmp_path, monkeypatch):
    monkeypatch.setattr(runner, "DIFF_POLL_S", 0.1)
    code = [sys.executable, "-c", "import time; time.sleep(2)"]
    fresh = (f"state{i}" for i in itertools.count())
    cr = runner.run_child(GenericAdapter(), code, {}, None, tmp_path, 30, 30,
                          stall=esc.Stall(stall_s=1, first_edit_s=1), diff_state=lambda: next(fresh))
    assert cr.breach is None


def test_a_broken_diff_probe_never_breaks_a_run(tmp_path, monkeypatch):
    monkeypatch.setattr(runner, "DIFF_POLL_S", 0.1)
    code = [sys.executable, "-c", "import time; time.sleep(1)"]

    def boom():
        raise RuntimeError("git went away")
    cr = runner.run_child(GenericAdapter(), code, {}, None, tmp_path, 30, 30, stall=esc.Stall(1, 1), diff_state=boom)
    assert cr.breach is None


def test_more_tool_calls_than_the_cap_in_one_attempt_is_stopped(tmp_path):
    code = ("import json, time\nfor i in range(60):\n"
            " print(json.dumps({'type': 'tool_use', 'id': i, 'part': {'type': 'tool', 'tool': 'bash', "
            "'state': {'status': 'completed', 'input': {'command': f'step {i}'}}}}), flush=True)\n time.sleep(0.02)\n"
            "time.sleep(20)\n")
    cr = runner.run_child(GenericAdapter(), [sys.executable, "-c", code], {}, None, tmp_path, 30, 30, max_calls=10)
    assert cr.breach == "calls"


def test_one_failed_round_is_not_an_escalation_two_are(run_task, make_spec, monkeypatch):
    monkeypatch.setenv("GRUNTLY_ESCALATE", "hard")
    res, root = run_task(make_spec("no_fix", max_attempts=1))
    assert res["status"] == "escalate" and res["escalation"]["class"] == "gave_up"
    assert res["escalation"]["rounds"] == 1 and res["escalation"]["eligible"] is False
    res2 = runner.execute(root, res["run_id"], guidance="Fix the operator in calc.py.", extra_attempts=1)
    assert res2["status"] == "escalate" and res2["escalation"]["rounds"] == 2 and res2["escalation"]["eligible"] is True


def test_the_policy_is_off_unless_asked_for(run_task, make_spec, monkeypatch):
    monkeypatch.delenv("GRUNTLY_ESCALATE", raising=False)
    res, root = run_task(make_spec("no_fix", max_attempts=1))
    res2 = runner.execute(root, res["run_id"], guidance="Fix the operator in calc.py.", extra_attempts=1)
    assert res2["escalation"]["eligible"] is False and res2["escalation"]["rounds"] == 2


def test_a_run_that_passes_carries_no_escalation_record(run_task, make_spec):
    res, _ = run_task(make_spec("pass"))
    assert res["status"] == "passed" and "escalation" not in res


def test_the_block_tells_the_lean_parent_to_escalate_only_when_eligible_and_a_gap_persists():
    base = {"run_id": "r_1", "status": "escalate", "attempts": 2, "diff_stat": {"paths": [], "insertions": 0, "deletions": 0}, "gates": {},
            "failure_bundle": {"reason": "attempts exhausted"}}
    gap = ["the request is about many modules and the diff touches 1 of 8 source files in app"]
    esc = {"class": "stuck", "why": "stuck: same failure twice", "rounds": 2, "eligible": True}
    not_eligible = agent.block({**base, "escalation": {**esc, "rounds": 1, "eligible": False}}, None, gap_strong=gap)
    no_gap = agent.block({**base, "escalation": esc}, None, gap_strong=[])                    # the guided round failed, but nothing measurably uncovered
    loud = agent.block({**base, "escalation": esc}, None, gap_strong=gap)
    assert "escalation:" not in not_eligible and "escalation:" not in no_gap
    assert "escalation: recommended (stuck: stuck: same failure twice; 2 rounds; still uncovered: the request is about many modules" in loud
    assert "full session of your own model" in loud
    assert "escalation: recommended" in agent.LEAN_PROMPT and "GRUNTLY-FALLBACK" in agent.LEAN_PROMPT
    assert '"' not in agent.LEAN_PROMPT and "<" not in agent.LEAN_PROMPT and ">" not in agent.LEAN_PROMPT


def test_the_full_session_is_the_normal_one_with_the_edit_tools_and_the_story(monkeypatch):
    lean, _ = agent.lean_command("t", "sonnet")
    full, _ = agent.lean_command("t", "sonnet", full=True)
    assert "--system-prompt" in lean and "--tools" in lean
    assert "--system-prompt" not in full and "--tools" not in full and "--strict-mcp-config" not in full and "--disable-slash-commands" not in full
    assert full[full.index("--allowedTools") + 1] == agent.FULL_TOOLS
    text = agent.escalation_task("Fix add().", "GRUNTLY-FALLBACK: stuck: gate x failed identically twice (run r_1)")
    assert text.startswith("Fix add().") and "stuck: gate x failed identically twice (run r_1)" in text and "could not finish" in text
    assert "GRUNTLY-FALLBACK" not in text


def test_run_agent_escalates_to_a_full_session_with_what_the_lean_one_said(monkeypatch, capsys):
    calls = []
    replies = iter(["GRUNTLY-FALLBACK: stuck after two rounds (run r_9)", "done by the full session"])

    class FakePopen:
        """What the parent runner starts: nothing real. (The runner uses Popen so it can end a whole process tree on a timeout.)"""
        def __init__(self, argv, **kw):
            self.argv, self.returncode, self.pid = argv, 0, 0

        def communicate(self, input=None, timeout=None):
            calls.append((self.argv, input))
            return next(replies), ""

    monkeypatch.setattr(agent.subprocess, "Popen", FakePopen)
    assert agent.run_agent("Fix add().") == 0
    (lean_argv, lean_in), (full_argv, full_in) = calls
    assert "--system-prompt" in lean_argv and "--system-prompt" not in full_argv
    assert lean_in == "Fix add()." and "stuck after two rounds (run r_9)" in full_in
    assert "done by the full session" in capsys.readouterr().out
