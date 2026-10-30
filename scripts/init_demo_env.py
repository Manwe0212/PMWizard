"""Create a private, local-only Docker Compose demo environment.

Uses unique random credentials for the disposable demo. Does not overwrite
an existing environment file or print infrastructure secrets.
"""

from __future__ import annotations

import os
import secrets
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
OUTPUT = ROOT / ".env.demo"


def initialize() -> Path:
    values = {
        "PMWIZARD_DEMO_DB_PASSWORD": secrets.token_urlsafe(32),
        "PMWIZARD_AUTH_SECRET": secrets.token_urlsafe(48),
        "PMWIZARD_DEMO_PASSWORD": secrets.token_urlsafe(24),
    }
    contents = (
        "# Local, disposable PMWizard demo ONLY. Never commit or reuse in production.\n"
        + "".join(f"{name}={value}\n" for name, value in values.items())
    )
    try:
        descriptor = os.open(OUTPUT, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    except FileExistsError as exc:
        raise RuntimeError(
            ".env.demo already exists; refusing to overwrite active credentials."
        ) from exc
    with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
        handle.write(contents)

    print("Created .env.demo with random credentials (private local file).")
    print("Demo login: demo@example.com")
    print("Demo workspace: 269ba0ba-35e4-4e86-bd2e-7d43f09d2550")
    print(f"Demo password (copy now): {values['PMWIZARD_DEMO_PASSWORD']}")
    print("To see it later, read PMWIZARD_DEMO_PASSWORD from your local .env.demo.")
    print("Do not share that file. Do not expose this local demo to the internet.")
    return OUTPUT


if __name__ == "__main__":
    initialize()
