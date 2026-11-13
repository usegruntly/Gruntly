"""The generic parent: a harness described in your settings, with nothing assumed about what it can do."""
import json
import sys

import pytest

from gruntly import parents, probe, providers
from gruntly.parents import base, generic, prompts


@pytest.fixture
def cfg(tmp_path, monkeypatch):
    monkeypatch.setenv("GRUNTLY_CONFIG_DIR", str(tmp_path / "cfg"))
    monkeypatch.setenv("GRUNTLY_STATE_DIR", str(tmp_path / "state"))
    (tmp_path / "cfg").mkdir()
    monkeypatch.chdir(tmp_path)
    return tmp_path


def _settings(tmp_path, text, where="global"):
    p = tmp_path / "cfg" / "config.toml" if where == "global" else tmp_path / ".gruntly.toml"
    p.write_text(text, encoding="utf8")


def test_without_settings_it_says_what_to_add(cfg):
    assert not generic.GenericParent().detect().installed and "[parent.generic]" in generic.GenericParent().detect().detail
    with pytest.raises(ValueError, match=r"needs a command: add \[parent.generic\] command"):
        generic.GenericParent().command("t", "delegating")
    r = base.run(generic.GenericParent(), "t", "delegating")
    assert r.returncode == 2 and r.outcome.is_error


def test_the_template_is_filled_the_prompt_goes_in_a_file_and_the_task_on_stdin(cfg):
    _settings(cfg, '[parent.generic]\ncommand = ["myagent", "--system-file", "{system_file}", "--model", "{model}", "--print"]\n')
    c = generic.GenericParent().command("Fix add().", "delegating", "m1")
    sf = str(cfg / "state" / "generic-parent" / "system.md")
    assert c.argv == ["myagent", "--system-file", sf, "--model", "m1", "--print"] and c.stdin == "Fix add()." and c.files == {sf: prompts.DELEGATING}
    assert len(c.notes) == 4 and all("not declared" in n for n in c.notes)


def test_the_project_settings_win_and_the_other_ways_of_giving_the_task_and_the_prompt_work(cfg):
    _settings(cfg, '[parent.generic]\ncommand = ["a"]\n[parent.generic.caps]\nrestrict_shell = true\n')
    _settings(cfg, '[parent.generic]\ncommand = "tool --sys {system} --task {task}"\ntask = "arg"\nsystem = "arg"\nworking_command = ["tool", "--yolo"]\n'
                   '[parent.generic.caps]\nreplace_system_prompt = true\n', where="project")
    c = generic.GenericParent().command("Do it", "delegating")
    assert c.argv == ["tool", "--sys", prompts.DELEGATING, "--task", "Do it"]                       # a string template is split like a shell would
    assert c.stdin is None and c.files == {}
    caps = generic.GenericParent().capabilities()
    assert caps.replace_system_prompt and caps.restrict_shell and not caps.restrict_tools and caps.experimental     # caps merge field by field, project over global
    assert generic.GenericParent().command("Do it", "working").argv == ["tool", "--yolo"]


def test_a_provider_passes_its_key_in_the_environment_only(cfg, monkeypatch):
    _settings(cfg, '[parent.generic]\ncommand = ["tool", "--base", "{base_url}", "--model", "{model}"]\n')
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-or-SECRET-xyz")
    c = generic.GenericParent().command("t", "delegating", "meta/llama", "openrouter")
    assert c.argv == ["tool", "--base", "https://openrouter.ai/api/v1", "--model", "meta/llama"]
    assert c.env["OPENROUTER_API_KEY"] == "sk-or-SECRET-xyz" and c.env["OPENAI_API_KEY"] == "sk-or-SECRET-xyz" and c.env["OPENAI_BASE_URL"] == "https://openrouter.ai/api/v1"
    assert "sk-or-SECRET-xyz" not in " ".join(c.argv) and "sk-or-SECRET-xyz" not in "".join(c.files.values())
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    with pytest.raises(ValueError, match="no API key for groq"):
        generic.GenericParent().command("t", "delegating", "m", "groq")
    with pytest.raises(ValueError, match="unknown provider 'nope'"):
        generic.GenericParent().command("t", "delegating", "m", "nope")


def test_the_output_is_the_answer_or_a_key_of_the_json_and_a_failure_is_an_error(cfg):
    _settings(cfg, '[parent.generic]\ncommand = ["x"]\n')
    assert generic.GenericParent().parse("  done \n", "", 0).final_message == "done"
    assert generic.GenericParent().parse("", "boom", 1).is_error and generic.GenericParent().parse("", "", 0).is_error
    _settings(cfg, '[parent.generic]\ncommand = ["x"]\noutput = "json:data.answer"\n')
    assert generic.GenericParent().parse('log\n{"data": {"answer": "42"}}', "", 0).final_message == "42"
    assert generic.GenericParent().parse('{"data": {}}', "", 0).is_error


def test_it_is_registered_and_never_claims_a_lean_setup_nobody_declared(cfg):
    assert "generic" in parents.names()
    c = parents.get_parent("generic").capabilities()
    assert not (c.replace_system_prompt or c.restrict_tools or c.restrict_shell or c.disable_extensions or c.reports_usage) and c.experimental


def test_end_to_end_a_python_one_liner_as_the_harness_reads_the_task_and_the_prompt_file_and_a_stub_sees_the_provider_key(cfg, tmp_path, monkeypatch):
    code = "import sys, os, json; sys.stdout.write(json.dumps({'r': sys.stdin.read() + '|' + open(sys.argv[1]).read()[:20] + '|' + os.environ['OPENAI_API_KEY']}))"
    _settings(cfg, "[parent.generic]\ncommand = " + json.dumps([sys.executable, "-c", code, "{system_file}"]) + '\noutput = "json:r"\n')
    with probe.StubServer() as srv:
        monkeypatch.setitem(providers.ALL, "stubprov", providers.Provider(name="stubprov", base_url=srv.base_url, key_env="STUB_API_KEY", default_model="stub-model"))
        monkeypatch.setenv("STUB_API_KEY", "dummy-key-123")
        r = base.run(generic.GenericParent(), "the task", "delegating", provider="stubprov", cwd=tmp_path, timeout_s=60)
    assert r.returncode == 0 and r.outcome.final_message == "the task|" + prompts.DELEGATING[:20] + "|dummy-key-123"
