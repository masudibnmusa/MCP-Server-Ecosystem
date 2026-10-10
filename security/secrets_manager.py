"""Credentials come from the environment (.env locally). Never hardcode, never log.

To use a vault later (HashiCorp Vault, AWS Secrets Manager, ...), change get_secret() only.
"""
import os
import re

from dotenv import load_dotenv

load_dotenv()

_SECRET_NAME = re.compile(r"(KEY|TOKEN|SECRET|PASSWORD|CREDENTIAL)", re.IGNORECASE)


class MissingSecretError(RuntimeError):
    pass


def get_secret(name: str, default: str | None = None, required: bool = False) -> str | None:
    value = os.getenv(name, default)
    if required and not value:
        raise MissingSecretError(f"{name} is not set. Add it to .env (see .env.example).")
    return value


def redact(text: str) -> str:
    """Mask the value of any secret-looking environment variable in text (used by the logger)."""
    for name, value in os.environ.items():
        if value and len(value) >= 6 and _SECRET_NAME.search(name):
            text = text.replace(value, "***")
    return text