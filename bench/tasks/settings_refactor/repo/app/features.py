import os


def enabled() -> list:
    raw = os.environ.get("APP_FEATURES", "")
    return [f.strip() for f in raw.split(",") if f.strip()]
