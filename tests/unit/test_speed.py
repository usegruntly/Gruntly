"""Child budgets grow with the child's own recorded speed, only once there is enough of it, and never shrink below the defaults."""
from gruntly import speed


def runs(n, wall, requests=None, harness="opencode", model="m", status="passed"):
    return [{"harness": harness, "model": model, "status": status, "wall_s": wall,
             "child_usage": {"requests": requests} if requests else None} for _ in range(n)]


def test_no_history_changes_nothing():
    assert speed.sized("opencode", "m", []) == {}
    assert speed.sized("opencode", "m", runs(speed.MIN_RUNS - 1, 60)) == {}


def test_a_fast_child_keeps_the_defaults_and_a_slow_one_gets_more_time_up_to_the_cap():
    assert speed.sized("opencode", "m", runs(10, 40, requests=10)) == {"budget_s": 900, "no_progress_s": 120}
    assert speed.sized("opencode", "m", runs(10, 1500, requests=10)) == {"budget_s": 1800, "no_progress_s": 300}   # 150 s a request


def test_budget_is_one_and_a_half_times_the_ninetieth_percentile_of_wall_time_above_the_floor():
    rows = runs(9, 100) + runs(1, 800)                  # p90 of ten runs = the slowest one
    assert speed.sized("opencode", "m", rows)["budget_s"] == 1200
    assert speed.sized("opencode", "m", rows, budget_floor=300)["budget_s"] == 1200
    assert speed.sized("opencode", "m", runs(10, 100), budget_floor=300)["budget_s"] == 300     # a supervised step's floor is lower
    assert speed.sized("opencode", "m", runs(10, 100), budget_floor=600)["budget_s"] == 600
    assert speed.sized("opencode", "m", runs(10, 200, requests=20))["no_progress_s"] == 120     # 3 x 10 s = 30 s, below the floor


def test_other_children_other_models_errors_and_timeouts_do_not_count():
    rows = runs(10, 900, harness="qwen") + runs(10, 900, model="other") + runs(10, 900, status="error") + runs(10, 900, status="timeout")
    assert speed.sized("opencode", "m", rows) == {}


def test_only_the_most_recent_runs_count():
    rows = runs(30, 1000) + runs(speed.WINDOW, 100)
    assert speed.sized("opencode", "m", rows)["budget_s"] == 900          # the slow old runs are out of the window


def test_the_persons_own_non_default_budget_wins(tmp_path):
    rows = runs(10, 1000, requests=10)
    assert speed.for_project(tmp_path, "opencode", "m", rows)["budget_s"] == 1500
    (tmp_path / ".gruntly.toml").write_text("budget_s = 1200\n", encoding="utf8")
    assert "budget_s" not in speed.for_project(tmp_path, "opencode", "m", rows)
    (tmp_path / ".gruntly.toml").write_text("budget_s = 900\n", encoding="utf8")          # the init template's value: not a choice
    assert speed.for_project(tmp_path, "opencode", "m", rows)["budget_s"] == 1500


def test_agent_run_does_not_cut_a_childs_budget_to_the_calls_wait(tmp_path, monkeypatch):
    """A slow child that outlives the wait costs one `gruntly wait`; killing it at the end of the wait costs the whole run."""
    from gruntly import cli
    monkeypatch.setattr(speed, "for_project", lambda *a, **k: {"budget_s": 1500, "no_progress_s": 200})
    monkeypatch.setattr(cli, "build_spec", lambda raw, root=None: type("S", (), {"harness": "opencode", "model": "m"})())
    assert cli._sized(tmp_path, 540) == {"budget_s": 1500, "no_progress_s": 200}
