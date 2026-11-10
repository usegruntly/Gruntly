"""Generates two larger bench tasks that need exploring several files (output is committed).

  inventory_reorder  a feature end to end: model, JSON store (old files must still load), service and CLI
  settings_refactor  move APP_* environment reads from six modules into one typed Settings loader

Each folder has repo/ (starter), reference/ (solved files), hidden/test_hidden.py and task.yaml. Run this file to
regenerate and self-check: the hidden tests must fail on the starter and pass on the reference.
"""
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from textwrap import dedent

import yaml

ROOT = Path(__file__).parent / "tasks"


def w(path: Path, text: str):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(dedent(text).lstrip("\n"), encoding="utf8", newline="\n")


# ------------------------------------------------------------------------------------------------ inventory_reorder
INV_MODELS = """
from dataclasses import dataclass


@dataclass
class Product:
    name: str
    quantity: int
    price: float
"""
INV_MODELS_REF = """
from dataclasses import dataclass


@dataclass
class Product:
    name: str
    quantity: int
    price: float
    reorder_level: int = 0

    @property
    def low(self) -> bool:
        return self.quantity <= self.reorder_level
"""
INV_STORE = """
import json
from pathlib import Path

from .models import Product


def load(path) -> dict:
    p = Path(path)
    if not p.is_file():
        return {}
    return {d["name"]: Product(d["name"], int(d["quantity"]), float(d["price"])) for d in json.loads(p.read_text())}


def save(path, products: dict) -> None:
    rows = [{"name": p.name, "quantity": p.quantity, "price": p.price} for p in products.values()]
    Path(path).write_text(json.dumps(rows, indent=1))
"""
INV_STORE_REF = """
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
"""
INV_SERVICE = """
from . import store
from .models import Product


class Inventory:
    def __init__(self, path):
        self.path = path
        self.products = store.load(path)

    def add(self, name: str, quantity: int, price: float) -> Product:
        if quantity < 0 or price < 0:
            raise ValueError("quantity and price must not be negative")
        p = self.products.get(name)
        if p:
            p.quantity += quantity
            p.price = price
        else:
            p = self.products[name] = Product(name, quantity, price)
        store.save(self.path, self.products)
        return p

    def remove(self, name: str, quantity: int) -> Product:
        p = self.products.get(name)
        if p is None:
            raise KeyError(name)
        if quantity > p.quantity:
            raise ValueError(f"only {p.quantity} {name} in stock")
        p.quantity -= quantity
        store.save(self.path, self.products)
        return p

    def total_value(self) -> float:
        return round(sum(p.quantity * p.price for p in self.products.values()), 2)

    def names(self) -> list:
        return sorted(self.products)
"""
INV_SERVICE_REF = INV_SERVICE.replace(
    "    def add(self, name: str, quantity: int, price: float) -> Product:\n        if quantity < 0 or price < 0:\n            raise ValueError(\"quantity and price must not be negative\")",
    "    def add(self, name: str, quantity: int, price: float, reorder_level: int = 0) -> Product:\n        if quantity < 0 or price < 0 or reorder_level < 0:\n            raise ValueError(\"quantity, price and reorder level must not be negative\")",
).replace(
    "            p.price = price\n        else:\n            p = self.products[name] = Product(name, quantity, price)",
    "            p.price = price\n            p.reorder_level = reorder_level\n        else:\n            p = self.products[name] = Product(name, quantity, price, reorder_level)",
).replace(
    "    def names(self) -> list:",
    "    def low_stock(self) -> list:\n        return [p for _, p in sorted(self.products.items()) if p.low]\n\n    def names(self) -> list:",
)
INV_CLI = """
from .service import Inventory


def run(argv: list, path) -> str:
    inv = Inventory(path)
    cmd, args = argv[0], argv[1:]
    try:
        if cmd == "add":
            p = inv.add(args[0], int(args[1]), float(args[2]))
            return f"{p.name}: {p.quantity}"
        if cmd == "remove":
            p = inv.remove(args[0], int(args[1]))
            return f"{p.name}: {p.quantity}"
        if cmd == "value":
            return f"{inv.total_value():.2f}"
        if cmd == "list":
            return "\\n".join(inv.names()) or "empty"
    except (ValueError, KeyError) as e:
        return f"error: {e}"
    return f"error: unknown command {cmd}"
"""
INV_CLI_REF = INV_CLI.replace(
    "            p = inv.add(args[0], int(args[1]), float(args[2]))",
    "            p = inv.add(args[0], int(args[1]), float(args[2]), int(args[3]) if len(args) > 3 else 0)",
).replace(
    "        if cmd == \"list\":",
    "        if cmd == \"low\":\n            return \"\\n\".join(f\"{p.name}: {p.quantity}/{p.reorder_level}\" for p in inv.low_stock()) or \"nothing is low\"\n        if cmd == \"list\":",
)
INV_TESTS = """
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
"""
INV_TEST_NEW = """
from inventory.service import Inventory


def test_low_stock_lists_products_at_or_under_their_reorder_level(tmp_path):
    inv = Inventory(tmp_path / "s.json")
    inv.add("washer", 5, 0.1, 10)
    inv.add("bolt", 50, 0.5, 10)
    assert [p.name for p in inv.low_stock()] == ["washer"]
"""
INV_HIDDEN = """
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
    assert run(["low"], s) == "alpha: 1/1\\nzeta: 2/5"
    assert run(["add", "neg", "1", "1.0", "-2"], s).startswith("error:")


def test_removing_stock_makes_a_product_low(tmp_path):
    inv = Inventory(tmp_path / "s.json")
    inv.add("p", 10, 1.0, 4)
    assert inv.low_stock() == []
    inv.remove("p", 6)
    assert [p.name for p in inv.low_stock()] == ["p"]
"""


def make_inventory():
    d = ROOT / "inventory_reorder"
    shutil.rmtree(d, ignore_errors=True)
    repo = d / "repo"
    w(repo / "inventory" / "__init__.py", "")
    w(repo / "inventory" / "models.py", INV_MODELS)
    w(repo / "inventory" / "store.py", INV_STORE)
    w(repo / "inventory" / "service.py", INV_SERVICE)
    w(repo / "inventory" / "cli.py", INV_CLI)
    w(repo / "tests" / "test_inventory.py", INV_TESTS)
    w(repo / "tests" / "test_low_stock.py", INV_TEST_NEW)
    ref = d / "reference" / "inventory"
    w(ref / "models.py", INV_MODELS_REF)
    w(ref / "store.py", INV_STORE_REF)
    w(ref / "service.py", INV_SERVICE_REF)
    w(ref / "cli.py", INV_CLI_REF)
    w(d / "hidden" / "test_hidden.py", INV_HIDDEN)
    brief = ("Products need a reorder level: a product whose quantity is at or below its level is low on stock. Add it end "
             "to end. It is stored with the product (store files saved before this change must still load, as level 0). "
             "It can be set when a product is added: Inventory.add(name, quantity, price, reorder_level=0), and the CLI "
             "takes `add NAME QTY PRICE [LEVEL]`; a negative level is an error like a negative quantity. "
             "Inventory.low_stock() returns the low products sorted by name. The CLI gets a `low` command printing one "
             "`name: quantity/level` line per low product, or `nothing is low`.")
    _yaml(d, brief, "python -m pytest -q")


# ------------------------------------------------------------------------------------------------ settings_refactor
SET_MODULES = {
    "db.py": """
        import os


        def connection_url() -> str:
            return os.environ.get("APP_DB_URL", "sqlite:///app.db")
        """,
    "cache.py": """
        import os


        def ttl() -> int:
            return int(os.environ.get("APP_CACHE_TTL", "60"))
        """,
    "mailer.py": """
        import os


        def sender() -> str:
            return os.environ.get("APP_MAIL_FROM", "noreply@example.com")
        """,
    "http.py": """
        import os


        def client_options() -> dict:
            return {"timeout": float(os.environ.get("APP_TIMEOUT", "5.0")),
                    "retries": int(os.environ.get("APP_RETRIES", "3"))}
        """,
    "logging_setup.py": """
        import os


        def level() -> str:
            return os.environ.get("APP_LOG_LEVEL", "INFO").upper()
        """,
    "features.py": """
        import os


        def enabled() -> list:
            raw = os.environ.get("APP_FEATURES", "")
            return [f.strip() for f in raw.split(",") if f.strip()]
        """,
}
SET_CONFIG_REF = """
import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Settings:
    db_url: str = "sqlite:///app.db"
    cache_ttl: int = 60
    mail_from: str = "noreply@example.com"
    timeout: float = 5.0
    retries: int = 3
    log_level: str = "INFO"
    features: tuple = ()


def _num(name, kind, default):
    raw = os.environ.get(name)
    if raw is None:
        return default
    try:
        return kind(raw)
    except ValueError:
        raise ValueError(f"{name} must be a {kind.__name__}, got {raw!r}") from None


def load() -> Settings:
    feats = tuple(f.strip() for f in os.environ.get("APP_FEATURES", "").split(",") if f.strip())
    return Settings(os.environ.get("APP_DB_URL", "sqlite:///app.db"), _num("APP_CACHE_TTL", int, 60),
                    os.environ.get("APP_MAIL_FROM", "noreply@example.com"), _num("APP_TIMEOUT", float, 5.0),
                    _num("APP_RETRIES", int, 3), os.environ.get("APP_LOG_LEVEL", "INFO").upper(), feats)
"""
SET_REF_MODULES = {
    "db.py": "from .config import load\n\n\ndef connection_url() -> str:\n    return load().db_url\n",
    "cache.py": "from .config import load\n\n\ndef ttl() -> int:\n    return load().cache_ttl\n",
    "mailer.py": "from .config import load\n\n\ndef sender() -> str:\n    return load().mail_from\n",
    "http.py": "from .config import load\n\n\ndef client_options() -> dict:\n    s = load()\n    return {\"timeout\": s.timeout, \"retries\": s.retries}\n",
    "logging_setup.py": "from .config import load\n\n\ndef level() -> str:\n    return load().log_level\n",
    "features.py": "from .config import load\n\n\ndef enabled() -> list:\n    return list(load().features)\n",
}
SET_TESTS = """
from app import cache, db, features, http, logging_setup, mailer


def test_defaults():
    assert db.connection_url() == "sqlite:///app.db" and cache.ttl() == 60 and mailer.sender() == "noreply@example.com"
    assert http.client_options() == {"timeout": 5.0, "retries": 3} and logging_setup.level() == "INFO"
    assert features.enabled() == []


def test_overrides(monkeypatch):
    monkeypatch.setenv("APP_CACHE_TTL", "5")
    monkeypatch.setenv("APP_LOG_LEVEL", "debug")
    monkeypatch.setenv("APP_FEATURES", "a, b,")
    assert cache.ttl() == 5 and logging_setup.level() == "DEBUG" and features.enabled() == ["a", "b"]
"""
SET_TEST_NEW = """
from app.config import Settings, load


def test_load_returns_settings_with_the_defaults(monkeypatch):
    for k in ("APP_DB_URL", "APP_CACHE_TTL", "APP_TIMEOUT", "APP_RETRIES"):
        monkeypatch.delenv(k, raising=False)
    s = load()
    assert isinstance(s, Settings) and s.cache_ttl == 60 and s.retries == 3 and s.timeout == 5.0
"""
SET_HIDDEN = """
import dataclasses
import pathlib

import pytest

from app import cache, db, features, http, mailer
from app.config import load


def test_every_variable_still_works(monkeypatch):
    monkeypatch.setenv("APP_DB_URL", "postgres://x")
    monkeypatch.setenv("APP_MAIL_FROM", "a@b.c")
    monkeypatch.setenv("APP_TIMEOUT", "2.5")
    monkeypatch.setenv("APP_RETRIES", "7")
    monkeypatch.setenv("APP_FEATURES", "x")
    assert db.connection_url() == "postgres://x" and mailer.sender() == "a@b.c"
    assert http.client_options() == {"timeout": 2.5, "retries": 7} and features.enabled() == ["x"]


@pytest.mark.parametrize("name", ["APP_CACHE_TTL", "APP_TIMEOUT", "APP_RETRIES"])
def test_a_bad_number_names_the_variable(monkeypatch, name):
    monkeypatch.setenv(name, "lots")
    with pytest.raises(ValueError, match=name):
        load()


def test_settings_cannot_be_changed():
    with pytest.raises(dataclasses.FrozenInstanceError):
        load().cache_ttl = 1


def test_only_config_reads_the_environment():
    pkg = pathlib.Path(cache.__file__).parent
    readers = [p.name for p in pkg.glob("*.py") if p.name != "config.py"
               and ("os.environ" in p.read_text() or "getenv" in p.read_text())]
    assert readers == []
"""


def make_settings():
    d = ROOT / "settings_refactor"
    shutil.rmtree(d, ignore_errors=True)
    repo = d / "repo"
    w(repo / "app" / "__init__.py", "")
    w(repo / "app" / "config.py", '"""Application settings."""\n')
    for name, text in SET_MODULES.items():
        w(repo / "app" / name, text)
    w(repo / "tests" / "test_app.py", SET_TESTS)
    w(repo / "tests" / "test_config.py", SET_TEST_NEW)
    ref = d / "reference" / "app"
    w(ref / "config.py", SET_CONFIG_REF)
    for name, text in SET_REF_MODULES.items():
        (ref / name).write_text(text, encoding="utf8", newline="\n")
    w(d / "hidden" / "test_hidden.py", SET_HIDDEN)
    brief = ("Configuration is read from APP_* environment variables all over the app package. Move it into one place: a "
             "frozen Settings dataclass in app/config.py and a load() function that reads every variable when it is called, "
             "with the same names, defaults and types as today, and raises ValueError naming the variable when a number "
             "cannot be parsed. Every other module must use load() instead of reading the environment; behaviour stays the same.")
    _yaml(d, brief, "python -m pytest -q")


def _yaml(d: Path, brief: str, acceptance: str):
    (d / "task.yaml").write_text(yaml.safe_dump({"brief": brief, "allowed_paths": ["**"],
                                                 "acceptance": [{"cmd": acceptance, "timeout_s": 300}]}, sort_keys=False),
                                 encoding="utf8")


def self_check(name: str) -> None:
    d = ROOT / name
    for label, apply_ref, want in (("starter", False, False), ("reference", True, True)):
        with tempfile.TemporaryDirectory() as tmp:
            work = Path(tmp) / "r"
            shutil.copytree(d / "repo", work)
            if apply_ref:
                shutil.copytree(d / "reference", work, dirs_exist_ok=True)
            shutil.copy(d / "hidden" / "test_hidden.py", work / "test_hidden.py")
            r = subprocess.run([sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider"], cwd=work,
                               capture_output=True, text=True)
            ok = r.returncode == 0
            print(f"{name} {label}: {'pass' if ok else 'fail'}" + ("" if ok == want else "   <-- WRONG\n" + r.stdout[-1500:]))


if __name__ == "__main__":
    make_inventory()
    make_settings()
    self_check("inventory_reorder")
    self_check("settings_refactor")
