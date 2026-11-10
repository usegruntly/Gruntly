import os


def connection_url() -> str:
    return os.environ.get("APP_DB_URL", "sqlite:///app.db")
