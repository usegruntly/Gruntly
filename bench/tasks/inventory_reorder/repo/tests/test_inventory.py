from inventory.cli import run
from inventory.service import Inventory


def test_add_remove_value(tmp_path):
    inv = Inventory(tmp_path / "s.json")
    inv.add("bolt", 10, 0.5)
    inv.remove("bolt", 4)
    assert Inventory(tmp_path / "s.json").products["bolt"].quantity == 6
    assert inv.total_value() == 3.0


def test_cli_lists_and_reports_errors(tmp_path):
    s = tmp_path / "s.json"
    assert run(["add", "nut", "3", "0.25"], s) == "nut: 3"
    assert run(["list"], s) == "nut"
    assert run(["remove", "nut", "9"], s).startswith("error:")
