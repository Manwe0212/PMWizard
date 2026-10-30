"""Authenticated project creation: authorization, ownership and atomicity."""

from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from pmwizard.api import create_app
from pmwizard.auth import AccessTokenService, AuthRepository, AuthService, AuthSettings
from pmwizard.persistence import Base
from pmwizard.persistence.orm import AuditLogORM, ProjectMembershipORM, ProjectORM

SETTINGS = AuthSettings(secret_key="project-creation-test-secret-1234567890")


@pytest.fixture()
def project_env():
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, class_=Session, expire_on_commit=False)
    tenant = uuid4()
    with factory() as session:
        auth = AuthService(session, AccessTokenService(SETTINGS))
        user = auth.create_user(
            tenant_id=tenant,
            email="creator@example.com",
            display_name="Creator",
            password="Long secure test password",
        )
    with TestClient(create_app(factory, auth_settings=SETTINGS)) as client:
        response = client.post("/v1/auth/login", json={
            "tenant_id": str(tenant),
            "email": "creator@example.com",
            "password": "Long secure test password",
        })
        assert response.status_code == 200
        token = response.json()["access_token"]
        yield client, factory, tenant, user, {"Authorization": f"Bearer {token}"}
    engine.dispose()


def test_create_project_assigns_manager_membership_and_initial_audit(project_env):
    client, factory, tenant, user, headers = project_env
    assert client.get("/v1/projects", headers=headers).json()["count"] == 0

    response = client.post("/v1/projects", headers=headers, json={
        "name": "  Customer Enablement Launch  ",
        "description": "Operational onboarding and handover",
        "objective": "Streamline onboarding",
        "methodology": "hybrid",
        "start_date": "2026-11-01",
        "planned_end_date": "2027-01-31",
    })
    assert response.status_code == 201, response.text
    payload = response.json()
    assert payload["name"] == "Customer Enablement Launch"
    assert payload["role"] == "project_manager"
    assert payload["status"] == "planning"
    assert payload["permissions"] == ["project:read", "project:review"]
    project_id = payload["project_id"]
    listed = client.get("/v1/projects", headers=headers)
    assert listed.status_code == 200
    assert [item["project_id"] for item in listed.json()["items"]] == [project_id]
    memory = client.get(f"/v1/projects/{project_id}/memory", headers=headers)
    assert memory.status_code == 200, memory.text
    assert memory.json()["project"]["name"] == "Customer Enablement Launch"
    activity = client.get(f"/v1/projects/{project_id}/activity", headers=headers)
    assert activity.status_code == 200
    assert activity.json()["count"] == 1
    assert activity.json()["items"][0]["action"] == "project_created"
    assert activity.json()["items"][0]["actor_id"] == str(user.id)

    with factory() as session:
        from uuid import UUID
        project = session.get(ProjectORM, UUID(project_id))
        assert project.tenant_id == tenant
        assert project.project_manager_id == user.id
        assert project.description == "Operational onboarding and handover"
        assert project.objective == "Streamline onboarding"
        assert project.start_date.isoformat() == "2026-11-01"
        assert project.planned_end_date.isoformat() == "2027-01-31"
        membership = session.scalar(
            select(ProjectMembershipORM).where(
                ProjectMembershipORM.project_id == UUID(project_id),
            )
        )
        assert membership.tenant_id == tenant
        assert membership.user_id == user.id
        assert membership.permissions == ["project:read", "project:review"]
        audits = session.scalars(
            select(AuditLogORM).where(AuditLogORM.project_id == UUID(project_id))
        ).all()
        assert len(audits) == 1
        assert audits[0].action == "project_created"
        assert audits[0].final_state == {"status": "planning"}


def test_rejects_unauthenticated_and_trusted_header_creation(project_env):
    client, factory, tenant, user, headers = project_env
    assert client.post("/v1/projects", json={"name": "Project A"}).status_code == 401
    allowed_test_client = TestClient(
        create_app(factory, auth_settings=SETTINGS, allow_trusted_headers=True)
    )
    trusted = {
        "X-PMWizard-Tenant-ID": str(tenant),
        "X-PMWizard-User-ID": str(user.id),
        "X-PMWizard-Permissions": "project:read,project:review",
    }
    assert allowed_test_client.post(
        "/v1/projects", headers=trusted, json={"name": "Project B"}
    ).status_code == 403


@pytest.mark.parametrize("body", [
    {"name": ""},
    {"name": "  "},
    {"name": "AB"},
    {"name": "a" * 121},
    {"name": "Valid Project", "tenant_id": str(uuid4())},
    {"name": "Valid Project", "project_manager_id": str(uuid4())},
    {"name": "Valid Project", "permissions": ["admin:all"]},
    {"name": "Valid Project", "status": "completed"},
    {"name": "Valid Project", "methodology": "unrestricted"},
    {
        "name": "Valid Project",
        "start_date": "2027-02-01",
        "planned_end_date": "2027-01-31",
    },
])
def test_invalid_or_privilege_injection_is_rejected(project_env, body):
    client, factory, tenant, user, headers = project_env
    response = client.post("/v1/projects", headers=headers, json=body)
    assert response.status_code == 422
    with factory() as session:
        assert session.scalar(select(func.count()).select_from(ProjectORM)) == 0


def test_created_project_not_visible_to_other_tenants_or_users(project_env):
    client, factory, tenant, user, headers = project_env
    created = client.post(
        "/v1/projects", headers=headers, json={"name": "Private Team Initiative"}
    ).json()
    other_tenant = uuid4()
    with factory() as session:
        auth = AuthService(session, AccessTokenService(SETTINGS))
        other = auth.create_user(
            tenant_id=other_tenant,
            email="another@example.com",
            display_name="Another tenant",
            password="A different secure password",
        )
        colleague = auth.create_user(
            tenant_id=tenant,
            email="colleague@example.com",
            display_name="Colleague without membership",
            password="Another secure password",
        )
        other_token = AccessTokenService(SETTINGS).issue(
            user_id=other.id, tenant_id=other_tenant
        )
        colleague_token = AccessTokenService(SETTINGS).issue(
            user_id=colleague.id, tenant_id=tenant
        )
    for token in (other_token, colleague_token):
        scoped_headers = {"Authorization": f"Bearer {token}"}
        listing = client.get("/v1/projects", headers=scoped_headers)
        assert listing.status_code == 200
        assert listing.json()["items"] == []
        assert client.get(
            f"/v1/projects/{created['project_id']}/memory",
            headers=scoped_headers,
        ).status_code == 404


def test_membership_failure_rolls_back_project_and_audit(project_env, monkeypatch):
    client, factory, tenant, user, headers = project_env

    def deny_membership(self, **kwargs):
        raise RuntimeError("forced membership failure")

    monkeypatch.setattr(AuthRepository, "add_project_membership", deny_membership)
    # Assert atomicity at service layer rather than relying on HTTP 500 handling.
    from pmwizard.onboarding import CreateProjectRequest, ProjectOnboardingService
    with factory() as session:
        with pytest.raises(RuntimeError, match="forced membership failure"):
            ProjectOnboardingService(session).create(
                tenant_id=tenant,
                actor_id=user.id,
                command=CreateProjectRequest(name="Atomic Creation Test"),
            )
    with factory() as session:
        assert session.scalar(select(func.count()).select_from(ProjectORM)) == 0
        assert session.scalar(select(func.count()).select_from(ProjectMembershipORM)) == 0
        assert session.scalar(select(func.count()).select_from(AuditLogORM)) == 0
