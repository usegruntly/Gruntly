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
