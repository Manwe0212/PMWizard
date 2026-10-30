"""Synthetic local demo bootstrap: safe, repeatable and API-usable."""

from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from pmwizard.api import create_app
from pmwizard.auth import AccessTokenService, AuthService, AuthSettings
from pmwizard.demo import (
    DEMO_EMAIL,
    DEMO_PROJECT_ID,
    DEMO_TENANT_ID,
    DEMO_USER_ID,
    assert_local_demo_allowed,
    seed_local_demo,
)
from pmwizard.persistence import Base
from pmwizard.persistence.orm import (
    AISuggestionORM,
    ActionItemORM,
    AppUserORM,
    DecisionORM,
    EventORM,
    EvidenceORM,
    IssueORM,
    ProjectMembershipORM,
    ProjectORM,
    RiskORM,
)

PASSWORD = "Synthetic-Demo-Password-For-Tests-2026"
NOW = datetime(2026, 10, 30, 19, 0, tzinfo=timezone.utc)
SETTINGS = AuthSettings(secret_key="local-demo-unit-test-auth-secret-key-1234567890")


@pytest.fixture()
def local_demo_env(monkeypatch):
    monkeypatch.setenv("PMWIZARD_ENV", "development")
    monkeypatch.setenv("PMWIZARD_ENABLE_LOCAL_DEMO", "true")
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    factory = sessionmaker(
        bind=engine, class_=Session, expire_on_commit=False,
    )
    yield factory
    engine.dispose()


def _seed(factory):
    with factory.begin() as session:
        return seed_local_demo(session, password=PASSWORD, now=NOW)


def test_demo_seed_creates_project_user_and_governed_usable_data(local_demo_env):
    factory = local_demo_env
    result = _seed(factory)
    assert result.created == 13
    assert result.existing == 0
    assert result.tenant_id == DEMO_TENANT_ID
    assert result.project_id == DEMO_PROJECT_ID
    assert result.user_id == DEMO_USER_ID
    assert result.email == DEMO_EMAIL

    with factory() as session:
        user = session.get(AppUserORM, DEMO_USER_ID)
        assert user is not None
        assert user.password_hash != PASSWORD
        assert user.password_hash.startswith("$argon2id$")
        membership = session.scalar(
            select(ProjectMembershipORM).where(
                ProjectMembershipORM.tenant_id == DEMO_TENANT_ID,
                ProjectMembershipORM.user_id == DEMO_USER_ID,
                ProjectMembershipORM.project_id == DEMO_PROJECT_ID,
            )
        )
        assert membership is not None
        assert sorted(membership.permissions) == ["project:read", "project:review"]
        assert session.scalar(
            select(func.count()).select_from(ActionItemORM)
        ) == 3
        assert session.scalar(select(func.count()).select_from(RiskORM)) == 1
        assert session.scalar(select(func.count()).select_from(IssueORM)) == 1
        assert session.scalar(select(func.count()).select_from(DecisionORM)) == 1
        assert session.scalar(select(func.count()).select_from(EventORM)) == 1
        evidence = session.scalar(select(EvidenceORM))
        assert evidence is not None
        assert evidence.permission_scope == ["project:read"]
        suggestion = session.scalar(select(AISuggestionORM))
        assert suggestion is not None
        assert suggestion.review_status == "pending"
        assert suggestion.evidence_ids == [str(evidence.id)]

    with factory() as session:
        token = AuthService(
            session, AccessTokenService(SETTINGS),
        ).login(
            tenant_id=DEMO_TENANT_ID,
            email=DEMO_EMAIL,
            password=PASSWORD,
        ).access_token

    with TestClient(create_app(factory, auth_settings=SETTINGS)) as client:
        headers = {"Authorization": f"Bearer {token}"}
        projects = client.get("/v1/projects", headers=headers)
        assert projects.status_code == 200
        assert projects.json()["count"] == 1
        assert projects.json()["items"][0]["project_id"] == str(DEMO_PROJECT_ID)
        inbox = client.get(f"/v1/projects/{DEMO_PROJECT_ID}/inbox", headers=headers)
        assert inbox.status_code == 200
        assert inbox.json()["count"] == 1
        activity = client.get(
            f"/v1/projects/{DEMO_PROJECT_ID}/activity", headers=headers
        )
        assert activity.status_code == 200
        assert activity.json()["count"] >= 1
        health = client.get(
            f"/v1/projects/{DEMO_PROJECT_ID}/health", headers=headers
        )
        assert health.status_code == 200
        memory = client.get(
            f"/v1/projects/{DEMO_PROJECT_ID}/memory", headers=headers
        )
        assert memory.status_code == 200


def test_demo_seed_is_idempotent_and_preserves_reviewed_data(local_demo_env):
    factory = local_demo_env
    first = _seed(factory)
    with factory.begin() as session:
        row = session.scalar(
            select(ActionItemORM).where(
                ActionItemORM.tenant_id == DEMO_TENANT_ID,
                ActionItemORM.title == "Unblock vendor integration review",
            )
        )
        row.status = "completed"
    second = _seed(factory)
    assert first.created == 13
    assert second.created == 0
    assert second.existing == 13
    with factory() as session:
        assert session.scalar(
            select(func.count()).select_from(ProjectORM)
        ) == 1
        assert session.scalar(
            select(func.count()).select_from(AppUserORM)
        ) == 1
        assert session.scalar(
            select(func.count()).select_from(AISuggestionORM)
        ) == 1
        assert session.scalar(
            select(ActionItemORM.status).where(
                ActionItemORM.title == "Unblock vendor integration review",
            )
        ) == "completed"


def test_demo_fails_closed_without_explicit_dev_mode_or_local_database(monkeypatch):
    url = "postgresql+psycopg://pmwizard:local@localhost:5432/pmwizard"
    with pytest.raises(RuntimeError, match="PMWIZARD_ENV"):
        assert_local_demo_allowed(url, {
            "PMWIZARD_ENV": "production", "PMWIZARD_ENABLE_LOCAL_DEMO": "true",
        })
    with pytest.raises(RuntimeError, match="PMWIZARD_ENABLE_LOCAL_DEMO"):
        assert_local_demo_allowed(url, {
            "PMWIZARD_ENV": "development",
            "PMWIZARD_ENABLE_LOCAL_DEMO": "false",
        })
    for remote in (
        "postgresql+psycopg://user:password@db.example.com:5432/pmwizard",
        "postgresql+psycopg://user:password@10.1.2.3:5432/pmwizard",
        "mysql://user:password@localhost:3306/db",
    ):
        with pytest.raises(RuntimeError, match="refuses|supports"):
            assert_local_demo_allowed(remote, {
                "PMWIZARD_ENV": "development", "PMWIZARD_ENABLE_LOCAL_DEMO": "true",
            })


def test_demo_requires_password_and_never_rotates_existing_user(local_demo_env):
    factory = local_demo_env
    with factory.begin() as session:
        with pytest.raises(ValueError, match="12 characters"):
            seed_local_demo(session, password="short", now=NOW)
    first = _seed(factory)
    with pytest.raises(RuntimeError, match="password differs"):
        with factory.begin() as session:
            seed_local_demo(
                session, password="Different-Long-Password-For-Tests", now=NOW,
            )
    again = _seed(factory)
    assert again.created == 0
    assert again.existing == first.created


def test_demo_does_not_touch_other_projects_or_tenants(local_demo_env):
    factory = local_demo_env
    other_tenant = uuid4()
    other_project = uuid4()
    with factory.begin() as session:
        session.add(ProjectORM(
            id=other_project,
            tenant_id=other_tenant,
            name="Real unrelated project",
            provenance={},
        ))
    _seed(factory)
    _seed(factory)
    with factory() as session:
        assert session.scalar(
            select(func.count()).select_from(ProjectORM)
        ) == 2
        unrelated = session.get(ProjectORM, other_project)
        assert unrelated.name == "Real unrelated project"
        assert unrelated.tenant_id == other_tenant


def test_demo_identity_collision_aborts_without_partial_rows(local_demo_env):
    factory = local_demo_env
    with factory.begin() as session:
        session.add(ProjectORM(
            id=DEMO_PROJECT_ID,
            tenant_id=DEMO_TENANT_ID,
            name="Existing project with same ID",
            source_system="real_system",
            external_id="real-project",
            provenance={},
        ))
    with pytest.raises(RuntimeError, match="identity collision"):
        _seed(factory)
    with factory() as session:
        assert session.scalar(select(func.count()).select_from(AppUserORM)) == 0
        project = session.get(ProjectORM, DEMO_PROJECT_ID)
        assert project.name == "Existing project with same ID"
