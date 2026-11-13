"""The escalation A/B of bench/run_bench.py (the `lean_esc` arm): the second phase and the report section, with no model."""
import importlib.util
import sys
from pathlib import Path

BENCH = Path(__file__).parents[2] / "bench"
sys.path.insert(0, str(BENCH))
spec = importlib.util.spec_from_file_location("run_bench_esc", BENCH / "run_bench.py")
rb = importlib.util.module_from_spec(spec)
spec.loader.exec_module(rb)


class A:
    budget_usd = 0.6
    parent_model = "sonnet"


def info(cost, reply, turns=3, edits=0):
    return {"cost_usd": cost, "turns": turns, "reply": reply, "tools": {"Bash": turns}, "tokens": {"input": 4, "output": 100, "cache_read": 10, "cache_write": 20},
            "tool_output_bytes": 100, "parent_edits_total": edits, "cold_start": False, "first_call": {}}


def test_no_escalation_when_the_parent_did_not_ask_for_it(monkeypatch, tmp_path):
    monkeypatch.setattr(rb, "sh", lambda *a, **k: (_ for _ in ()).throw(AssertionError("no second session expected")))
    first = info(0.04, "All done.")
    esc, passed, detail, merged, wall = rb.escalate(tmp_path, tmp_path, {"brief": "b", "acceptance": [{"cmd": "c"}], "allowed_paths": ["x"]}, A(), tmp_path,
                                                    "t.lean_esc.1", first, True, {"cases_passed": 5}, 30)
    assert esc["triggered"] is False and esc["pass_before"] is True
    assert passed is True and merged is first and wall == 30


def test_the_second_phase_runs_a_normal_session_and_judges_again(monkeypatch, tmp_path):
    seen = {}

    class P:
        stdout = "raw-second-session"

    def fake_sh(cmd, cwd, **kw):
        seen["cmd"], seen["input"] = cmd, kw["input"]
        return P()
    monkeypatch.setattr(rb, "sh", fake_sh)
    monkeypatch.setattr(rb, "analyse", lambda raw: info(0.12, "fixed it", turns=9, edits=3))
    monkeypatch.setattr(rb, "judge", lambda td, w: True)
    monkeypatch.setattr(rb, "judge_detail", lambda: {"cases_passed": 8, "cases_failed": 0})
    first = info(0.05, "GRUNTLY-FALLBACK: stuck after two rounds (run r_9)", turns=3)
    spec_ = {"brief": "Fix add().", "acceptance": [{"cmd": "pytest -q"}], "allowed_paths": ["calc.py"]}
    esc, passed, detail, merged, wall = rb.escalate(tmp_path, tmp_path, spec_, A(), tmp_path, "t.lean_esc.1", first, False, {"cases_failed": 3}, 40)
    cmd = seen["cmd"]
    assert "--system-prompt" not in cmd and "--tools" not in cmd and "Write" in cmd and "Edit" in cmd        # the normal session, as in `alone`
    assert "A small model tried this first" in seen["input"] and "stuck after two rounds (run r_9)" in seen["input"] and "Fix add()." in seen["input"]
    assert esc["triggered"] and esc["pass_before"] is False and esc["pass_after"] is True and esc["rescued"] is True
    assert esc["esc_cost"] == 0.12 and esc["esc_turns"] == 9 and esc["esc_edits"] == 3 and esc["reason"].startswith("stuck after two rounds")
    assert passed is True and detail["cases_passed"] == 8                      # the final outcome is the one after the escalation
    assert merged["cost_usd"] == 0.17 and merged["turns"] == 12 and merged["takeover_edits"] == 3 and merged["tokens"]["output"] == 200
    assert (tmp_path / "t.lean_esc.1.esc.jsonl").read_text() == "raw-second-session"


def row(task, arm, passed, cost, esc=None, child=0.0):
    r = {"task": task, "bucket": "L", "arm": arm, "rep": 1, "passed": passed, "cost_usd": cost, "child_cost_usd": child, "reviewer_cost_usd": 0}
    if esc is not None:
        r["esc"] = esc
    return r


def test_the_ab_section_counts_rescued_needless_and_what_the_rescue_cost():
    rows = [
        row("a", "lean_esc", True, 0.05, {"triggered": False, "pass_before": True}, child=0.01),
        row("b", "lean_esc", True, 0.17, {"triggered": True, "pass_before": False, "pass_after": True, "rescued": True, "esc_cost": 0.12,
                                          "esc_turns": 9, "reason": "stuck"}, child=0.01),
        row("c", "lean_esc", False, 0.19, {"triggered": True, "pass_before": False, "pass_after": False, "rescued": False, "esc_cost": 0.14,
                                           "esc_turns": 12, "reason": "gave up"}, child=0.01),
        row("a", "alone", True, 0.10), row("b", "alone", True, 0.11), row("c", "alone", True, 0.12),
    ]
    out = "\n".join(rb.esc_section(rows))
    assert "| 3 | 2 | 1 | 0 | 1 | 1/3 | 2/3 |" in out                        # runs, escalated, rescued, needless, still failed, pass before/after
    assert "$0.260" in out                                                  # escalation spend: 0.12 + 0.14
    assert "$0.260 | $0.260 |" in out                                       # per rescued pass is the whole spend while only one was rescued
    assert "Same tasks, `alone` (this file): 3/3 passed" in out
    assert "b #1 (stuck): rescued" in out and "c #1 (gave up): not rescued" in out
    assert rb.esc_section([row("a", "alone", True, 0.1)]) == []


def test_the_report_has_the_section_and_lists_the_arm():
    rows = [{**row("b", "lean_esc", True, 0.17, {"triggered": True, "pass_before": False, "pass_after": True, "rescued": True, "esc_cost": 0.12,
                                                 "esc_turns": 9, "reason": "stuck"}),
             "turns": 12, "wall_s": 100, "tokens": {"output": 500}, "tool_output_bytes": 2048, "gruntly_status": ["escalate"],
             "gruntly_applied": [None], "gruntly_attempts": [2], "child_tokens": 0, "takeover_edits": 3, "sessions": 1}]
    text = rb.report(rows, {"harness": "claude", "model": "haiku", "parent_model": "sonnet"})
    assert "| L | lean_esc |" in text and "## Escalation A/B" in text
