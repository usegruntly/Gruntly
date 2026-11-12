"""Stall tracking, the classes of a failed run, and the escalation policy."""
import pytest

from gruntly import escalation as esc


def test_a_run_with_no_edit_for_too_long_is_stopped_but_reading_a_while_is_fine():
    s = esc.Stall(stall_s=60, first_edit_s=100, now=0)
    assert s.observe(esc.EMPTY, now=50) is None            # still reading
    assert s.observe(esc.EMPTY, now=101) == "noedit"


def test_a_stall_is_time_since_the_last_new_diff_not_since_the_last_edit_of_any_kind():
    s = esc.Stall(stall_s=60, first_edit_s=100, now=0)
    assert s.observe("a", now=10) is None                  # first edit
    assert s.observe("b", now=40) is None                  # a new diff: progress
    assert s.observe("b", now=99) is None                  # 59 s since the last new one
    assert s.observe("b", now=101) == "stall"              # 61 s


def test_editing_and_reverting_is_a_loop_not_progress():
    s = esc.Stall(stall_s=1000, first_edit_s=1000, now=0)
    out = [s.observe(x, now=i) for i, x in enumerate(["a", esc.EMPTY, "a", esc.EMPTY, "a"])]
    assert out[:3] == [None, None, None] and "loop" in out[3:]


def test_a_new_diff_every_time_is_not_a_loop():
    s = esc.Stall(stall_s=1000, first_edit_s=1000, now=0)
    assert all(s.observe(f"state{i}", now=i) is None for i in range(20))


def test_zero_disables_the_clocks():
    s = esc.Stall(stall_s=0, first_edit_s=0, now=0)
    assert s.observe(esc.EMPTY, now=10_000) is None and s.observe("a", now=10_001) is None and s.observe("a", now=99_999) is None


@pytest.mark.parametrize("status,reason,breach,files,attempts,cls", [
    ("timeout", "the child repeated the same output over and over", "loop", 2, 1, "stuck"),
    ("timeout", "no new change to the code for 240s", "stall", 1, 1, "stuck"),
    ("escalate", "stuck: gate 'acceptance' failed identically twice", None, 1, 2, "stuck"),
    ("escalate", "child made 4 malformed tool calls", None, 0, 1, "stuck"),
    ("timeout", "wall-clock budget exceeded", "wall", 3, 1, "slow"),
    ("timeout", "wall-clock budget exceeded", "wall", 0, 1, "stuck"),
    ("timeout", "wall-clock budget used up", None, 2, 2, "slow"),
    ("escalate", "narrated work: the child reported success but made no edits", None, 0, 2, "gave_up"),
    ("escalate", "acceptance failed", None, 0, 2, "gave_up"),
    ("escalate", "acceptance failed", None, 2, 2, "hard"),
])
def test_classes_of_a_run_that_did_not_pass(status, reason, breach, files, attempts, cls):
    assert esc.classify(status, reason, breach, files, attempts)["class"] == cls


def test_nothing_to_classify_for_a_pass_or_a_server_error():
    assert esc.classify("passed", None) is None and esc.classify("error", "model server error") is None


def test_escalation_is_rare_off_by_default_never_after_one_round_never_for_a_slow_run():
    classes = ("stuck", "hard", "gave_up", "slow")
    assert not any(esc.recommend(c, "off", 5) for c in classes)
    assert not any(esc.recommend(c, "hard", 1) for c in classes)              # one failed round: a follow-up may still finish it
    assert [esc.recommend(c, "hard", 2) for c in classes] == [True, True, True, False]
    assert esc.recommend("stuck", "hard", 3) and not esc.recommend("slow", "hard", 3)


def test_the_attempts_own_starting_diff_is_the_baseline_not_progress():
    s = esc.Stall(stall_s=60, first_edit_s=100, now=0, start="earlier-work")
    assert s.observe("earlier-work", now=500) == "stall"                      # edited already, nothing new for 500 s
    assert esc.Stall(stall_s=60, first_edit_s=100, now=0, start="w").observe("w", now=30) is None


def test_policy_comes_from_the_environment_then_the_project_file_and_is_off_by_default(tmp_path, monkeypatch):
    monkeypatch.delenv("GRUNTLY_ESCALATE", raising=False)
    assert esc.when(tmp_path) == "off"
    (tmp_path / ".gruntly.toml").write_text('[escalate]\nwhen = "hard"\n')
    assert esc.when(tmp_path) == "hard"
    monkeypatch.setenv("GRUNTLY_ESCALATE", "off")
    assert esc.when(tmp_path) == "off"
    monkeypatch.setenv("GRUNTLY_ESCALATE", "any")                              # there is no `any`: too easy to over-escalate
    assert esc.when(tmp_path) == "off"
    monkeypatch.setenv("GRUNTLY_ESCALATE", "sometimes")
    assert esc.when(tmp_path) == "off"
