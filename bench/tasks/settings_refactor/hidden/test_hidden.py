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
