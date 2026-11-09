import json

import pytest

from gruntly import cli, keys, providers


@pytest.fixture(autouse=True)
def cfg(tmp_path, monkeypatch):
    monkeypatch.setenv("GRUNTLY_CONFIG_DIR", str(tmp_path / "cfg"))
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    return tmp_path / "cfg"


def test_set_lookup_remove_round_trip(cfg):
    assert keys.lookup("gemini", "GEMINI_API_KEY") == (None, None)
    keys.set_key("gemini", 'a"b\c-key')
    assert keys.lookup("gemini", "GEMINI_API_KEY") == ('a"b\c-key', "keys file")
    assert (cfg / "keys.toml").is_file()
    assert keys.remove("gemini") and not keys.remove("gemini")
    assert keys.lookup("gemini", "GEMINI_API_KEY") == (None, None)


def test_the_environment_wins_over_the_file(monkeypatch):
    keys.set_key("gemini", "from-file")
    monkeypatch.setenv("GEMINI_API_KEY", "from-env")
    assert keys.lookup("gemini", "GEMINI_API_KEY") == ("from-env", "environment")
    assert providers.api_key(providers.get("gemini")) == "from-env"


def test_auth_never_prints_the_key(capsys, monkeypatch):
    import io
    monkeypatch.setattr("sys.stdin", io.StringIO("SECRET-VALUE-123\n"))
    assert cli.main(["auth", "set", "gemini"]) == 0
    assert cli.main(["auth", "list"]) == 0
    assert cli.main(["doctor"]) in (0, 1)
    out = capsys.readouterr()
    assert "SECRET-VALUE-123" not in out.out + out.err
    assert "key found (keys file)" in out.out
    assert cli.main(["auth", "remove", "gemini"]) == 0
    assert cli.main(["auth", "set", "nope"]) == 2


def test_a_stored_key_reaches_a_run_but_not_its_spec(repo, make_spec, monkeypatch):
    from gruntly import runner, worktree
    from gruntly.spec import build_spec
    keys.set_key("gemini", "STORED-KEY-XYZ")
    monkeypatch.setattr(providers, "PROVIDERS", {"gemini": providers.Provider(
        "gemini", "http://127.0.0.1:9/v1", "GEMINI_API_KEY", "m")})       # nothing listens there: the run fails fast
    root = worktree.preflight(repo)
    rid = runner.prepare(build_spec(make_spec("pass", provider="gemini"), root), root)
    runner.execute(root, rid)
    run_dir = root / ".gruntly" / "runs" / rid
    for f in run_dir.rglob("*"):
        if f.is_file():
            assert "STORED-KEY-XYZ" not in f.read_text(encoding="utf8", errors="replace"), f
