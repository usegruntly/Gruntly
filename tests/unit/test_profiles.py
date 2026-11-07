"""Profiles: what the child is given (tools, prompt, inlined files) and how the adapters express it."""
import json
import subprocess
from pathlib import Path

import pytest

from gruntly import profiles, prompt
from gruntly.adapters.base import get_adapter
from gruntly.adapters.opencode import AGENT, OpenCodeAdapter, agent_config
from gruntly.adapters.qwen import QwenAdapter
from gruntly.spec import SpecError, build_spec


def git_repo(tmp_path, files):
    for rel, text in files.items():
        p = tmp_path / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text)
    subprocess.run(["git", "init", "-q", "-b", "main"], cwd=tmp_path, check=True)
    subprocess.run(["git", "add", "-A"], cwd=tmp_path, check=True)
    return tmp_path


def spec_for(**over):
    d = {"brief": "Fix add().", "allowed_paths": ["calc.py"], "acceptance": ["python -m pytest -q test_calc.py"]}
    d.update(over)
    return build_spec(d)


SMALL = {"calc.py": "def add(a, b):\n    return a - b\n", "test_calc.py": "from calc import add\n"}


# ------------------------------------------------------------------ resolution
def test_auto_picks_typist_for_a_few_small_literal_files(tmp_path):
    t = git_repo(tmp_path, SMALL)
    rp = profiles.resolve(spec_for(), t)
    assert rp.name == "typist" and rp.rewrite_only and rp.inline
    assert rp.targets == ["calc.py"]
    assert set(rp.tools) == {"write"}  # no test tool (evaluate & fix), no read (file is inlined), no edit (small file)


def test_auto_picks_worker_for_globs_or_big_scope(tmp_path):
    t = git_repo(tmp_path, SMALL)
    assert profiles.resolve(spec_for(allowed_paths=["**"]), t).name == "worker"
    big = git_repo(tmp_path / "big", {"calc.py": "x = 1\n" * 300})
    assert profiles.resolve(spec_for(), big).name == "worker"


def test_edit_tool_stays_for_files_too_big_to_rewrite(tmp_path):
    t = git_repo(tmp_path, {"calc.py": "x = 1\n" * 120})
    rp = profiles.resolve(spec_for(profile="typist"), t)
    assert rp.name == "typist" and not rp.rewrite_only and "edit" in rp.tools


def test_new_files_count_as_targets_and_are_announced(tmp_path):
    t = git_repo(tmp_path, {"test_calc.py": "x\n"})
    rp = profiles.resolve(spec_for(), t)
    assert rp.name == "typist" and rp.targets == ["calc.py"]
    assert "FILES TO CREATE: calc.py" in profiles.inline_block(spec_for(), rp, t)


def test_self_check_adds_the_test_tool_and_default_profile_has_no_tool_list(tmp_path):
    t = git_repo(tmp_path, SMALL)
    assert "test" in profiles.resolve(spec_for(self_check=True), t).tools
    d = profiles.resolve(spec_for(profile="default"), t)
    assert d.name == "default" and d.tools == []


def test_profile_context_floors(tmp_path):
    s = spec_for()
    assert profiles.context_floor(s, "typist") < profiles.context_floor(s, "worker") < profiles.context_floor(s, "default")
    assert profiles.context_floor(spec_for(min_context=1000), "default") == 1000


def test_bad_profile_is_a_spec_error():
    with pytest.raises(SpecError):
        spec_for(profile="wizard")


# ------------------------------------------------------------------ inlining
def test_inline_shows_targets_and_context_but_never_denied_or_env_files(tmp_path):
    t = git_repo(tmp_path, {**SMALL, ".env": "SECRET=1\n", "notes.md": "n\n", ".env.local": "K=2\n"})
    s = spec_for(allowed_paths=["calc.py", ".env"], context_files=["notes.md", ".env.local", "test_calc.py"],
                 deny_paths=["notes.md"])
    rp = profiles.resolve(s, t, "typist")
    block = profiles.inline_block(s, rp, t)
    assert "FILE calc.py" in block and "FILE test_calc.py" in block
    assert "SECRET" not in block and "K=2" not in block and "notes.md" not in block


def test_inline_respects_the_size_cap(tmp_path):
    t = git_repo(tmp_path, {"calc.py": "a = 1\n", "big.py": "x" * (profiles.INLINE_MAX_CHARS + 10)})
    s = spec_for(context_files=["big.py"])
    block = profiles.inline_block(s, profiles.resolve(s, t, "typist"), t)
    assert "FILE calc.py" in block and "big.py" not in block


def test_inline_off_for_default_and_when_disabled(tmp_path):
    t = git_repo(tmp_path, SMALL)
    assert profiles.inline_block(spec_for(profile="default"), profiles.resolve(spec_for(profile="default"), t), t) == ""
    s = spec_for(inline_files=False)
    rp = profiles.resolve(s, t)
    assert not rp.inline and "read" in rp.tools and profiles.inline_block(s, rp, t) == ""


# ------------------------------------------------------------------ prompts
def test_evaluate_and_fix_prompt_forbids_running_tests_and_names_no_command(tmp_path):
    t = git_repo(tmp_path, SMALL)
    s = spec_for()
    rp = profiles.resolve(s, t)
    text = prompt.first(s, prompt.Ctx(rp, profiles.inline_block(s, rp, t)))
    assert "Do not run tests" in text and "the system runs the tests" in text
    assert "pytest" not in text  # the child is never told the command
    assert "FILE calc.py" in text and "return a - b" in text
    assert "code you only show in your reply is ignored" in text
    assert len(text.split()) < 160


def test_self_check_prompt_allows_only_the_acceptance_command(tmp_path):
    t = git_repo(tmp_path, SMALL)
    s = spec_for(self_check=True)
    text = prompt.first(s, prompt.Ctx(profiles.resolve(s, t), ""))
    assert "python -m pytest -q test_calc.py" in text and "Do not run tests" not in text


def test_retry_hands_the_gate_output_back_without_involving_the_parent(tmp_path):
    t = git_repo(tmp_path, SMALL)
    s = spec_for()
    text = prompt.retry(s, "acceptance", "assert -1 == 5", ctx=prompt.Ctx(profiles.resolve(s, t), ""))
    assert "The system ran the checks" in text and "assert -1 == 5" in text and "Do not run tests" in text


def test_default_profile_prompt_is_the_original_one(tmp_path):
    t = git_repo(tmp_path, SMALL)
    s = spec_for(profile="default")
    assert prompt.first(s, prompt.Ctx(profiles.resolve(s, t), "")) == prompt.first(s)
    assert "Before you finish, run:" in prompt.first(s)


# ------------------------------------------------------------------ adapters
def test_opencode_slim_agent_has_only_the_profiles_tools(tmp_path):
    t = git_repo(tmp_path, SMALL)
    s = spec_for()
    cfg = agent_config(s, profiles.resolve(s, t))
    on = {k for k, v in cfg["tools"].items() if v}
    assert on == {"write", "edit"}  # OpenCode ties write and edit together; everything else is off
    # regression: without an explicit grant the model got no tools and pasted code into its reply
    assert cfg["permission"] == {"edit": "allow"}
    assert len(cfg["prompt"].split()) < 25


def test_opencode_self_check_allows_bash_for_the_acceptance_command_only(tmp_path):
    t = git_repo(tmp_path, SMALL)
    s = spec_for(self_check=True)
    cfg = agent_config(s, profiles.resolve(s, t))
    assert cfg["tools"]["bash"] is True
    rules = list(cfg["permission"]["bash"].items())
    assert rules[0] == ("*", "deny")  # last match wins, so the catch-all deny must come first
    assert ("python -m pytest -q test_calc.py", "allow") in rules


def test_opencode_command_selects_the_agent_and_disables_discovery(tmp_path):
    t = git_repo(tmp_path, SMALL)
    s = spec_for(harness="opencode", model="m")
    work = tmp_path / ".gruntly" / "worktrees" / "r_x"
    work.mkdir(parents=True)
    cmd = OpenCodeAdapter().command(s, work, "hi", None, profile=profiles.resolve(s, t))
    assert "--agent" in cmd.argv and cmd.argv[cmd.argv.index("--agent") + 1] == AGENT
    assert cmd.env["OPENCODE_DISABLE_CLAUDE_CODE"] == "1" and cmd.env["OPENCODE_DISABLE_PROJECT_CONFIG"] == "1"
    assert json.loads(cmd.env["OPENCODE_CONFIG_CONTENT"])["agent"][AGENT]["tools"]["bash"] is False
    plain = OpenCodeAdapter().command(s, work, "hi", None, profile=profiles.resolve(s, t, "default"))
    assert "--agent" not in plain.argv and "agent" not in json.loads(plain.env["OPENCODE_CONFIG_CONTENT"])


def test_qwen_slim_runs_bare_with_a_short_prompt_and_without_the_shell(tmp_path):
    t = git_repo(tmp_path, SMALL)
    s = spec_for(harness="qwen")
    cmd = QwenAdapter().command(s, tmp_path, "hi", None, profile=profiles.resolve(s, t))
    assert "--bare" in cmd.argv and "--system-prompt" in cmd.argv
    excluded = [cmd.argv[i + 1] for i, a in enumerate(cmd.argv) if a == "--exclude-tools"]
    assert "run_shell_command" in excluded and "notebook_edit" in excluded and "edit" not in excluded
    # regression: Qwen's edit tool needs read_file first; excluding it made the model loop for 27 requests
    assert "read_file" not in excluded
    assert "get_goal" in excluded and "update_goal" in excluded
    s2 = spec_for(harness="qwen", self_check=True)
    cmd2 = QwenAdapter().command(s2, tmp_path, "hi", None, profile=profiles.resolve(s2, t))
    assert "run_shell_command" not in [cmd2.argv[i + 1] for i, a in enumerate(cmd2.argv) if a == "--exclude-tools"]
    plain = QwenAdapter().command(s, tmp_path, "hi", None, profile=profiles.resolve(s, t, "default"))
    assert "--bare" not in plain.argv


def test_only_profile_aware_adapters_resolve_auto(tmp_path):
    assert get_adapter("opencode").capabilities().profiles and get_adapter("qwen").capabilities().profiles
    assert not get_adapter("generic").capabilities().profiles and not get_adapter("hermes").capabilities().profiles


def test_opencode_parser_reports_input_tokens_per_request():
    fx = Path(__file__).parents[1] / "fixtures" / "opencode" / "run_json_success.jsonl"
    out = OpenCodeAdapter().parse(fx.read_text(encoding="utf8"), "", 0)
    assert out.usage["requests"] == 4 and 10000 < out.usage["input_per_request"] < 12000


def test_qwen_parser_reports_requests_and_input_per_request():
    fx = Path(__file__).parents[1] / "fixtures" / "qwen" / "headless_json_success.json"
    out = QwenAdapter().parse(fx.read_text(encoding="utf8"), "", 0)
    assert out.usage["requests"] == 6 and out.usage["input_per_request"] > 10000


# ------------------------------------------------------------------ child bench plumbing
def _bench():
    import importlib.util
    spec = importlib.util.spec_from_file_location("run_child_bench", Path(__file__).parents[2] / "bench" / "run_child_bench.py")
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def test_bench_arms_map_to_profile_and_self_check():
    b = _bench()
    assert b.arm_settings("typist") == {"profile": "typist", "self_check": False}
    assert b.arm_settings("worker-self") == {"profile": "worker", "self_check": True}
    with pytest.raises(SystemExit):
        b.arm_settings("wizard")


def test_bench_report_counts_false_passes_and_first_try():
    b = _bench()
    rows = [
        {"task": "t", "brief": "precise", "arm": "typist", "rep": 1, "status": "passed", "attempts": 1, "first_try": True,
         "hidden_pass": True, "wall_s": 20, "child_tokens": 3000, "requests": 2, "input_per_request": 1500},
        {"task": "t", "brief": "precise", "arm": "typist", "rep": 2, "status": "passed", "attempts": 2, "first_try": False,
         "hidden_pass": False, "wall_s": 40, "child_tokens": 7000, "requests": 4, "input_per_request": 1700},
    ]
    out = b.report(rows, {"harness": "opencode", "model": "m"})
    line = next(ln for ln in out.splitlines() if ln.startswith("| typist |"))
    assert "| 50% | 50% | 1 |" in line  # first-try 50%, hidden pass 50%, one false pass
