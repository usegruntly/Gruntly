import json

import pytest

from inventory.cli import run
from inventory.service import Inventory


def test_level_defaults_to_zero_and_equality_counts_as_low(tmp_path):
    inv = Inventory(tmp_path / "s.json")
    inv.add("a", 0, 1.0)
    inv.add("b", 3, 1.0, 3)
    inv.add("c", 4, 1.0, 3)
    assert [p.name for p in inv.low_stock()] == ["a", "b"]


def test_level_is_saved_and_old_files_still_load(tmp_path):
    s = tmp_path / "s.json"
    Inventory(s).add("x", 2, 1.0, 5)
    assert Inventory(s).products["x"].reorder_level == 5
    old = tmp_path / "old.json"
    old.write_text(json.dumps([{"name": "y", "quantity": 1, "price": 2.0}]))
    assert Inventory(old).products["y"].reorder_level == 0


def test_negative_level_is_refused(tmp_path):
    with pytest.raises(ValueError):
        Inventory(tmp_path / "s.json").add("x", 1, 1.0, -1)


def test_cli_add_with_level_and_low_command(tmp_path):
    s = tmp_path / "s.json"
    assert run(["low"], s) == "nothing is low"
    run(["add", "zeta", "2", "1.0", "5"], s)
    run(["add", "alpha", "1", "1.0", "1"], s)
    run(["add", "mid", "9", "1.0"], s)
    assert run(["low"], s) == "alpha: 1/1\nzeta: 2/5"
    assert run(["add", "neg", "1", "1.0", "-2"], s).startswith("error:")


def test_removing_stock_makes_a_product_low(tmp_path):
    inv = Inventory(tmp_path / "s.json")
    inv.add("p", 10, 1.0, 4)
    assert inv.low_stock() == []
    inv.remove("p", 6)
    assert [p.name for p in inv.low_stock()] == ["p"]
