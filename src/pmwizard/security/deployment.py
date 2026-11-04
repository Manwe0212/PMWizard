"""Fail-closed configuration checks for non-demo PMWizard deployments.

This is deliberately not a deployment installer or full production audit.
The validator is also available as a preflight CLI that logs no secrets.
"""

from __future__ import annotations

import os
import re
from collections.abc import Mapping
from urllib.parse import urlparse

from sqlalchemy.engine import make_url


def validate_runtime_environment(env: Mapping[str, str]) -> None:
    stage = env.get("PMWIZARD_ENV", "development").strip().lower()
    if stage not in {"development", "test", "staging", "production"}:
        raise RuntimeError("PMWIZARD_ENV must be development, test, staging or production.")
    if stage not in {"staging", "production"}:
        return

    if env.get("PMWIZARD_ENABLE_LOCAL_DEMO", "").lower() in {"1", "true", "yes"}:
        raise RuntimeError("Demo data seeding is forbidden in staging and production.")

    secret = env.get("PMWIZARD_AUTH_SECRET", "")
    if (
        len(secret) < 48
        or len(set(secret)) < 16
        or any(word in secret.casefold() for word in ("example", "demo", "password", "changeme", "secret"))
    ):
        raise RuntimeError("Staging and production require a strong, independently generated auth secret.")

    db = env.get("PMWIZARD_DATABASE_URL", "")
    try:
        parsed_db = make_url(db)
    except Exception as exc:
        raise RuntimeError("A PostgreSQL database URL is required.") from exc
    if (
        parsed_db.drivername != "postgresql+psycopg"
        or not parsed_db.password
        or parsed_db.password.casefold() in {"pmwizard", "password", "changeme", "postgres"}
    ):
        raise RuntimeError("A non-default PostgreSQL connection is required.")
    if stage == "production":
        if parsed_db.query.get("sslmode") not in {"verify-full", "verify-ca"}:
            raise RuntimeError("Production PostgreSQL connections must verify TLS certificates.")

    public_url = env.get("PMWIZARD_PUBLIC_BASE_URL", "").rstrip("/")
    parsed = urlparse(public_url)
    if (
        parsed.scheme != "https"
        or not parsed.hostname
        or parsed.hostname in {"localhost", "127.0.0.1"}
        or parsed.username is not None
        or parsed.password is not None
        or parsed.query
        or parsed.fragment
        or parsed.path not in {"", "/"}
    ):
        raise RuntimeError("A public HTTPS application origin is required.")

    for flag in (
        "PMWIZARD_INVITATION_EMAIL_ENABLED",
        "PMWIZARD_INVITATION_REQUIRE_EMAIL_VERIFICATION",
        "PMWIZARD_PASSWORD_RESET_ENABLED",
    ):
        if env.get(flag, "").strip().lower() not in {"1", "true", "yes"}:
            raise RuntimeError(f"{flag} must be enabled outside development.")

    if env.get("PMWIZARD_NOTIFICATION_SMTP_STARTTLS", "").strip().lower() not in {
        "1", "true", "yes",
    }:
        raise RuntimeError("Verified SMTP STARTTLS is required.")
    if not env.get("PMWIZARD_NOTIFICATION_SMTP_HOST", "").strip():
        raise RuntimeError("Configured SMTP host is required.")
    if not env.get("PMWIZARD_NOTIFICATION_EMAIL_FROM", "").strip():
        raise RuntimeError("Configured SMTP sender is required.")

    try:
        minutes = int(env.get("PMWIZARD_ACCESS_TOKEN_MINUTES", "30"))
    except ValueError as exc:
        raise RuntimeError("Invalid session expiry setting.") from exc
    if minutes < 5 or minutes > 30:
        raise RuntimeError("Staging and production access tokens must expire within 5–30 minutes.")


if __name__ == "__main__":
    validate_runtime_environment(os.environ)
    print("PMWizard deployment configuration: passed.")
