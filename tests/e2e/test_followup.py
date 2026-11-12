"""Follow-ups: they may touch the files the parent names, they carry the round count, and an empty-diff run is classified."""
import sys

from gruntly import agent, store
from tests.e2e.test_agent import proj, say  # noqa: F401


def run_id(block):
    return next(ln.split(": ", 1)[1] for ln in block.splitlines() if ln.startswith("run: "))


def test_a_follow_up_may_touch_the_files_it_names(repo):
    (repo / "inventory").mkdir()
    for n in ("models", "store", "cli", "service"):
        (repo / "inventory" / f"{n}.py").write_text("x = 1\n")
    allowed = ["inventory/service.py"]
    out = agent.widen_scope(allowed, "Edit inventory/models.py, then store.py and cli.py.", repo)
    assert out[0] == "inventory/service.py"
    assert set(out) == {"inventory/service.py", "inventory/models.py", "inventory/store.py", "inventory/cli.py"}
    assert agent.widen_scope(allowed, "make it better", repo) == allowed          # nothing named, nothing widened
    assert agent.widen_scope(["**"], "edit cli.py", repo) == ["**"]


def test_a_follow_up_naming_another_file_gets_it_and_counts_as_the_next_round(proj, capsys, monkeypatch):
    (proj / "other.py").write_text("def sub(a, b):\n    return a - b\n")
    first = say(capsys, monkeypatch, proj, "fix add() so test_calc passes")
    rid = run_id(first)
    second = say(capsys, monkeypatch, proj, "also update other.py to keep the names", "--continue", rid)
    rid2 = run_id(second)
    st = store.Store.existing(proj, rid2)
    spec = st.read_json("spec.json")
    assert "other.py" in spec["allowed_paths"] and "calc.py" in spec["allowed_paths"]      # the first run's files and the named one
    lineage = st.read_json("lineage.json")
    assert lineage["from"] == rid and lineage["rounds"] == 1 and lineage["base"]          # where the first round started, for the cumulative diff
    assert st.read_json("state.json")["rounds"] == 2                                         # the first run and this follow-up


def test_a_pass_that_apply_refuses_for_an_empty_diff_is_recorded_as_gave_up(run_task, make_spec, monkeypatch):
    monkeypatch.setenv("GRUNTLY_ESCALATE", "hard")
    res, _ = run_task(make_spec("no_fix", max_attempts=1, followup=True, apply_on_pass=True,
                                acceptance=[{"cmd": f'"{sys.executable}" -c "pass"', "timeout_s": 30}]))
    assert res["status"] == "escalate" and res["failure_bundle"]["reason"] == "empty diff"
    esc = res["escalation"]
    assert esc["class"] == "gave_up" and esc["rounds"] == 1 and esc["eligible"] is False       # one round: not yet


def test_a_request_that_lists_parts_runs_with_the_whole_project_in_scope(proj, capsys, monkeypatch):
    out = say(capsys, monkeypatch, proj, "fix add() so test_calc passes. (1) the add function (2) keep the names (3) keep the docstrings")
    spec = store.Store.existing(proj, run_id(out)).read_json("spec.json")
    assert spec["allowed_paths"] == ["**"] and "Change only:" not in spec["brief"] and "every part" in spec["brief"]


def test_a_single_part_request_keeps_the_narrow_scope(proj, capsys, monkeypatch):
    out = say(capsys, monkeypatch, proj, "fix add() so test_calc passes")
    spec = store.Store.existing(proj, run_id(out)).read_json("spec.json")
    assert spec["allowed_paths"] != ["**"] and "Change only:" in spec["brief"]


def test_a_follow_up_listing_parts_gets_the_whole_project(repo):
    allowed = ["inventory/service.py"]
    assert agent.widen_scope(allowed, "Still missing: (1) the CLI (2) the model (3) the tests", repo) == ["**"]
    assert agent.widen_scope(allowed, "Still missing: the CLI", repo) == allowed


def test_a_guided_second_round_that_still_leaves_parts_uncovered_recommends_escalation(proj, monkeypatch):
    res = {"run_id": "r_2", "status": "passed", "applied": True, "attempts": 1, "verify": "unchanged", "gates": {},
           "diff_stat": {"paths": ["calc.py"], "insertions": 1, "deletions": 0}}
    req = "Still missing: (1) the CLI (2) the model (3) the tests"
    patch = "diff --git a/calc.py b/calc.py\n--- a/calc.py\n+++ b/calc.py\n@@ -0,0 +1 @@\n+x = 1\n"
    monkeypatch.setenv("GRUNTLY_ESCALATE", "hard")
    gap = ["the request lists 3 parts and the diff touches 1 source file (calc.py): check that every part is in the diff"]
    loud = agent.block(res, None, patch=patch, request=req, root=proj, rounds=2, gap_strong=gap)
    assert "escalation: recommended (incomplete after 2 rounds: the request lists 3 parts" in loud
    assert "escalation:" not in agent.block(res, None, patch=patch, request=req, root=proj, rounds=1, gap_strong=gap)   # one round: a follow-up may still do it
    assert "escalation:" not in agent.block(res, None, patch=patch, request=req, root=proj, rounds=2, gap_strong=[])    # nothing measurably uncovered
    monkeypatch.setenv("GRUNTLY_ESCALATE", "off")
    assert "escalation:" not in agent.block(res, None, patch=patch, request=req, root=proj, rounds=3, gap_strong=gap)   # policy off


def test_a_chain_of_rounds_that_leaves_the_original_request_uncovered_ends_in_a_recommendation(proj, capsys, monkeypatch):
    monkeypatch.setenv("GRUNTLY_ESCALATE", "hard")
    first = say(capsys, monkeypatch, proj, "fix add() so test_calc passes. (1) the add function (2) keep the names (3) keep the docstrings")
    rid = run_id(first)
    assert store.Store.existing(proj, rid).read_json("request.json")["request"].startswith("fix add()")
    assert "escalation:" not in first                                         # round 1 never escalates
    second = say(capsys, monkeypatch, proj, "do (1) (2) and (3) properly", "--continue", rid)
    rid2 = run_id(second)
    st = store.Store.existing(proj, rid2)
    assert st.read_json("request.json")["request"].startswith("fix add()")     # the original request travels with the chain
    assert st.read_json("lineage.json")["base"]
    assert "escalation: recommended" in second and "still uncovered: the request lists 3 parts" in second, second
    monkeypatch.setenv("GRUNTLY_ESCALATE", "off")
    third = say(capsys, monkeypatch, proj, "do (1) (2) and (3) properly", "--continue", rid2)
    assert "escalation:" not in third                                         # policy off: the same chain recommends nothing


def test_every_other_module_means_the_whole_project_even_without_numbered_parts():
    raw = {"brief": "Move it.\n\nMake the failing tests pass. Change only: app/config.py.", "allowed_paths": ["app/config.py"]}
    req = "Put it in app/config.py. Every other module must use load() instead of reading the environment."
    out = agent.open_scope(dict(raw), req)
    assert out["allowed_paths"] == ["**"] and "Change only:" not in out["brief"]
    assert agent.open_scope(dict(raw), "Put it in app/config.py.")["allowed_paths"] == ["app/config.py"]
    assert agent.spans_files("rename it everywhere") and not agent.spans_files("fix the off-by-one in paginate()")
