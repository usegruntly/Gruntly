"""The verdict rule of bench/gold_doc.py, on made-up rows: it must be strict, and it must not call a pilot a result."""
import sys
from pathlib import Path

BENCH = Path(__file__).parents[2] / "bench"
sys.path.insert(0, str(BENCH))
import gold_doc  # noqa: E402


def row(task, passed, cost, child=0.0, turns=4, **extra):
    return {"task": task, "passed": passed, "cost_usd": cost, "child_cost_usd": child, "turns": turns, "wall_s": 20, "tool_output_bytes": 4096, **extra}


def groups(n, ref_cost, del_cost, child=0.005, ref_pass=1.0, del_pass=1.0, ref_turns=8, del_turns=2):
    tasks = [f"t{i}" for i in range(n)]
    pr = lambda i: i < round(ref_pass * n)
    pd = lambda i: i < round(del_pass * n)
    jitter = lambda i: 1 + 0.01 * (i % 3)
    return {"reference": [row(t, pr(i), ref_cost * jitter(i), turns=ref_turns) for i, t in enumerate(tasks)],
            "delegated": [row(t, pd(i), del_cost * jitter(i), child, turns=del_turns) for i, t in enumerate(tasks)],
            "cheap": [row(t, True, 0.005) for t in tasks]}


def test_fewer_than_four_tasks_is_never_a_verdict_however_good_it_looks():
    a = gold_doc.analyse(groups(3, 0.50, 0.05))
    assert a["verdict"].startswith("UNSURE") and "n < 4" in a["verdict"]


def test_a_clear_saving_at_equal_quality_over_enough_tasks_is_delegate():
    a = gold_doc.analyse(groups(6, 0.40, 0.10))
    assert a["verdict"] == "DELEGATE", a
    assert a["fresh"] < -0.15 and a["ci"][1] < 0


def test_losing_more_than_one_task_is_avoid_even_if_it_is_cheaper():
    a = gold_doc.analyse(groups(8, 0.40, 0.10, ref_pass=1.0, del_pass=0.625))      # 3 of 8 lost
    assert a["verdict"] == "AVOID"


def test_losing_exactly_one_task_is_still_non_inferior():
    a = gold_doc.analyse(groups(8, 0.40, 0.10, ref_pass=1.0, del_pass=0.875))
    assert a["non_inferior"] and a["verdict"] == "DELEGATE"


def test_costing_much_more_with_nothing_to_gain_is_avoid():
    a = gold_doc.analyse(groups(5, 0.05, 0.12, ref_turns=1, del_turns=2))
    assert a["verdict"] == "AVOID", a


def test_equal_cost_but_a_long_session_saving_is_labelled_modelled_not_measured():
    a = gold_doc.analyse(groups(5, 0.06, 0.06, ref_turns=10, del_turns=2))
    assert a["verdict"].startswith("DELEGATE IN LONG SESSIONS") and "modelled" in a["verdict"], a


def test_no_delegated_rows_gives_no_analysis():
    assert gold_doc.analyse({"reference": [row("t", True, 0.1)]}) is None


def test_the_document_builds_from_the_stored_rows_and_prints_its_rule():
    text = gold_doc.build()
    assert "Verdict rule (fixed before any verdict was computed)" in text and "## Verdict matrix" in text
    assert "UNSURE means: do not delegate by default" in text
