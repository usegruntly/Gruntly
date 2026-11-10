from .config import load


def sender() -> str:
    return load().mail_from
