"""The harness x role x provider matrix: every registered harness has a row, the protocol rules decide compatibility, and the text says what was checked."""
import json

import pytest

from gruntly import matrix, parents, providers
from gruntly.adapters import base as child_base


def test_every_registered_parent_and_child_harness_has_a_protocol_and_a_row():
    m = matrix.build()
    rows = {r["harness"]: r for r in m["harnesses"]}
    for n in parents.names():
        assert n in matrix.PROTOCOL, f"parent {n} has no protocol in matrix.PROTOCOL"
        assert rows[n]["parent"] is not None
    for n in matrix.CHILD_NAMES:
        assert n in matrix.PROTOCOL and n in rows
    for n in ("claude", "generic", "qwen", "opencode", "hermes"):
        assert rows[n]["child"] is not None
    for n, why in matrix.NO_CHILD.items():
        assert rows[n]["child"] is None and rows[n]["child_reason"] == why and why


def test_a_harness_without_a_child_role_says_why_and_the_child_adapters_listed_exist():
    for n in matrix.CHILD_NAMES:
        if n not in matrix.NO_CHILD:
            assert child_base.get_adapter(n).name == n


def test_the_delegating_level_is_lean_partial_or_no():
    from gruntly.parents.base import ParentCaps
    assert matrix.delegating_level(ParentCaps(replace_system_prompt=True, restrict_tools=True, restrict_shell=True, disable_extensions=True)) == "lean"
    assert matrix.delegating_level(ParentCaps(replace_system_prompt=True, restrict_tools=True, restrict_shell=False)) == "partial: any command can run, extensions not switched off"
    assert matrix.delegating_level(ParentCaps(modes=("working",))) == "no"
    rows = {r["harness"]: r for r in matrix.build()["harnesses"]}
    assert rows["claude"]["parent"]["delegating"] == "lean" and rows["aider"]["parent"]["delegating"] == "no" and rows["aider"]["parent"]["working"]
    assert rows["hermes"]["parent"]["delegating"].startswith("partial") and rows["hermes"]["parent"]["experimental"]


def test_compatibility_follows_the_wire_protocol_and_the_catalogs_responses_flag():
    cat = providers.ALL
    assert matrix.compatible("opencode", cat["groq"]) == "yes" and matrix.compatible("opencode", cat["ollama"]) == "yes"
    assert matrix.compatible("codex", cat["openai"]) == "yes" and matrix.compatible("codex", cat["deepseek"]) == "bridged" and matrix.compatible("codex", cat["mistral"]) == "bridged"      # chat-only providers go through the bridge
    assert matrix.compatible("gemini", cat["gemini"]) == "yes" and matrix.compatible("gemini", cat["openai"]) == "no"
    assert matrix.compatible("claude", cat["openai"]) == "no" and matrix.compatible("generic", cat["openai"]) == "unknown"


def test_the_matrix_is_json_and_the_text_names_what_was_checked_and_why_direct_has_no_child():
    m = matrix.build()
    json.dumps(m)
    assert set(m["providers"]) == set(providers.ALL) and all(set(g["harnesses"]) == {r["harness"] for r in m["harnesses"]} for g in m["providers"].values())
    text = matrix.render(m)
    assert "stub 1.19.5" in text and "live 1.19.5" in text and "stub 0.68.0 through the bridge" in text and "the direct parent is a loop" in text and "PROVIDER" in text
    for r in m["harnesses"]:
        if r["parent"]:
            assert r["parent"]["checked"], f"{r['harness']} parent has no CHECKED entry"
        if r["child"]:
            assert r["child"]["checked"], f"{r['harness']} child has no CHECKED entry"


def test_the_cli_prints_the_matrix_as_text_and_as_json(capsys):
    from gruntly import cli
    assert cli.main(["harness", "matrix"]) == 0
    text = capsys.readouterr().out
    assert "HARNESS" in text and "codex" in text and "PROVIDER" in text and "No child role" in text
    assert cli.main(["harness", "matrix", "--json"]) == 0
    data = json.loads(capsys.readouterr().out)
    assert {r["harness"] for r in data["harnesses"]} >= {"claude", "opencode", "codex", "gemini", "aider", "direct", "generic"} and "openai" in data["providers"]
