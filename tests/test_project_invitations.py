"""PR #29: one-time signup links, explicit role grants and token lifecycle."""

from datetime import datetime, timedelta, timezone
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from pmwizard.api import create_app
from pmwizard.auth import (
    AccessTokenService, AuthRepository, AuthService, AuthSettings,
)
from pmwizard.invitations import (
    AcceptInvitationRequest, ProjectInvitationService, digest_token,
)
from pmwizard.persistence import Base
from pmwizard.persistence.orm import (
    AppUserORM, AuditLogORM, ProjectInvitationORM, ProjectMembershipORM,
)

SETTINGS = AuthSettings(secret_key="invitation-test-signing-secret-key-1234567890")


@pytest.fixture()
def invitation_env():
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, class_=Session, expire_on_commit=False)
    tenant = uuid4()
    other_tenant = uuid4()
    with factory() as session:
        service = AuthService(session, AccessTokenService(SETTINGS))
        owner = service.create_user(
            tenant_id=tenant,
            email="manager@example.com",
            display_name="Project Manager",
            password="Strong owner password 123",
        )
        viewer = service.create_user(
            tenant_id=tenant,
            email="viewer@example.com",
            display_name="Viewer",
            password="Strong viewer password 123",
        )
        external = service.create_user(
            tenant_id=other_tenant,
            email="external@example.com",
            display_name="External",
            password="Strong external password 123",
        )
    tokens = AccessTokenService(SETTINGS)

    def headers(user, target_tenant=None):
        return {"Authorization": "Bearer " + tokens.issue(
            user_id=user.id, tenant_id=target_tenant or tenant,
        )}

    with TestClient(create_app(
        factory, auth_settings=SETTINGS, allow_trusted_headers=True,
    )) as client:
        project = client.post(
            "/v1/projects", json={"name": "Invitations Project"},
            headers=headers(owner),
        )
        assert project.status_code == 201, project.text
        project_id = UUID(project.json()["project_id"])
        yield {
            "client": client, "factory": factory, "owner": owner,
            "viewer": viewer, "external": external, "tenant": tenant,
            "other_tenant": other_tenant, "project_id": project_id,
            "headers": headers,
            "url": f"/v1/projects/{project_id}/invitations",
            "tokens": tokens,
        }
    engine.dispose()


def issue(v, email="newperson@example.com", role="reviewer"):
    return v["client"].post(
        v["url"],
        headers=v["headers"](v["owner"]),
        json={"email": email, "role": role},
    )


def redeem(v, token, *, display_name="Invited Collaborator", password="Strong invitation password 123"):
    return v["client"].post("/v1/invitations/accept", json={
        "token": token, "display_name": display_name, "password": password,
    })


def test_invitation_token_hash_only_one_time_signup_and_login(invitation_env):
    v = invitation_env
    issued = issue(v, email="NewPerson@Example.com")
    assert issued.status_code == 201, issued.text
    assert issued.headers["cache-control"] == "private, no-store"
    data = issued.json()
    token = data["token"]
    assert len(token) >= 40
    assert data["invitation"]["email"] == "newperson@example.com"
    assert data["invitation"]["status"] == "pending"
    assert data["invitation"]["role"] == "reviewer"

    with v["factory"]() as session:
        stored = session.scalar(
            select(ProjectInvitationORM).where(
                ProjectInvitationORM.id == UUID(data["invitation"]["id"]),
            )
        )
        assert stored.token_hash == digest_token(token)
        assert token != stored.token_hash
        assert stored.invited_email == "newperson@example.com"
        audits = session.scalars(select(AuditLogORM)).all()
        assert token not in str([
            (row.previous_state, row.proposed_state, row.final_state) for row in audits
        ])

    listing = v["client"].get(v["url"], headers=v["headers"](v["owner"]))
    assert listing.status_code == 200
    assert listing.json()["items"][0]["id"] == data["invitation"]["id"]
    assert "token" not in str(listing.json())

    accepted = redeem(v, token)
    assert accepted.status_code == 200, accepted.text
    assert accepted.headers["cache-control"] == "private, no-store"
    session_info = accepted.json()
    assert session_info["project_id"] == str(v["project_id"])
    assert session_info["user"]["email"] == "newperson@example.com"
    assert session_info["access_token"]
    user_id = UUID(session_info["user"]["id"])
    with v["factory"]() as session:
        member = session.scalar(
            select(ProjectMembershipORM).where(
                ProjectMembershipORM.tenant_id == v["tenant"],
                ProjectMembershipORM.project_id == v["project_id"],
                ProjectMembershipORM.user_id == user_id,
            )
        )
        assert member is not None
        assert member.permissions == ["project:read", "project:review"]
        user_row = session.get(AppUserORM, user_id)
        assert user_row.password_hash != "Strong invitation password 123"
        assert user_row.password_hash.startswith("$argon2id$")
        stored = session.get(ProjectInvitationORM, UUID(data["invitation"]["id"]))
        assert stored.status == "accepted"
        assert stored.accepted_user_id == user_id
        assert stored.accepted_at is not None
        all_audits = session.scalars(select(AuditLogORM)).all()
        assert "project_invitation_accepted" in [row.action for row in all_audits]
        assert token not in str([
            (row.previous_state, row.proposed_state, row.final_state) for row in all_audits
        ])

    auth_headers = {"Authorization": "Bearer " + session_info["access_token"]}
    projects = v["client"].get("/v1/projects", headers=auth_headers)
    assert projects.status_code == 200
    assert projects.json()["count"] == 1
    assert projects.json()["items"][0]["permissions"] == ["project:read", "project:review"]
    assert v["client"].get(v["url"], headers=auth_headers).status_code == 403
    assert redeem(v, token).status_code == 400
    assert v["client"].post("/v1/auth/login", json={
        "tenant_id": str(v["tenant"]),
        "email": "newperson@example.com",
        "password": "Strong invitation password 123",
    }).status_code == 200


def test_revoke_expires_and_reissue_after_expiration(invitation_env):
    v = invitation_env
    a = issue(v)
    assert a.status_code == 201
    a_id = UUID(a.json()["invitation"]["id"])
    a_token = a.json()["token"]
    duplicate = issue(v)
    assert duplicate.status_code == 409
    revoke = v["client"].delete(
        f"{v['url']}/{a_id}", headers=v["headers"](v["owner"]),
    )
    assert revoke.status_code == 204
    assert redeem(v, a_token).status_code == 400
    assert v["client"].delete(
        f"{v['url']}/{a_id}", headers=v["headers"](v["owner"]),
    ).status_code == 409

    b = issue(v)
    assert b.status_code == 201
    b_id = UUID(b.json()["invitation"]["id"])
    with v["factory"].begin() as session:
        row = session.get(ProjectInvitationORM, b_id)
        row.expires_at = datetime.now(timezone.utc) - timedelta(seconds=30)
    assert redeem(v, b.json()["token"]).status_code == 400
    statuses = v["client"].get(v["url"], headers=v["headers"](v["owner"])).json()
    assert next(item for item in statuses["items"] if item["id"] == str(b_id))["status"] == "expired"
    assert issue(v).status_code == 201


def test_authorization_and_cross_tenant_isolation(invitation_env):
    v = invitation_env
    client = v["client"]
    assert client.get(v["url"]).status_code == 401
    assert client.post(v["url"], json={"email": "new@example.com"}).status_code == 401
    assert client.get(v["url"], headers=v["headers"](v["viewer"])).status_code == 404
    assert client.post(v["url"], headers=v["headers"](v["viewer"]), json={
        "email": "new@example.com",
    }).status_code == 404
    assert client.get(v["url"], headers=v["headers"](v["external"], v["other_tenant"])).status_code == 404
    assert client.post(v["url"], headers={
        "X-PMWizard-Tenant-ID": str(v["tenant"]),
        "X-PMWizard-User-ID": str(v["owner"].id),
        "X-PMWizard-Permissions": "project:manage_members",
    }, json={"email": "new@example.com"}).status_code == 403

    # Existing user in the same tenant should go through member management.
    assert issue(v, email="viewer@example.com").status_code == 409
    # Identically named account in ANOTHER tenant must not block creation.
    allowed = issue(v, email="external@example.com")
    assert allowed.status_code == 201
    accepted = redeem(v, allowed.json()["token"])
    assert accepted.status_code == 200
    assert accepted.json()["user"]["tenant_id"] == str(v["tenant"])
    assert accepted.json()["user"]["id"] != str(v["external"].id)


@pytest.mark.parametrize("payload", [
    {"email": "invalid"},
    {"email": "new@example.com", "role": "admin"},
    {"email": "new@example.com", "role": "viewer", "permissions": ["*"]},
    {"email": "new@example.com", "role": "viewer", "tenant_id": str(uuid4())},
])
def test_invite_rejects_injected_permissions_and_bad_data(invitation_env, payload):
    v = invitation_env
    response = v["client"].post(
        v["url"], headers=v["headers"](v["owner"]), json=payload,
    )
    assert response.status_code == 422


@pytest.mark.parametrize("payload", [
    {"token": "not-a-real-invitation", "display_name": "Someone", "password": "Strong password 123"},
    {"token": "A" * 43, "display_name": "Someone", "password": "Strong password 123"},
    {"token": "B" * 43, "display_name": " ", "password": "Strong password 123"},
    {"token": "B" * 43, "display_name": "Someone", "password": "short"},
])
def test_accept_rejects_invalid_tokens_and_credentials(invitation_env, payload):
    v = invitation_env
    response = v["client"].post("/v1/invitations/accept", json=payload)
    assert response.status_code in (400, 422)
    with v["factory"]() as session:
        assert session.scalar(select(func.count()).select_from(ProjectInvitationORM)) == 0


def test_accept_transaction_rolls_back_if_membership_creation_fails(invitation_env, monkeypatch):
    v = invitation_env
    issued = issue(v)
    token = issued.json()["token"]
    inv_id = UUID(issued.json()["invitation"]["id"])

    def fail_membership(self, **kwargs):
        raise RuntimeError("membership write failed")

    monkeypatch.setattr(AuthRepository, "add_project_membership", fail_membership)
    with v["factory"]() as session:
        with pytest.raises(RuntimeError, match="membership write failed"):
            ProjectInvitationService(session).accept(
                command=AcceptInvitationRequest(
                    token=token,
                    display_name="New User",
                    password="Strong signup password 123",
                ),
                token_service=v["tokens"],
            )
    with v["factory"]() as session:
        assert session.get(ProjectInvitationORM, inv_id).status == "pending"
        assert session.scalar(select(func.count()).select_from(AppUserORM).where(
            AppUserORM.tenant_id == v["tenant"],
            AppUserORM.email == "newperson@example.com",
        )) == 0
        assert session.scalar(select(func.count()).select_from(AuditLogORM).where(
            AuditLogORM.action == "project_invitation_accepted",
        )) == 0


def test_enforces_bounded_pending_invitation_capacity(invitation_env):
    v = invitation_env
    for i in range(25):
        assert issue(v, email=f"guest{i}@example.com", role="viewer").status_code == 201
    rejected = issue(v, email="extra@example.com", role="viewer")
    assert rejected.status_code == 409
    assert "Too many pending invitations" in rejected.json()["detail"]
    page = v["client"].get(
        v["url"] + "?limit=10", headers=v["headers"](v["owner"]),
    ).json()
    assert page["count"] == 10
    assert page["next_offset"] == 10
