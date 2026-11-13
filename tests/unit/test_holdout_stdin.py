"""`--holdout PATH` with text on stdin when PATH already exists: the text used to be dropped silently, so a stale test ran (website session,
2026-11-13: two failed runs and a wasted hour). Now the text wins, unless the file is tracked."""
import argparse
import io
import threading
import time

import pytest

from gruntly import cli

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


def norm(path):
    return path.read_text(encoding="utf8").replace("\r\n", "\n")


def test_a_missing_file_is_still_created_from_stdin(proj, stdin):
    stdin(TEST_A)
    cli._holdout(ns("holdout_x.py"), proj, True)
    assert norm(proj / "holdout_x.py") == TEST_A


def test_an_existing_untracked_file_is_replaced_by_the_text_on_stdin_and_the_caller_is_told(proj, stdin, capsys):
    (proj / "holdout_x.py").write_text(TEST_A)
    stdin(TEST_B)
    ho = cli._holdout(ns("holdout_x.py"), proj, True)
    assert norm(proj / "holdout_x.py") == TEST_B and ho["files"] == ["holdout_x.py"]
    assert "already existed; replaced it with the text on stdin" in capsys.readouterr().err


def test_the_same_text_changes_nothing_and_says_nothing(proj, stdin, capsys):
    (proj / "holdout_x.py").write_text(TEST_A)
    stdin(TEST_A)
    cli._holdout(ns("holdout_x.py"), proj, True)
    assert norm(proj / "holdout_x.py") == TEST_A and capsys.readouterr().err == ""


def test_a_tracked_file_is_never_overwritten(proj, stdin):
    before = (proj / "test_calc.py").read_text()
    stdin(TEST_B)
    with pytest.raises(ValueError, match="tracked by git"):
        cli._holdout(ns("test_calc.py"), proj, True)
    assert (proj / "test_calc.py").read_text() == before


@pytest.mark.parametrize("text, tty", [("", False), ("   \n", False), (TEST_B, True)])
def test_no_text_or_a_terminal_leaves_the_existing_file_alone(proj, stdin, text, tty):
    (proj / "holdout_x.py").write_text(TEST_A)
    stdin(text, tty=tty)
    cli._holdout(ns("holdout_x.py"), proj, True)
    assert norm(proj / "holdout_x.py") == TEST_A


def test_the_request_itself_on_stdin_is_never_taken_for_a_test(proj, stdin):
    (proj / "holdout_x.py").write_text(TEST_A)
    stdin("fix add() please")
    cli._holdout(ns("holdout_x.py"), proj, False)                                         # request_in_args False: stdin is the request
    assert norm(proj / "holdout_x.py") == TEST_A


def test_with_several_holdouts_the_text_goes_to_the_missing_one_and_existing_ones_are_untouched(proj, stdin):
    (proj / "holdout_old.py").write_text(TEST_A)
    stdin(TEST_B)
    ho = cli._holdout(ns("holdout_old.py", "holdout_new.py"), proj, True)
    assert norm(proj / "holdout_old.py") == TEST_A and norm(proj / "holdout_new.py") == TEST_B and ho["files"] == ["holdout_old.py", "holdout_new.py"]


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
        cli._holdout(ns("holdout_x.py"), proj, True)
    finally:
        release.set()
    assert time.monotonic() - t0 < 3 and norm(proj / "holdout_x.py") == TEST_A
