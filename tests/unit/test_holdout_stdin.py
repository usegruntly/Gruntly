"""`--holdout NAME` with the test text on stdin: the text stays in the run's own record and NO file is written into the project
(2026-11-14: a day of runs left 21 holdout_*.py files, 18 with local paths, in a repo root; before that, text piped in for a name that
already existed was dropped silently and a stale test ran)."""
import argparse
import io
import threading
import time

import pytest

from gruntly import cli, holdout

TEST_A = "def test_a():\n    assert True\n"
TEST_B = "def test_b():\n    assert 1 + 1 == 2\n"


def ns(*paths):
    return argparse.Namespace(holdout=list(paths), holdout_cmd=None)


@pytest.fixture
def stdin(monkeypatch):
    def put(text, tty=False):
        f = io.StringIO(text)
        f.isatty = lambda: tty
        monkeypatch.setattr("sys.stdin", f)
    return put


@pytest.fixture
def proj(repo, monkeypatch):
    monkeypatch.chdir(repo)
    return repo


def test_text_on_stdin_is_kept_in_the_record_and_no_file_is_written(proj, stdin):
    stdin(TEST_A)
    ho = cli._holdout(ns("holdout_x.py"), proj, True)
    assert ho["files"] == ["holdout_x.py"] and ho["inline"] == {"holdout_x.py": TEST_A} and "holdout_x.py" in ho["cmd"]
    assert not (proj / "holdout_x.py").exists()


def test_an_old_file_with_that_name_is_left_alone_and_the_call_is_refused_with_a_way_out(proj, stdin):
    (proj / "holdout_x.py").write_text(TEST_A)
    stdin(TEST_B)
    with pytest.raises(ValueError, match="already a file in your project"):
        cli._holdout(ns("holdout_x.py"), proj, True)
    assert (proj / "holdout_x.py").read_text() == TEST_A


def test_a_tracked_file_is_never_used_as_a_name(proj, stdin):
    stdin(TEST_B)
    with pytest.raises(ValueError, match="git tracks"):
        cli._holdout(ns("test_calc.py"), proj, True)


@pytest.mark.parametrize("text, tty", [("", False), ("   \n", False), (TEST_B, True)])
def test_no_text_or_a_terminal_uses_the_file_already_in_the_project(proj, stdin, text, tty):
    (proj / "holdout_x.py").write_text(TEST_A)
    stdin(text, tty=tty)
    ho = cli._holdout(ns("holdout_x.py"), proj, True)
    assert ho["files"] == ["holdout_x.py"] and "inline" not in ho and (proj / "holdout_x.py").read_text() == TEST_A


def test_no_file_and_no_text_says_how_to_pass_it(proj, stdin):
    stdin("")
    with pytest.raises(ValueError, match="no test text arrived"):
        cli._holdout(ns("holdout_x.py"), proj, True)


def test_the_request_itself_on_stdin_is_never_taken_for_a_test(proj, stdin):
    (proj / "holdout_x.py").write_text(TEST_A)
    stdin("fix add() please")
    ho = cli._holdout(ns("holdout_x.py"), proj, False)                                    # request_in_args False: stdin is the request
    assert "inline" not in ho and (proj / "holdout_x.py").read_text() == TEST_A


def test_with_several_holdouts_the_text_goes_to_the_missing_one_and_the_existing_file_stays(proj, stdin):
    (proj / "holdout_old.py").write_text(TEST_A)
    stdin(TEST_B)
    ho = cli._holdout(ns("holdout_old.py", "holdout_new.py"), proj, True)
    assert ho["files"] == ["holdout_old.py", "holdout_new.py"] and ho["inline"] == {"holdout_new.py": TEST_B}
    assert not (proj / "holdout_new.py").exists() and (proj / "holdout_old.py").read_text() == TEST_A


def test_a_pipe_that_stays_open_and_silent_does_not_hang_the_call(proj, monkeypatch):
    release = threading.Event()

    class Silent:
        def isatty(self):
            return False

        def read(self):
            release.wait(10)
            return ""

    (proj / "holdout_x.py").write_text(TEST_A)
    monkeypatch.setattr("sys.stdin", Silent())
    monkeypatch.setattr(cli, "HOLDOUT_STDIN_WAIT_S", 0.2)
    t0 = time.monotonic()
    try:
        ho = cli._holdout(ns("holdout_x.py"), proj, True)
    finally:
        release.set()
    assert time.monotonic() - t0 < 3 and "inline" not in ho


def test_place_writes_the_text_for_the_moment_and_remove_takes_it_away(tmp_path):
    h = {"files": ["sub/holdout_x.py"], "cmd": "x", "inline": {"sub/holdout_x.py": TEST_A}}
    made = holdout.place(h, tmp_path)
    assert (tmp_path / "sub" / "holdout_x.py").read_text() == TEST_A
    holdout.remove(made)
    assert not (tmp_path / "sub" / "holdout_x.py").exists()


def test_place_never_overwrites_a_file_and_undoes_what_it_made(tmp_path):
    (tmp_path / "b.py").write_text("keep")
    h = {"files": ["a.py", "b.py"], "cmd": "x", "inline": {"a.py": TEST_A, "b.py": TEST_B}}
    with pytest.raises(FileExistsError):
        holdout.place(h, tmp_path)
    assert (tmp_path / "b.py").read_text() == "keep" and not (tmp_path / "a.py").exists()


def test_place_copies_a_file_the_parent_wrote_into_the_project(tmp_path):
    src, dst = tmp_path / "src", tmp_path / "dst"
    src.mkdir()
    dst.mkdir()
    (src / "h.py").write_text(TEST_A)
    made = holdout.place({"files": ["h.py"], "cmd": "x"}, dst, src)
    assert (dst / "h.py").read_text() == TEST_A
    holdout.remove(made)
    assert not (dst / "h.py").exists() and (src / "h.py").exists()
