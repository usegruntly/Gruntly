from app.config import Settings, load


def test_load_returns_settings_with_the_defaults(monkeypatch):
    for k in ("APP_DB_URL", "APP_CACHE_TTL", "APP_TIMEOUT", "APP_RETRIES"):
        monkeypatch.delenv(k, raising=False)
    s = load()
    assert isinstance(s, Settings) and s.cache_ttl == 60 and s.retries == 3 and s.timeout == 5.0
