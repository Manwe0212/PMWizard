"""Tests for Authentication + Project Selection V0."""

from uuid import uuid4

import jwt
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from pmwizard.api import create_app
from pmwizard.auth import (
    AccessTokenService,
    AuthService,
    AuthSettings,
)
from pmwizard.models import Project
from pmwizard.persistence import Base, ProjectMemoryService
from pmwizard.persistence.orm import AppUserORM


AUTH_SETTINGS = AuthSettings(
    secret_key="pmwizard-test-secret-key-must-be-at-least-32-bytes",
    access_token_minutes=30,
)


@pytest.fixture()
def auth_env():
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    factory = sessionmaker(
        bind=engine,
        class_=Session,
        expire_on_commit=False,
    )
    app = create_app(
        factory,
        auth_settings=AUTH_SETTINGS,
        allow_trusted_headers=False,
    )
    with TestClient(app) as client:
        yield client, factory


def _seed_user_and_projects(factory):
    tenant_id = uuid4()
    with factory() as session:
        memory = ProjectMemoryService(session)
        project_a = memory.create_project(
            tenant_id,
            Project(name="Project Alpha", status="active"),
        )
        project_b = memory.create_project(
            tenant_id,
            Project(name="Project Beta", status="active"),
        )
        hidden_project = memory.create_project(
            tenant_id,
            Project(name="Hidden Project", status="active"),
        )

        auth = AuthService(
            session,
            AccessTokenService(AUTH_SETTINGS),
        )
        user = auth.create_user(
            tenant_id=tenant_id,
            email="pm@example.com",
            display_name="Project Manager",
            password="A secure V0 password!",
        )
        auth.grant_project_access(
            tenant_id=tenant_id,
            user_id=user.id,
            project_id=project_a.id,
            role="project_manager",
            permissions=[
                "project:read",
                "project:review",
                "source:mail",
            ],
        )
        auth.grant_project_access(
            tenant_id=tenant_id,
            user_id=user.id,
            project_id=project_b.id,
            role="viewer",
            permissions=["project:read"],
        )

    return tenant_id, user, project_a, project_b, hidden_project


def _login(client, tenant_id, password="A secure V0 password!"):
    return client.post(
        "/v1/auth/login",
        json={
            "tenant_id": str(tenant_id),
            "email": "pm@example.com",
            "password": password,
        },
    )


def test_password_is_argon2_hashed_not_plaintext(auth_env) -> None:
    _, factory = auth_env
    tenant_id, user, *_ = _seed_user_and_projects(factory)

    with factory() as session:
        row = session.scalar(
            select(AppUserORM).where(
                AppUserORM.tenant_id == tenant_id,
                AppUserORM.id == user.id,
            )
        )
        assert row is not None
        assert row.password_hash != "A secure V0 password!"
        assert row.password_hash.startswith("$argon2id$")


def test_login_returns_short_lived_bearer_token(auth_env) -> None:
    client, factory = auth_env
    tenant_id, user, *_ = _seed_user_and_projects(factory)

    response = _login(client, tenant_id)

    assert response.status_code == 200
    payload = response.json()
    assert payload["token_type"] == "bearer"
    assert payload["expires_in"] == 1800
    assert payload["user"]["id"] == str(user.id)
    assert payload["user"]["email"] == "pm@example.com"
    assert payload["access_token"]


def test_invalid_password_returns_generic_401(auth_env) -> None:
    client, factory = auth_env
    tenant_id, *_ = _seed_user_and_projects(factory)

    response = _login(client, tenant_id, password="incorrect password")

    assert response.status_code == 401
    assert response.json()["detail"] == "Invalid email or password"
    assert response.headers["www-authenticate"] == "Bearer"


def test_bearer_token_authenticates_me(auth_env) -> None:
    client, factory = auth_env
    tenant_id, user, *_ = _seed_user_and_projects(factory)
    token = _login(client, tenant_id).json()["access_token"]

    response = client.get(
        "/v1/auth/me",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200
    assert response.json()["user"]["id"] == str(user.id)
    assert response.json()["user"]["display_name"] == "Project Manager"


def test_tampered_token_is_rejected(auth_env) -> None:
    client, factory = auth_env
    tenant_id, *_ = _seed_user_and_projects(factory)
    token = _login(client, tenant_id).json()["access_token"]
    parts = token.split(".")
    tampered_payload = parts[1][:-1] + ("A" if parts[1][-1] != "A" else "B")
    tampered = ".".join([parts[0], tampered_payload, parts[2]])

    response = client.get(
        "/v1/auth/me",
        headers={"Authorization": f"Bearer {tampered}"},
    )

    assert response.status_code == 401
    assert "Invalid or expired access token" in response.json()["detail"]


def test_token_does_not_embed_project_permissions(auth_env) -> None:
    client, factory = auth_env
    tenant_id, *_ = _seed_user_and_projects(factory)
    token = _login(client, tenant_id).json()["access_token"]

    claims = jwt.decode(
        token,
        AUTH_SETTINGS.secret_key,
        algorithms=["HS256"],
        audience=AUTH_SETTINGS.audience,
        issuer=AUTH_SETTINGS.issuer,
    )

    assert "permissions" not in claims
    assert "projects" not in claims


def test_project_selector_lists_only_memberships(auth_env) -> None:
    client, factory = auth_env
    tenant_id, _, project_a, project_b, hidden = _seed_user_and_projects(factory)
    token = _login(client, tenant_id).json()["access_token"]

    response = client.get(
        "/v1/projects",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["count"] == 2
    ids = {item["project_id"] for item in payload["items"]}
    assert ids == {str(project_a.id), str(project_b.id)}
    assert str(hidden.id) not in ids

    alpha = next(
        item for item in payload["items"]
        if item["project_id"] == str(project_a.id)
    )
    beta = next(
        item for item in payload["items"]
        if item["project_id"] == str(project_b.id)
    )
    assert alpha["role"] == "project_manager"
    assert "project:review" in alpha["permissions"]
    assert beta["role"] == "viewer"
    assert beta["permissions"] == ["project:read"]


def test_project_permissions_are_resolved_per_membership(auth_env) -> None:
    client, factory = auth_env
    tenant_id, _, project_a, project_b, _ = _seed_user_and_projects(factory)
    token = _login(client, tenant_id).json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    alpha = client.get(
        f"/v1/projects/{project_a.id}/inbox",
        headers=headers,
    )
    beta = client.get(
        f"/v1/projects/{project_b.id}/inbox",
        headers=headers,
    )

    assert alpha.status_code == 200
    assert beta.status_code == 200

    # Beta has read but not review permission. A nonexistent suggestion still
    # reaches the permission gate before resource lookup.
    fake_suggestion = uuid4()
    denied_review = client.post(
        f"/v1/projects/{project_b.id}/inbox/{fake_suggestion}/review",
        headers=headers,
        json={"status": "accepted"},
    )
    assert denied_review.status_code == 403
    assert "project:review" in denied_review.json()["detail"]


def test_non_member_project_is_not_discoverable(auth_env) -> None:
    client, factory = auth_env
    tenant_id, _, _, _, hidden = _seed_user_and_projects(factory)
    token = _login(client, tenant_id).json()["access_token"]

    response = client.get(
        f"/v1/projects/{hidden.id}/inbox",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 404
    assert response.json()["detail"] == "Project not found or not authorized."


def test_trusted_headers_are_disabled_by_default(auth_env) -> None:
    client, factory = auth_env
    tenant_id, user, project_a, *_ = _seed_user_and_projects(factory)

    response = client.get(
        f"/v1/projects/{project_a.id}/inbox",
        headers={
            "X-PMWizard-Tenant-ID": str(tenant_id),
            "X-PMWizard-User-ID": str(user.id),
            "X-PMWizard-Permissions": "project:read",
        },
    )

    assert response.status_code == 401
    assert response.json()["detail"] == "Authentication required"
