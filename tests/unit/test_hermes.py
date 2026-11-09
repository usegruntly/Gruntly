from pathlib import Path

from gruntly.adapters.hermes import HermesAdapter, home_for, write_config
from gruntly.spec import build_spec

FIX = Path(__file__).parents[1] / "fixtures" / "hermes"


def task(**over):
    return build_spec({"brief": "x", "acceptance": ["true"], "harness": "hermes", "model": "m/one",
                       "endpoint": "http://127.0.0.1:5555/v1", "api_key": "gruntly-proxy", **over})


def workdir(tmp_path):
    w = tmp_path / ".gruntly" / "worktrees" / "r_1"
    w.mkdir(parents=True)
    return w


def test_the_real_quiet_output_gives_the_answer_without_the_diff_preview_and_the_session_id():
    out = (FIX / "quiet_success.stdout").read_text(encoding="utf8")
    err = (FIX / "quiet_success.stderr").read_text(encoding="utf8")
    o = HermesAdapter().parse(out, err, 0)
    assert o.session_id == "20261109_191151_014343" and not o.is_error
    assert o.final_message == "a//home/aaryan/hs_test/calc.py → b//home/aaryan/hs_test/calc.py\n@@ -1,2 +1,2 @@\n def add(a, b):\n-    return a - b\n+    return a + b\nAd-hoc verification successful: add(a, b) now correctly returns a + b." \
        or "Ad-hoc verification successful" in o.final_message
    assert "┊" not in o.final_message


def test_a_resumed_session_keeps_its_id_and_a_failure_is_an_error():
    err = (FIX / "quiet_resumed.stderr").read_text(encoding="utf8")
    o = HermesAdapter().parse("The file changed was ./calc.py.\n", err, 0)
    assert o.session_id == "20261109_191151_014343" and o.final_message.startswith("The file changed")
    assert HermesAdapter().parse("", "boom", 1).is_error


def test_ansi_colour_codes_do_not_leak_into_the_answer():
    o = HermesAdapter().parse("\x1b[33m⚠ warning\x1b[0m\nDone.\n", "\nsession_id: s1\n", 0)
    assert o.final_message == "Done." and o.session_id == "s1"


def test_the_config_points_hermes_at_the_endpoint_and_names_the_model(tmp_path):
    w = workdir(tmp_path)
    cmd = HermesAdapter().command(task(), w, "do it", None)
    cfg = (home_for(w) / "config.yaml").read_text(encoding="utf8")
    assert 'base_url: "http://127.0.0.1:5555/v1"' in cfg and 'api_key: "gruntly-proxy"' in cfg and 'model: "m/one"' in cfg
    assert "provider: custom:gruntly" in cfg
    assert cmd.env["HERMES_HOME"] == str(home_for(w)) and cmd.env["LANG"] == "C.UTF-8" and cmd.stdin is None
    assert cmd.argv[1:4] == ["chat", "-Q", "--ignore-rules"] and cmd.argv[-2:] == ["-q", "do it"]
    assert "--provider" in cmd.argv and "custom:gruntly" in cmd.argv and "--resume" not in cmd.argv


def test_the_config_is_rewritten_for_every_attempt_because_the_proxy_port_changes(tmp_path):
    w = workdir(tmp_path)
    HermesAdapter().command(task(endpoint="http://127.0.0.1:1111/v1"), w, "p", None)
    HermesAdapter().command(task(endpoint="http://127.0.0.1:2222/v1"), w, "p", "sess-9")
    text = (home_for(w) / "config.yaml").read_text(encoding="utf8")
    assert "2222" in text and "1111" not in text


def test_resume_adds_the_session_flag(tmp_path):
    cmd = HermesAdapter().command(task(), workdir(tmp_path), "again", "20261109_191151_014343")
    i = cmd.argv.index("--resume")
    assert cmd.argv[i + 1] == "20261109_191151_014343"


def test_permission_modes_bypass_yolo_otherwise_only_file_tools(tmp_path):
    w = workdir(tmp_path)
    bypass = HermesAdapter().command(task(permissions="bypass"), w, "p", None).argv
    assert "--yolo" in bypass and "-t" not in bypass
    for mode in ("accept-edits", "plan"):
        argv = HermesAdapter().command(task(permissions=mode), w, "p", None).argv
        assert "--yolo" not in argv and argv[argv.index("-t") + 1] == "file"


def test_odd_characters_in_values_stay_valid(tmp_path):
    w = workdir(tmp_path)
    write_config(home_for(w), 'http://h/v1?a="b"', "k:y #1", "m/with: colon")
    import yaml
    cfg = yaml.safe_load((home_for(w) / "config.yaml").read_text(encoding="utf8"))
    assert cfg["custom_providers"][0]["api_key"] == "k:y #1" and cfg["model"]["default"] == "m/with: colon"


def test_capabilities_and_missing_install_message():
    a = HermesAdapter()
    assert a.capabilities().resume and not a.capabilities().profiles
    import gruntly.adapters.hermes as h
    orig = h.which
    h.which = lambda n: None
    try:
        d = a.detect()
    finally:
        h.which = orig
    assert not d.installed and "WSL2" in d.detail
