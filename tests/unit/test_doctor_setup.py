"""`gruntly doctor` checks what THIS project needs, not everything gruntly could ever use (website session, 2026-11-13: a project whose child is
Claude Code got `ok: false` because no local model server runs and half the providers have no key)."""
import json

import pytest

from gruntly import cli, doctor, models
from gruntly.adapters.base import Detection


class Fake:
    def __init__(self, installed=True, version="1.0"):
        self.installed, self.version = installed, version

    def detect(self):
        return Detection(self.installed, self.version if self.installed else None, "" if self.installed else "not installed (npm i -g x)")


def adapters(monkeypatch, **by_name):
    monkeypatch.setattr(doctor, "get_adapter", lambda name: by_name.get(name, Fake()))


def checks(rep):
    return {c["check"]: c for c in rep["checks"]}


def test_a_claude_child_needs_no_model_server_and_an_unreachable_one_is_not_a_failure(monkeypatch):
    adapters(monkeypatch)
    rep = doctor.run("http://127.0.0.1:1/v1", None, None, "claude")                    # nothing listens there
    c = checks(rep)
    assert rep["ok"] and c["model_server"]["ok"] and "not needed" in c["model_server"]["detail"] and "Claude Code" in c["model_server"]["detail"]
    assert c["child:claude"]["ok"] and not c["child:claude"]["warn"]


def test_a_generic_child_needs_no_model_server_either(monkeypatch):
    adapters(monkeypatch)
    rep = doctor.run("http://127.0.0.1:1/v1", None, None, "generic")
    assert rep["ok"] and "not needed" in checks(rep)["model_server"]["detail"] and "child:generic" not in checks(rep)


def test_a_local_model_still_needs_its_server(monkeypatch):
    adapters(monkeypatch)
    rep = doctor.run("http://127.0.0.1:1/v1", None, None, "opencode")
    assert not rep["ok"] and not checks(rep)["model_server"]["ok"]


def test_the_child_the_project_uses_must_be_installed_but_the_others_only_warn(monkeypatch):
    adapters(monkeypatch, qwen=Fake(False), opencode=Fake(False), claude=Fake(False))
    c = checks(doctor.run("http://127.0.0.1:1/v1", None, None, "claude"))
    assert not c["child:claude"]["ok"] and not c["child:claude"]["warn"]               # the configured one: a failure
    assert not c["child:qwen"]["ok"] and c["child:qwen"]["warn"]                       # the ones not in use: a note
    assert not doctor.run("http://127.0.0.1:1/v1", None, None, "claude")["ok"]


def test_the_check_names_the_default_children_when_there_is_no_project(monkeypatch):
    adapters(monkeypatch)
    names = set(checks(doctor.run("http://127.0.0.1:1/v1")))
    assert {"git", "model_server", "sandbox", "child:qwen", "child:opencode", "child:hermes"} <= names


@pytest.fixture
def project(repo, monkeypatch, tmp_path):
    monkeypatch.chdir(repo)
    monkeypatch.setenv("GRUNTLY_CONFIG_DIR", str(tmp_path / "cfg"))
    for k in ("GROQ_API_KEY", "GEMINI_API_KEY", "NVIDIA_API_KEY", "OPENROUTER_API_KEY", "OPENAI_API_KEY"):
        monkeypatch.delenv(k, raising=False)
    adapters(monkeypatch)
    return repo


def run_doctor(capsys, *flags):
    assert cli.main(["doctor", *flags]) == 0
    return capsys.readouterr().out


def test_the_command_for_a_claude_project_is_ok_and_keeps_the_provider_keys_to_one_note(project, capsys):
    (project / ".gruntly.toml").write_text('harness = "claude"\nmodel = "haiku"\n')
    rep = json.loads(run_doctor(capsys))
    c = checks(rep)
    assert rep["ok"] and "model_server" in c and "not needed" in c["model_server"]["detail"]
    assert not [n for n in c if n.startswith("provider:")]                              # no line per provider
    assert c["provider_keys"]["ok"] and "only needed if you use them" in c["provider_keys"]["detail"] and "groq" in c["provider_keys"]["detail"]


def test_a_hosted_project_needs_its_own_key_and_only_that_one(project, capsys, monkeypatch):
    (project / ".gruntly.toml").write_text('harness = "opencode"\nprovider = "groq"\nmodel = "m"\n')
    monkeypatch.setattr(models, "fetch", lambda name: [])
    rep = json.loads(run_doctor(capsys))
    c = checks(rep)
    assert not rep["ok"] and not c["provider:groq"]["ok"] and not c["provider:groq"]["warn"] and "gruntly auth set groq" in c["provider:groq"]["detail"]
    assert [n for n in c if n.startswith("provider:")] == ["provider:groq"]             # the other ten are not failures
    assert "groq" in c["provider_keys"]["detail"]


def test_the_human_view_is_one_readable_line_per_check(project, capsys):
    (project / ".gruntly.toml").write_text('harness = "claude"\nmodel = "haiku"\n')
    out = run_doctor(capsys, "--human").splitlines()
    assert out[0] == "everything this project needs is in place"
    assert any(line.startswith("  [ok  ] model_server: not needed") for line in out) and any(line.startswith("  [warn] sandbox") for line in out)
    assert not any(line.lstrip().startswith("{") for line in out)                        # not a dump of JSON
