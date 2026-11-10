import os


def client_options() -> dict:
    return {"timeout": float(os.environ.get("APP_TIMEOUT", "5.0")),
            "retries": int(os.environ.get("APP_RETRIES", "3"))}
