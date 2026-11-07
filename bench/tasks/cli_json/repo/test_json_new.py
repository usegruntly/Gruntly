import json

import pytest

from tool.cli import run


@pytest.mark.parametrize("cmd", ["list", "show", "stats", "users"])
def test_json_supported(cmd):
    assert isinstance(json.loads(run([cmd, "--json"])), dict)
