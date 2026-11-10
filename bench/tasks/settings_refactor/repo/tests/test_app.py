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
