"""PR #32 — fail-closed staging and production configuration checks."""

import pytest

from pmwizard.security.deployment import validate_runtime_environment


STRONG_KEY = "p8A1qZ7mN3K5vB9rX4cT6dE2wL0uH8yJ1sF5gP7nV9zR3kQ6"


def settings(*, stage="staging"):
    return {
        "PMWIZARD_ENV": stage,
        "PMWIZARD_DATABASE_URL": (
            "postgresql+psycopg://pmuser:NonDefault!PasswordOf44Chars@stage-db:5432/pmwizard"
        ),
        "PMWIZARD_AUTH_SECRET": STRONG_KEY,
        "PMWIZARD_PUBLIC_BASE_URL": "https://staging.example.org",
        "PMWIZARD_ENABLE_LOCAL_DEMO": "false",
        "PMWIZARD_INVITATION_EMAIL_ENABLED": "true",
        "PMWIZARD_INVITATION_REQUIRE_EMAIL_VERIFICATION": "true",
        "PMWIZARD_PASSWORD_RESET_ENABLED": "true",
        "PMWIZARD_NOTIFICATION_SMTP_STARTTLS": "true",
        "PMWIZARD_NOTIFICATION_SMTP_HOST": "mail.example.org",
        "PMWIZARD_NOTIFICATION_EMAIL_FROM": "security@example.org",
        "PMWIZARD_ACCESS_TOKEN_MINUTES": "30",
    }


def test_staging_preflight_accepts_explicit_hardening():
    validate_runtime_environment(settings())


def test_production_requires_postgres_tls_verification():
    production = settings(stage="production")
    with pytest.raises(RuntimeError, match="verify TLS"):
        validate_runtime_environment(production)
    production["PMWIZARD_DATABASE_URL"] += "?sslmode=verify-full"
    validate_runtime_environment(production)


@pytest.mark.parametrize("field,value,reason", [
    ("PMWIZARD_ENV", "unexpected", "PMWIZARD_ENV"),
    ("PMWIZARD_ENABLE_LOCAL_DEMO", "true", "Demo"),
    ("PMWIZARD_AUTH_SECRET", "demo-password-123", "strong"),
    ("PMWIZARD_DATABASE_URL", "sqlite+pysqlite:///:memory:", "PostgreSQL"),
    ("PMWIZARD_PUBLIC_BASE_URL", "http://staging.example.org", "HTTPS"),
    ("PMWIZARD_PUBLIC_BASE_URL", "https://localhost", "HTTPS"),
    ("PMWIZARD_INVITATION_EMAIL_ENABLED", "false", "INVITATION_EMAIL_ENABLED"),
    ("PMWIZARD_INVITATION_REQUIRE_EMAIL_VERIFICATION", "false", "REQUIRE_EMAIL_VERIFICATION"),
    ("PMWIZARD_PASSWORD_RESET_ENABLED", "false", "PASSWORD_RESET_ENABLED"),
    ("PMWIZARD_NOTIFICATION_SMTP_STARTTLS", "false", "STARTTLS"),
    ("PMWIZARD_NOTIFICATION_SMTP_HOST", "", "SMTP"),
    ("PMWIZARD_NOTIFICATION_EMAIL_FROM", "", "sender"),
    ("PMWIZARD_ACCESS_TOKEN_MINUTES", "1440", "5–30"),
])
def test_preflight_rejects_unsafe_settings(field, value, reason):
    current = settings()
    current[field] = value
    with pytest.raises(RuntimeError, match=reason):
        validate_runtime_environment(current)


def test_local_demo_remains_compatible():
    validate_runtime_environment({"PMWIZARD_ENV": "development"})
    validate_runtime_environment({"PMWIZARD_ENV": "test"})


def test_weak_secret_and_production_db_tls_do_not_expose_credentials_in_error():
    current = settings()
    current["PMWIZARD_AUTH_SECRET"] = "UnsecurePassword"
    with pytest.raises(RuntimeError) as error:
        validate_runtime_environment(current)
    assert "UnsecurePassword" not in str(error.value)
    assert "NonDefault!PasswordOf44Chars" not in str(error.value)
