import os


def sender() -> str:
    return os.environ.get("APP_MAIL_FROM", "noreply@example.com")
