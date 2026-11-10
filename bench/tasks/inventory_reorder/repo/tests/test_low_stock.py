from inventory.service import Inventory


def test_low_stock_lists_products_at_or_under_their_reorder_level(tmp_path):
    inv = Inventory(tmp_path / "s.json")
    inv.add("washer", 5, 0.1, 10)
    inv.add("bolt", 50, 0.5, 10)
    assert [p.name for p in inv.low_stock()] == ["washer"]
