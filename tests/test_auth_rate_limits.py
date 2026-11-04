"""PR #32 — durable, hashed authentication request throttles."""

from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from pmwizard.api import create_app
from pmwizard.auth import AuthService, AccessTokenService, AuthSettings
from pmwizard.persistence import Base
from pmwizard.persistence.orm import AuthRateLimitORM
from pmwizard.security.rate_limits import AuthRateLimiter, RateLimitExceeded

SETTINGS = AuthSettings(secret_key="pr32-rate-limit-testing-secret-with-high-entropy-1234567890")


@pytest.fixture()
def env():
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    factory = sessionmaker(
        bind=engine, class_=Session, expire_on_commit=False,
    )
    tenant_a, tenant_b = uuid4(), uuid4()
    with factory() as session:
        auth = AuthService(session, AccessTokenService(SETTINGS))
        auth.create_user(
            tenant_id=tenant_a,
            email="pm@example.com",
            display_name="Project Manager",
            password="Original strong password 123",
        )
    with TestClient(create_app(factory, auth_settings=SETTINGS)) as app:
        yield app, factory, tenant_a, tenant_b
    engine.dispose()


def login(client, tenant, email="pm@example.com", password="bad password"):
    return client.post("/v1/auth/login", json={
        "tenant_id": str(tenant), "email": email, "password": password,
    })


def test_login_limits_identity_and_preserves_other_identities(env):
    client, factory, tenant, other = env
    for _ in range(12):
        assert login(client, tenant).status_code == 401
    limited = login(client, tenant)
    assert limited.status_code == 429
    assert int(limited.headers["retry-after"]) > 0
    assert "password" not in limited.text

    # Rate limits use tenant+identity, not a global block on all users.
    assert login(client, tenant, email="another@example.com").status_code == 401
    assert login(client, other, email="pm@example.com").status_code == 401

    with factory() as session:
        counters = session.scalars(select(AuthRateLimitORM)).all()
        assert counters
        for item in counters:
            assert len(item.key_hash) == 64
            assert "pm@example.com" not in item.key_hash
            assert "testclient" not in item.key_hash
            assert item.hits > 0


def test_atomic_counts_survive_multiple_instances_on_shared_database(env):
    client, factory, tenant, other = env
    # A second FastAPI instance uses the same database and signing secret.
    with TestClient(create_app(factory, auth_settings=SETTINGS)) as second:
        for n in range(6):
            assert login(client if n % 2 == 0 else second, tenant).status_code == 401
        for n in range(6):
            assert login(second if n % 2 == 0 else client, tenant).status_code == 401
        assert login(second, tenant).status_code == 429


def test_counter_window_rollover_is_bounded_and_keyed(env):
    client, factory, tenant, other = env
    limiter = AuthRateLimiter(SETTINGS.secret_key)
    base = datetime(2026, 11, 4, 12, 0, tzinfo=timezone.utc)
    identity = f"{tenant}:pm@example.com"
    with factory() as session:
        for _ in range(12):
            limiter.check(
                session, route="login", source="127.0.0.1",
                identity=identity, now=base,
            )
        with pytest.raises(RateLimitExceeded) as error:
            limiter.check(
                session, route="login", source="127.0.0.1",
                identity=identity, now=base,
            )
        assert error.value.retry_after == 900
        # Next 15-minute window gets an independent digest and counter.
        limiter.check(
            session, route="login", source="127.0.0.1",
            identity=identity, now=base + timedelta(minutes=15),
        )
        assert len(session.scalars(select(AuthRateLimitORM)).all()) == 4


def test_recovery_request_limits_account_without_exposing_account_state(env):
    client, factory, tenant, other = env
    # Recovery is disabled in this test fixture. Requests should get 503
    # without consuming rate limits until SMTP is deliberately configured.
    request = {"tenant_id": str(tenant), "email": "pm@example.com"}
    for _ in range(3):
        result = client.post("/v1/auth/password-reset/request", json=request)
        assert result.status_code == 503
    with factory() as session:
        assert not session.scalars(select(AuthRateLimitORM)).all()


def test_rejects_unsupported_throttle_routes_and_short_secrets(env):
    with pytest.raises(ValueError):
        AuthRateLimiter("short")
    with env[1]() as session:
        with pytest.raises(ValueError, match="Unknown rate limit route"):
            AuthRateLimiter(SETTINGS.secret_key).check(
                session, route="not-an-auth-route", source="127.0.0.1",
            )
