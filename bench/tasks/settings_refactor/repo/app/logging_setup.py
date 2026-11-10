import os


def level() -> str:
    return os.environ.get("APP_LOG_LEVEL", "INFO").upper()
