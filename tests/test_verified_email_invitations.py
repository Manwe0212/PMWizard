"""PR #30: verified inbox possession by opt-in SMTP invitation delivery."""

import os
from datetime import timezone
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from pmwizard.api import create_app
from pmwizard.auth import AccessTokenService, AuthService, AuthSettings
from pmwizard.invitations.email_delivery import (
    InvitationEmailDelivery,
    InvitationDeliveryUnavailable,
    VerifiedTlsSmtpProvider,
    delivery_from_environment,
)
from pmwizard.persistence import Base
from pmwizard.persistence.orm import (
    AppUserORM,
    AuditLogORM,
    ProjectInvitationORM,
    ProjectMembershipORM,
)

SETTINGS = AuthSettings(secret_key="pr30-test-auth-signing-key-at-least-32-bytes-long")


class MailRecorder:
    def __init__(self, fail=False):
        self.messages = []
        self.fail = fail

    def send(self, *, to_email, subject, text):
        if self.fail:
            raise RuntimeError("SMTP credentials: SECRET_SENSITIVE_DATA")
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
    tenant = uuid4()
    with factory() as session:
        manager = AuthService(session, AccessTokenService(SETTINGS)).create_user(
            tenant_id=tenant,
            email="manager@example.com",
            display_name="Inviting Manager",
            password="Secure invitation tests password!",
        )
    jwt = AccessTokenService(SETTINGS).issue(user_id=manager.id, tenant_id=tenant)
    headers = {"Authorization": f"Bearer {jwt}"}
    def client_with(provider=None, strict=False):
        delivery = None
        if provider is not None:
            delivery = InvitationEmailDelivery(
                provider=provider, public_base_url="https://pmwizard.example.com",
            )
        return TestClient(
            create_app(
                factory, auth_settings=SETTINGS,
                invitation_email_delivery=delivery,
                require_verified_invitations=strict,
            )
        )
    with client_with() as client:
        project = client.post("/v1/projects", headers=headers, json={
            "name": "Verified Mail Project",
        })
        assert project.status_code == 201, project.text
        project_id = project.json()["project_id"]
    yield {
        "client_with": client_with,
        "factory": factory,
        "tenant": tenant,
        "project_id": project_id,
        "headers": headers,
        "list_url": f"/v1/projects/{project_id}/invitations",
    }
    engine.dispose()


def _email_token(sent_text: str) -> str:
    from urllib.parse import urlsplit
    line = next(item for item in sent_text.splitlines() if "/invite#token=" in item)
    return line.strip().split("#token=", 1)[1]


def test_sent_email_never_returns_token_and_acceptance_verifies_email(env):
    v = env
    recorder = MailRecorder()
    with v["client_with"](recorder) as client:
        result = client.post(
            v["list_url"], headers=v["headers"], json={
                "email": "newmember@example.com",
                "role": "viewer",
                "delivery_method": "email",
            },
        )
        assert result.status_code == 201, result.text
        payload = result.json()
        assert payload["token"] is None
        assert payload["invitation"]["delivery_method"] == "email"
        assert payload["invitation"]["delivery_status"] == "sent"
        assert payload["invitation"]["delivered_at"]
        assert len(recorder.messages) == 1
        destination, subject, body = recorder.messages[0]
        assert destination == "newmember@example.com"
        assert "invitation" in subject.lower()
        token = _email_token(body)
        assert len(token) >= 40
        assert "https://pmwizard.example.com/invite#token=" in body
        assert token not in result.text

        listing = client.get(v["list_url"], headers=v["headers"])
        assert listing.status_code == 200
        assert token not in listing.text
        with v["factory"]() as db:
            invite = db.get(ProjectInvitationORM, UUID(payload["invitation"]["id"]))
            assert invite.token_hash != token
            assert invite.delivery_method == "email"
            assert invite.delivery_status == "sent"
            assert invite.delivered_at is not None
            assert invite.accepted_at is None

        acceptance = client.post("/v1/invitations/accept", json={
            "token": token,
            "display_name": "New Colleague",
            "password": "A valid secret password 123",
        })
        assert acceptance.status_code == 200, acceptance.text
        assert acceptance.json()["user"]["email_verified_at"] is not None
        uid = UUID(acceptance.json()["user"]["id"])
        with v["factory"]() as db:
            user = db.get(AppUserORM, uid)
            assert user.email_verified_at is not None
            member = db.scalar(select(ProjectMembershipORM).where(
                ProjectMembershipORM.user_id == uid,
                ProjectMembershipORM.tenant_id == v["tenant"],
                ProjectMembershipORM.project_id == UUID(v["project_id"]),
            ))
            assert member.role == "viewer"
            assert member.permissions == ["project:read"]
            audit = db.scalars(select(AuditLogORM)).all()
            assert token not in str([
                (row.previous_state, row.proposed_state, row.final_state) for row in audit
            ])
        assert client.post("/v1/invitations/accept", json={
            "token": token, "display_name": "Another Person",
            "password": "Another valid secret password",
        }).status_code == 400


def test_email_disabled_returns_safe_503_without_creating_invitation(env):
    v = env
    with v["client_with"]() as client:
        res = client.post(v["list_url"], headers=v["headers"], json={
            "email": "unsent@example.com",
            "role": "viewer",
            "delivery_method": "email",
        })
        assert res.status_code == 503, res.text
        assert "could not be sent" in res.text
        assert "token" not in res.text.lower()
    with v["factory"]() as db:
        assert db.scalar(select(func.count()).select_from(ProjectInvitationORM)) == 0


def test_provider_failure_rolls_back_and_sanitizes_errors(env):
    v = env
    sender = MailRecorder(fail=True)
    with v["client_with"](sender) as client:
        response = client.post(v["list_url"], headers=v["headers"], json={
            "email": "unsent@example.com",
            "role": "reviewer",
            "delivery_method": "email",
        })
        assert response.status_code == 503, response.text
        assert "SECRET_SENSITIVE_DATA" not in response.text
    with v["factory"]() as db:
        assert db.scalar(select(func.count()).select_from(ProjectInvitationORM)) == 0
        assert db.scalar(select(func.count()).select_from(AuditLogORM).where(
            AuditLogORM.action == "project_invitation_created",
        )) == 0


def test_manual_legacy_signup_does_not_claim_mailbox_verification(env):
    v = env
    with v["client_with"]() as client:
        issued = client.post(v["list_url"], headers=v["headers"], json={
            "email": "unverified@example.com",
            "role": "viewer",
        })
        assert issued.status_code == 201
        assert issued.json()["token"]
        assert issued.json()["invitation"]["delivery_method"] == "manual"
        accepted = client.post("/v1/invitations/accept", json={
            "token": issued.json()["token"],
            "display_name": "Manual User",
            "password": "A long manual password 123",
        })
        assert accepted.status_code == 200
        assert accepted.json()["user"]["email_verified_at"] is None


@pytest.mark.parametrize("env_vars", [
    {"PMWIZARD_PUBLIC_BASE_URL": "http://pmwizard.example.com"},
    {"PMWIZARD_PUBLIC_BASE_URL": "https://pmwizard.example.com/path"},
    {"PMWIZARD_PUBLIC_BASE_URL": "https://attacker@pmwizard.example.com"},
    {"PMWIZARD_PUBLIC_BASE_URL": "https://pmwizard.example.com#token"},
    {"PMWIZARD_PUBLIC_BASE_URL": ""},
])
def test_delivery_configuration_rejects_unsafe_urls(monkeypatch, env_vars):
    monkeypatch.setenv("PMWIZARD_INVITATION_EMAIL_ENABLED", "true")
    monkeypatch.setenv("PMWIZARD_NOTIFICATION_SMTP_HOST", "smtp.example.com")
    monkeypatch.setenv("PMWIZARD_NOTIFICATION_EMAIL_FROM", "invites@example.com")
    monkeypatch.setenv("PMWIZARD_NOTIFICATION_SMTP_STARTTLS", "true")
    for key, value in env_vars.items():
        monkeypatch.setenv(key, value)
    with pytest.raises(RuntimeError, match="public HTTPS origin"):
        delivery_from_environment()


def test_email_delivery_opt_in_disabled_by_default(monkeypatch):
    monkeypatch.delenv("PMWIZARD_INVITATION_EMAIL_ENABLED", raising=False)
    assert delivery_from_environment() is None
    monkeypatch.setenv("PMWIZARD_INVITATION_EMAIL_ENABLED", "true")
    monkeypatch.setenv("PMWIZARD_PUBLIC_BASE_URL", "https://pmwizard.example.com")
    monkeypatch.delenv("PMWIZARD_NOTIFICATION_SMTP_HOST", raising=False)
    with pytest.raises(RuntimeError, match="SMTP host"):
        delivery_from_environment()
    monkeypatch.setenv("PMWIZARD_NOTIFICATION_SMTP_HOST", "smtp.example.com")
    monkeypatch.setenv("PMWIZARD_NOTIFICATION_EMAIL_FROM", "invites@example.com")
    monkeypatch.setenv("PMWIZARD_NOTIFICATION_SMTP_STARTTLS", "false")
    with pytest.raises(RuntimeError, match="STARTTLS"):
        delivery_from_environment()


def test_smtp_transport_requires_verified_tls_and_supports_secret_free_relay(monkeypatch):
    calls = []
    class SmtpFake:
        def __init__(self, host, port, timeout):
            calls.append(("connect", host, port, timeout))
        def __enter__(self):
            return self
        def __exit__(self, *args):
            return None
        def ehlo(self):
            calls.append(("ehlo",))
        def starttls(self, *, context):
            assert context.verify_mode == 2
            assert context.check_hostname
            calls.append(("starttls",))
        def send_message(self, message):
            assert message["To"] == "receiver@example.com"
            calls.append(("sent",))

    provider = VerifiedTlsSmtpProvider(
        host="smtp.example.com", port=587, from_email="invites@example.com",
        starttls=True, smtp_factory=SmtpFake,
    )
    provider.send(
        to_email="receiver@example.com", subject="Invitation", text="Test message",
    )
    assert [item[0] for item in calls] == ["connect", "ehlo", "starttls", "ehlo", "sent"]


def test_strict_policy_blocks_manual_issuance_and_redemption(env):
    v = env
    sender = MailRecorder()

    # Previously issued manual links cannot be redeemed in strict mode.
    with v["client_with"]() as permissive:
        old = permissive.post(v["list_url"], headers=v["headers"], json={
            "email": "oldmanual@example.com", "role": "viewer",
        })
        assert old.status_code == 201
        old_token = old.json()["token"]

    with v["client_with"](sender, strict=True) as client:
        listing = client.get(v["list_url"], headers=v["headers"])
        assert listing.status_code == 200
        assert listing.json()["email_available"] is True
        assert listing.json()["strict_email_only"] is True
        denied = client.post(v["list_url"], headers=v["headers"], json={
            "email": "newmanual@example.com",
            "role": "viewer",
            "delivery_method": "manual",
        })
        assert denied.status_code == 403
        assert "requires verified email" in denied.json()["detail"]
        denied_redeem = client.post("/v1/invitations/accept", json={
            "token": old_token, "display_name": "Old Manual",
            "password": "A valid long manual password",
        })
        assert denied_redeem.status_code == 400

        sent = client.post(v["list_url"], headers=v["headers"], json={
            "email": "verifiedstrict@example.com",
            "role": "reviewer", "delivery_method": "email",
        })
        assert sent.status_code == 201
        assert sent.json()["token"] is None
        assert client.post("/v1/invitations/accept", json={
            "token": _email_token(sender.messages[0][2]),
            "display_name": "Verified Account",
            "password": "A valid long verified password",
        }).status_code == 200


def test_strict_policy_requires_configured_delivery_at_startup(monkeypatch):
    from pmwizard.api.app import create_default_app
    monkeypatch.setenv("PMWIZARD_DATABASE_URL", "sqlite+pysqlite:///:memory:")
    monkeypatch.setenv("PMWIZARD_AUTH_SECRET", "strict-mode-key-at-least-32-characters-long")
    monkeypatch.setenv("PMWIZARD_INVITATION_EMAIL_ENABLED", "false")
    monkeypatch.setenv("PMWIZARD_INVITATION_REQUIRE_EMAIL_VERIFICATION", "true")
    with pytest.raises(RuntimeError, match="Strict invitation verification"):
        create_default_app()
