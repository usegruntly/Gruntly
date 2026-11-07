import json

import pytest

from tool.cli import run

EXPECTED = {'list': {'items': ['a', 'b', 'c']}, 'show': {'id': 7, 'title': 'demo', 'tags': ['x', 'y']}, 'stats': {'count': 12, 'mean': 3.5}, 'users': {'users': [{'name': 'ann', 'role': 'admin'}, {'name': 'bo', 'role': 'dev'}]}}


@pytest.mark.parametrize("cmd", sorted(EXPECTED))
def test_json_matches(cmd):
    assert json.loads(run([cmd, "--json"])) == EXPECTED[cmd]


@pytest.mark.parametrize("cmd", ["jobs", "logs", "config"])
def test_other_commands_still_refuse_json(cmd):
    with pytest.raises(SystemExit):
        run([cmd, "--json"])


@pytest.mark.parametrize("cmd", sorted(EXPECTED))
def test_text_output_unchanged(cmd):
    assert "--json" not in run([cmd])
    assert run([cmd]).splitlines()
