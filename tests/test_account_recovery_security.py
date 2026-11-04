"""PR #31: verified password recovery, replay safety and JWT revocation."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from pmwizard.api import create_app
from pmwizard.auth import AccessTokenService, AuthService, AuthSettings
from pmwizard.invitations.email_delivery import InvitationEmailDelivery
from pmwizard.persistence import Base
from pmwizard.persistence.orm import (
    AppUserORM, AuditLogORM, PasswordResetORM, RevokedSessionORM,
)


SETTINGS = AuthSettings(secret_key="pr31-auth-security-signing-secret-longer-than-32")


class MailRecorder:
    def __init__(self, *, fail: bool = False):
        self.messages: list[tuple[str, str, str]] = []
        self.fail = fail

    def send(self, *, to_email: str, subject: str, text: str) -> None:
        if self.fail:
            raise RuntimeError("SENSITIVE SMTP CREDENTIALS MUST NOT LEAK")
        self.messages.append((to_email, subject, text))


@pytest.fixture()
def env():
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, class_=Session, expire_on_commit=False)
    tenant, alternate_tenant = uuid4(), uuid4()
    with factory() as session:
        auth = AuthService(session, AccessTokenService(SETTINGS))
        verified = auth.create_user(
            tenant_id=tenant,
            email="verified@example.com",
            display_name="Verified User",
            password="Original secure password 123",
        )
        unverified = auth.create_user(
            tenant_id=tenant,
            email="unverified@example.com",
            display_name="Unverified User",
            password="Original secure password 123",
        )
        outside = auth.create_user(
            tenant_id=alternate_tenant,
            email="verified@example.com",
            display_name="Other Tenant Verified",
            password="Original secure password 123",
        )
        for subject in (verified, outside):
            row = session.get(AppUserORM, subject.id)
            row.email_verified_at = datetime.now(timezone.utc)
        session.commit()
    mail = MailRecorder()
    delivery = InvitationEmailDelivery(
        provider=mail,
        public_base_url="https://pmwizard.example.com",
    )
    with TestClient(create_app(
        factory,
        auth_settings=SETTINGS,
        password_recovery_delivery=delivery,
        allow_trusted_headers=True,
    )) as client:
        yield {
            "client": client,
            "factory": factory,
            "tenant": tenant,
            "other_tenant": alternate_tenant,
            "verified": verified,
            "unverified": unverified,
            "outside": outside,
            "mail": mail,
            "delivery": delivery,
        }
    engine.dispose()


def login(v, *, tenant=None, email="verified@example.com", password="Original secure password 123"):
    return v["client"].post("/v1/auth/login", json={
        "tenant_id": str(tenant or v["tenant"]), "email": email, "password": password,
    })


def bearer(token):
    return {"Authorization": f"Bearer {token}"}


def request_reset(v, *, tenant=None, email="verified@example.com"):
    return v["client"].post("/v1/auth/password-reset/request", json={
        "tenant_id": str(tenant or v["tenant"]), "email": email,
    })


def reset_token(v) -> str:
    line = next(
        line for line in v["mail"].messages[-1][2].splitlines()
        if "/reset-password#token=" in line
    )
    return line.partition("#token=")[2].strip()


def confirm(v, token, password="Different secure password 2026"):
    return v["client"].post("/v1/auth/password-reset/confirm", json={
        "token": token, "password": password,
    })


def test_reset_verifies_mailbox_and_rotates_every_previous_session(env):
    v = env
    first = login(v)
    second = login(v)
    assert first.status_code == second.status_code == 200
    token_a, token_b = first.json()["access_token"], second.json()["access_token"]
    assert token_a != token_b

    result = request_reset(v)
    assert result.status_code == 202
    assert result.json()["message"].startswith("If this verified account exists")
    assert len(v["mail"].messages) == 1
    to_email, subject, message = v["mail"].messages[0]
    assert to_email == "verified@example.com"
    assert "reset" in subject.lower()
    assert "https://pmwizard.example.com/reset-password#token=" in message
    secret = reset_token(v)

    with v["factory"]() as session:
        saved = session.scalar(
            select(PasswordResetORM).where(PasswordResetORM.tenant_id == v["tenant"])
        )
        assert saved is not None
        assert saved.token_hash != secret
        assert len(saved.token_hash) == 64
        assert saved.used_at is None

    changed = confirm(v, secret)
    assert changed.status_code == 200, changed.text
    assert changed.json() == {"status": "password_updated", "sessions": "revoked"}
    assert confirm(v, secret).status_code == 400
    assert login(v).status_code == 401
    assert login(v, password="Different secure password 2026").status_code == 200
    for old in (token_a, token_b):
        res = v["client"].get("/v1/auth/me", headers=bearer(old))
        assert res.status_code == 401
    with v["factory"]() as session:
        user = session.get(AppUserORM, v["verified"].id)
        assert user.auth_version == 1
        assert user.password_hash.startswith("$argon2id$")
        assert "Different secure password 2026" not in user.password_hash
        reset = session.scalar(select(PasswordResetORM).where(
            PasswordResetORM.tenant_id == v["tenant"]
        ))
        assert reset.used_at is not None
        history = session.scalars(select(AuditLogORM).where(
            AuditLogORM.action == "account_password_reset",
        )).all()
        assert len(history) == 1
        assert "Different secure password" not in str(history[0].final_state)
        assert secret not in str(history[0].final_state)


def test_recovery_does_not_enumerate_unknown_inactive_or_unverified_accounts(env):
    v = env
    with v["factory"].begin() as session:
        row = session.get(AppUserORM, v["outside"].id)
        row.is_active = False

    requests = [
        request_reset(v, email="missing@example.com"),
        request_reset(v, email="unverified@example.com"),
        request_reset(v, tenant=v["other_tenant"], email="verified@example.com"),
    ]
    assert all(result.status_code == 202 for result in requests)
    assert len({result.text for result in requests}) == 1
    assert v["mail"].messages == []
    with v["factory"]() as session:
        assert session.scalar(select(func.count()).select_from(PasswordResetORM)) == 0


def test_per_account_cooldown_prevents_reset_email_bursts(env):
    v = env
    assert request_reset(v).status_code == 202
    assert request_reset(v).status_code == 202
    assert len(v["mail"].messages) == 1
    with v["factory"].begin() as session:
        row = session.scalar(select(PasswordResetORM))
        row.created_at = datetime.now(timezone.utc) - timedelta(minutes=16)
    assert request_reset(v).status_code == 202
    assert len(v["mail"].messages) == 2

    latest_secret = reset_token(v)
    assert confirm(v, latest_secret).status_code == 200
    with v["factory"]() as session:
        rows = session.scalars(select(PasswordResetORM)).all()
        assert len(rows) == 2
        assert all(row.used_at is not None for row in rows)


def test_expired_and_invalid_reset_links_cannot_update_account(env):
    v = env
    assert request_reset(v).status_code == 202
    token = reset_token(v)
    assert confirm(v, "a" * 43).status_code == 400
    assert confirm(v, "not-valid").status_code == 422
    with v["factory"].begin() as session:
        reset = session.scalar(select(PasswordResetORM))
        reset.expires_at = datetime.now(timezone.utc) - timedelta(seconds=1)
    assert confirm(v, token).status_code == 400
    assert login(v).status_code == 200


def test_mail_failure_is_silent_and_does_not_store_reset(env):
    v = env
    v["mail"].fail = True
    result = request_reset(v)
    assert result.status_code == 202
    assert "SENSITIVE" not in result.text
    assert len(v["mail"].messages) == 0
    with v["factory"]() as session:
        assert session.scalar(select(func.count()).select_from(PasswordResetORM)) == 0


def test_logout_revokes_only_this_token(env):
    v = env
    token_a = login(v).json()["access_token"]
    token_b = login(v).json()["access_token"]
    a = v["client"].post("/v1/auth/logout", headers=bearer(token_a))
    assert a.status_code == 204
    assert v["client"].get("/v1/auth/me", headers=bearer(token_a)).status_code == 401
    assert v["client"].get("/v1/auth/me", headers=bearer(token_b)).status_code == 200
    assert v["client"].post("/v1/auth/logout", headers=bearer(token_a)).status_code == 401
    with v["factory"]() as session:
        revocations = session.scalars(select(RevokedSessionORM)).all()
        assert len(revocations) == 1
        assert len(revocations[0].jti_hash) == 64
        assert token_a not in revocations[0].jti_hash


def test_logout_all_revokes_all_access_tokens_without_password_change(env):
    v = env
    token_a = login(v).json()["access_token"]
    token_b = login(v).json()["access_token"]
    result = v["client"].post("/v1/auth/logout-all", headers=bearer(token_b))
    assert result.status_code == 204
    for token in (token_a, token_b):
        assert v["client"].get("/v1/auth/me", headers=bearer(token)).status_code == 401
    assert login(v).status_code == 200
    with v["factory"]() as session:
        assert session.get(AppUserORM, v["verified"].id).auth_version == 1


def test_trusted_headers_cannot_logout_or_reset_authenticated_sessions(env):
    v = env
    trusted = {
        "X-PMWizard-Tenant-ID": str(v["tenant"]),
        "X-PMWizard-User-ID": str(v["verified"].id),
        "X-PMWizard-Permissions": "project:read,project:manage_members",
    }
    assert v["client"].post("/v1/auth/logout", headers=trusted).status_code == 403
    assert v["client"].post("/v1/auth/logout-all", headers=trusted).status_code == 403


def test_recovery_disabled_responds_503_without_mutating_account(env):
    v = env
    with TestClient(create_app(v["factory"], auth_settings=SETTINGS)) as client:
        req = client.post("/v1/auth/password-reset/request", json={
            "tenant_id": str(v["tenant"]), "email": "verified@example.com",
        })
        assert req.status_code == 503
        res = client.post("/v1/auth/password-reset/confirm", json={
            "token": "a" * 43, "password": "Another strong password",
        })
        assert res.status_code == 503
    with v["factory"]() as session:
        assert session.scalar(select(func.count()).select_from(PasswordResetORM)) == 0
