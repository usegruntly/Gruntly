import json
from pathlib import Path

from .models import Product


def load(path) -> dict:
    p = Path(path)
    if not p.is_file():
        return {}
    return {d["name"]: Product(d["name"], int(d["quantity"]), float(d["price"]), int(d.get("reorder_level", 0)))
            for d in json.loads(p.read_text())}


def save(path, products: dict) -> None:
    rows = [{"name": p.name, "quantity": p.quantity, "price": p.price, "reorder_level": p.reorder_level}
            for p in products.values()]
    Path(path).write_text(json.dumps(rows, indent=1))
