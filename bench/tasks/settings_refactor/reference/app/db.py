from .config import load


def connection_url() -> str:
    return load().db_url
