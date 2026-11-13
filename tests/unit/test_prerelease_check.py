"""scripts/prerelease_check.py: nothing that should not be public goes public by accident."""
import importlib.util
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("prerelease_check", ROOT / "scripts" / "prerelease_check.py")
check = importlib.util.module_from_spec(spec)
spec.loader.exec_module(check)


def _repo(tmp_path, files, email="dev@users.noreply.github.com"):
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    for name, text in files.items():
        (tmp_path / name).write_text(text, encoding="utf8")
    subprocess.run(["git", "add", "-A"], cwd=tmp_path, check=True)
    subprocess.run(["git", "-c", f"user.email={email}", "-c", "user.name=dev", "commit", "-qm", "x"], cwd=tmp_path, check=True)
    return tmp_path


def test_it_finds_a_key_a_home_path_an_email_and_a_forbidden_word_without_printing_the_key(tmp_path, capsys):
    key = "sk-" + "Q7x9" * 8
    person, mail = "jd" + "oe", "jane.d" + "oe@corp-mail" + ".org"          # assembled here so that this file does not trip the check it tests
    _repo(tmp_path, {"a.py": f'KEY = "{key}"\n', "b.md": f"see C:\\Users\\{person}\\Desktop and /home/{person}/x and write to {mail}\n",
                     "c.txt": "owner: Zebulon\n"})
    assert check.main(["--root", str(tmp_path), "--words", "zebulon"]) == 1
    out = capsys.readouterr().out
    for want in ("a.py:1: key-shaped string", "b.md:1: a real person's home path", "b.md:1: an email address", "c.txt:1: the word 'zebulon'"):
        assert want in out
    assert key not in out and "jdoe" not in out and "corp-mail" not in out                  # what was found is located, not repeated


def test_things_that_only_look_personal_pass(tmp_path, capsys):
    _repo(tmp_path, {"a.py": 'T = "sk-test1234567890abcdefghijklmnop"\nP = "/home/user/work and C:\\\\Users\\\\USER\\\\x and /Users/runner/y"\n',
                     "b.md": "install gruntly@v0.3.0 from https://qwenlm.github.io/docs/en/users/overview, mail dev@example.com\n"})
    assert check.main(["--root", str(tmp_path)]) == 0 and "clean" in capsys.readouterr().out


def test_history_mode_flags_a_real_commit_email_but_not_a_noreply_one(tmp_path, capsys):
    ok = _repo(tmp_path / "ok" if (tmp_path / "ok").mkdir() is None else tmp_path, {"a.txt": "x\n"})
    assert check.main(["--root", str(ok), "--history"]) == 0
    capsys.readouterr()
    bad_dir = tmp_path / "bad"
    bad_dir.mkdir()
    bad = _repo(bad_dir, {"a.txt": "x\n"}, email="someone@" + "university.edu")
    assert check.main(["--root", str(bad)]) == 0                                          # the tree is fine ...
    assert check.main(["--root", str(bad), "--history"]) == 1                             # ... the history is not
    assert "not a noreply address" in capsys.readouterr().out


def test_this_repository_itself_is_clean():
    assert check.main(["--root", str(ROOT)]) == 0
