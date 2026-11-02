"""PR #28: access-scoped project memberships and role governance."""

from datetime import datetime, timezone
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from pmwizard.api import create_app
from pmwizard.auth import AccessTokenService, AuthRepository, AuthService, AuthSettings
from pmwizard.members import (
    AddProjectMemberRequest,
    ProjectMemberService,
    ProjectRole,
)
from pmwizard.persistence import Base
from pmwizard.persistence.orm import (
    AppUserORM,
    AuditLogORM,
    ProjectMembershipORM,
    ProjectORM,
)

SETTINGS = AuthSettings(secret_key="pr28-membership-tests-secret-key-long-enough-2026")


@pytest.fixture()
def members_env():
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, class_=Session, expire_on_commit=False)
    tenant, another_tenant = uuid4(), uuid4()
    with factory() as session:
        auth = AuthService(session, AccessTokenService(SETTINGS))
        owner = auth.create_user(
            tenant_id=tenant, email="owner@example.com", display_name="Owner",
            password="long-test-owner-password",
        )
        reviewer = auth.create_user(
            tenant_id=tenant, email="reviewer@example.com", display_name="Reviewer",
            password="long-test-reviewer-password",
        )
        viewer = auth.create_user(
            tenant_id=tenant, email="viewer@example.com", display_name="Viewer",
            password="long-test-viewer-password",
        )
        outsider = auth.create_user(
            tenant_id=tenant, email="outsider@example.com", display_name="Outsider",
            password="long-test-outsider-password",
        )
        external = auth.create_user(
            tenant_id=another_tenant, email="external@example.com",
            display_name="External", password="long-test-external-password",
        )

    tokens = AccessTokenService(SETTINGS)
    def headers(user, tenant_id=tenant):
        return {
            "Authorization": "Bearer " + tokens.issue(
                tenant_id=tenant_id, user_id=user.id,
            )
        }

    with TestClient(create_app(factory, auth_settings=SETTINGS,
                               allow_trusted_headers=True)) as client:
        created = client.post(
            "/v1/projects",
            headers=headers(owner),
            json={"name": "Secure Project Team"},
        )
        assert created.status_code == 201, created.text
        project_id = UUID(created.json()["project_id"])
        yield {
            "factory": factory,
            "client": client,
            "tenant": tenant,
            "another_tenant": another_tenant,
            "project_id": project_id,
            "owner": owner,
            "reviewer": reviewer,
            "viewer": viewer,
            "outsider": outsider,
            "external": external,
            "headers": headers,
            "url": f"/v1/projects/{project_id}/members",
        }
    engine.dispose()


def test_owner_can_add_existing_user_and_grant_only_project_role(members_env):
    v = members_env
    client, url, owner_headers = v["client"], v["url"], v["headers"](v["owner"])

    listed = client.get(url, headers=owner_headers)
    assert listed.status_code == 200
    assert listed.json()["count"] == 1
    assert listed.json()["next_offset"] is None
    original = listed.json()["items"][0]
    assert original["is_owner"] is True
    assert original["user_id"] == str(v["owner"].id)
    assert set(original["permissions"]) == {
        "project:read", "project:review", "project:manage_members",
    }

    add = client.post(url, headers=owner_headers, json={
        "email": "REVIEWER@example.com", "role": "reviewer",
    })
    assert add.status_code == 201, add.text
    member = add.json()
    assert member["user_id"] == str(v["reviewer"].id)
    assert member["role"] == "reviewer"
    assert member["permissions"] == ["project:read", "project:review"]
    assert member["is_owner"] is False

    review_headers = v["headers"](v["reviewer"])
    assert client.get(f"/v1/projects/{v['project_id']}/memory", headers=review_headers).status_code == 200
    assert client.get(url, headers=review_headers).status_code == 403
    with v["factory"]() as session:
        membership = session.scalar(
            select(ProjectMembershipORM).where(
                ProjectMembershipORM.tenant_id == v["tenant"],
                ProjectMembershipORM.user_id == v["reviewer"].id,
                ProjectMembershipORM.project_id == v["project_id"],
            )
        )
        assert membership.permissions == ["project:read", "project:review"]
        rows = session.scalars(
            select(AuditLogORM).where(
                AuditLogORM.tenant_id == v["tenant"],
                AuditLogORM.project_id == v["project_id"],
            )
        ).all()
        assert [row.action for row in rows] == [
            "project_created", "project_member_added",
        ]
        assert all("reviewer@example.com" not in str(row.final_state) for row in rows)
        assert all("password" not in str(row.final_state) for row in rows)


def test_role_change_and_revoke_enforced_by_next_request(members_env):
    v = members_env
    client, url = v["client"], v["url"]
    headers = v["headers"](v["owner"])
    member_url = f"{url}/{v['viewer'].id}"
    assert client.post(url, headers=headers, json={
        "email": "viewer@example.com",
        "role": "viewer",
    }).status_code == 201

    viewer_headers = v["headers"](v["viewer"])
    assert client.get(f"/v1/projects/{v['project_id']}/memory", headers=viewer_headers).status_code == 200
    assert client.get(url, headers=viewer_headers).status_code == 403
    assert client.post(
        f"/v1/projects/{v['project_id']}/inbox/{uuid4()}/review",
        headers=viewer_headers,
        json={"status": "accepted"},
    ).status_code == 403

    updated = client.patch(member_url, headers=headers, json={"role": "project_manager"})
    assert updated.status_code == 200
    assert updated.json()["role"] == "project_manager"
    assert "project:manage_members" in updated.json()["permissions"]
    assert client.get(url, headers=viewer_headers).status_code == 200

    # Another manager may modify the original actor only? Self and original
    # project owner are protected, so access to that member cannot be revoked.
    assert client.delete(f"{url}/{v['owner'].id}", headers=viewer_headers).status_code == 409
    assert client.patch(member_url, headers=viewer_headers, json={"role": "viewer"}).status_code == 409

    downgraded = client.patch(member_url, headers=headers, json={"role": "reviewer"})
    assert downgraded.status_code == 200
    assert downgraded.json()["permissions"] == ["project:read", "project:review"]
    assert client.get(url, headers=viewer_headers).status_code == 403

    deleted = client.delete(member_url, headers=headers)
    assert deleted.status_code == 204
    assert not deleted.content
    assert client.get(f"/v1/projects/{v['project_id']}/memory", headers=viewer_headers).status_code == 404
    assert client.delete(member_url, headers=headers).status_code == 404
    with v["factory"]() as session:
        events = session.scalars(
            select(AuditLogORM.action).where(
                AuditLogORM.tenant_id == v["tenant"],
                AuditLogORM.project_id == v["project_id"],
            )
        ).all()
        assert "project_member_role_changed" in events
        assert "project_member_removed" in events


def test_owner_and_manager_cannot_modify_self_or_original_owner(members_env):
    v = members_env
    client, url = v["client"], v["url"]
    headers = v["headers"](v["owner"])
    assert client.patch(
        f"{url}/{v['owner'].id}", headers=headers, json={"role": "viewer"}
    ).status_code == 409
    assert client.delete(f"{url}/{v['owner'].id}", headers=headers).status_code == 409
    assert client.get(url, headers=headers).json()["items"][0]["role"] == "project_manager"


def test_no_tenant_directory_leak_and_no_cross_project_access(members_env):
    v = members_env
    client, url = v["client"], v["url"]
    headers = v["headers"](v["owner"])
    assert client.get(url, headers=v["headers"](v["outsider"])).status_code == 404
    assert client.get(url).status_code == 401
    assert client.get(url, headers={
        "X-PMWizard-Tenant-ID": str(v["tenant"]),
        "X-PMWizard-User-ID": str(v["owner"].id),
        "X-PMWizard-Permissions": "project:read,project:manage_members",
    }).status_code == 403
    assert client.post(url, headers=headers, json={
        "email": "external@example.com", "role": "viewer",
    }).status_code == 404
    assert client.post(url, headers=headers, json={
        "email": "missing@example.com", "role": "viewer",
    }).status_code == 404
    assert client.post(url, headers=headers, json={
        "email": "reviewer@example.com", "role": "viewer",
    }).status_code == 201
    assert client.post(url, headers=headers, json={
        "email": "reviewer@example.com", "role": "viewer",
    }).status_code == 409
    assert client.get(url, headers=v["headers"](v["external"], v["another_tenant"])).status_code == 404
    other_headers = v["headers"](v["reviewer"])
    assert client.post(url, headers=other_headers, json={
        "email": "outsider@example.com", "role": "viewer",
    }).status_code == 403


@pytest.mark.parametrize("body", [
    {"email": "missing-at-sign"},
    {"email": "member@example.com", "role": "admin"},
    {"email": "member@example.com", "role": "viewer", "permissions": ["*"]},
    {"email": "member@example.com", "role": "project_manager", "tenant_id": str(uuid4())},
])
def test_add_role_validation_rejects_overprivilege(members_env, body):
    v = members_env
    result = v["client"].post(v["url"], headers=v["headers"](v["owner"]), json=body)
    assert result.status_code == 422


def test_member_list_pagination_is_bounded(members_env):
    v = members_env
    client, url = v["client"], v["url"]
    owner_headers = v["headers"](v["owner"])
    for name in ("viewer", "reviewer"):
        assert client.post(url, headers=owner_headers, json={
            "email": f"{name}@example.com", "role": "viewer",
        }).status_code == 201

    first = client.get(url + "?limit=2&offset=0", headers=owner_headers).json()
    assert first["count"] == 2
    assert first["next_offset"] == 2
    second = client.get(url + "?limit=2&offset=2", headers=owner_headers).json()
    assert second["count"] == 1
    assert second["next_offset"] is None
    assert len({item["user_id"] for item in first["items"] + second["items"]}) == 3
    assert client.get(url + "?limit=101", headers=owner_headers).status_code == 422
    assert client.get(url + "?offset=-1", headers=owner_headers).status_code == 422


def test_atomic_rollback_when_audit_fails(members_env, monkeypatch):
    v = members_env
    from pmwizard.members import ProjectMemberService

    def broken_audit(self, **kwargs):
        raise RuntimeError("audit failure")

    monkeypatch.setattr(ProjectMemberService, "_audit", broken_audit)
    with v["factory"]() as session:
        with pytest.raises(RuntimeError, match="audit failure"):
            ProjectMemberService(session).add_member(
                tenant_id=v["tenant"],
                project_id=v["project_id"],
                actor_id=v["owner"].id,
                command=AddProjectMemberRequest(
                    email="viewer@example.com", role=ProjectRole.REVIEWER,
                ),
            )
    with v["factory"]() as session:
        assert session.scalar(
            select(func.count()).select_from(ProjectMembershipORM).where(
                ProjectMembershipORM.project_id == v["project_id"],
            )
        ) == 1
        assert session.scalar(
            select(func.count()).select_from(AuditLogORM).where(
                AuditLogORM.project_id == v["project_id"],
            )
        ) == 1


def test_inactive_user_not_eligible_for_addition(members_env):
    v = members_env
    with v["factory"].begin() as session:
        user = session.scalar(select(AppUserORM).where(
            AppUserORM.tenant_id == v["tenant"],
            AppUserORM.id == v["viewer"].id,
        ))
        user.is_active = False
    result = v["client"].post(
        v["url"],
        headers=v["headers"](v["owner"]),
        json={"email": "viewer@example.com", "role": "viewer"},
    )
    assert result.status_code == 404
