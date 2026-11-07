import json

from tool.cli import run


def test_status_text():
    assert run(["status"]) == "state: ok\nuptime: 42"


def test_status_json():
    assert json.loads(run(["status", "--json"])) == {"state": "ok", "uptime": 42}
