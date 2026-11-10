from .config import load


def client_options() -> dict:
    s = load()
    return {"timeout": s.timeout, "retries": s.retries}
