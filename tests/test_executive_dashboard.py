"""Tests for Executive Dashboard V0."""

from datetime import date, datetime, timezone
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from pmwizard.api import create_app
from pmwizard.auth import AccessTokenService, AuthService, AuthSettings
from pmwizard.connectors import (
    ConnectorDescriptor,
    ConnectorPage,
    ConnectorTestResult,
)
from pmwizard.models import AISuggestion, ActionItem, Evidence, Project
from pmwizard.models.enums import (
    ActionItemStatus,
    DecisionStatus,
    DependencyStatus,
    IssueStatus,
    RiskStatus,
    SuggestionType,
)
from pmwizard.persistence import Base, ProjectMemoryService
from pmwizard.persistence.orm import (
    DecisionORM,
    DependencyORM,
    IssueORM,
    RiskORM,
)
from pmwizard.sources import create_durable_connector_runner


AUTH_SETTINGS = AuthSettings(
    secret_key="pmwizard-executive-dashboard-test-secret-32",
)
NOW = datetime(2026, 10, 29, 15, 0, tzinfo=timezone.utc)


class _FailureConnector:
    connector_key = "synthetic:executive-failure:v0"
    descriptor = ConnectorDescriptor(
        source_type="email",
        source_system="synthetic_failure",
        display_name="Broken Executive Mail",
        permission_scope=["project:read"],
        safe_config={},
    )

    def test_connection(self) -> ConnectorTestResult:
        return ConnectorTestResult(ok=False, message="unavailable")

    def fetch_page(self, *, project_id, cursor, limit) -> ConnectorPage:
        raise ConnectionError("source unavailable")


@pytest.fixture()
def executive_env():
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
        allow_trusted_headers=True,
    )
    with TestClient(app) as client:
        yield client, factory


def _login(client, tenant_id, email, password):
    response = client.post(
        "/v1/auth/login",
        json={
            "tenant_id": str(tenant_id),
            "email": email,
            "password": password,
        },
    )
    assert response.status_code == 200
    return response.json()["access_token"]


def _seed(factory):
    tenant_id = uuid4()

    with factory() as session:
        memory = ProjectMemoryService(session)
        alpha = memory.create_project(
            tenant_id,
            Project(
                name="Alpha",
                priority="high",
                planned_end_date=date(2026, 12, 1),
                forecast_end_date=date(2026, 12, 1),
            ),
        )
        beta = memory.create_project(
            tenant_id,
            Project(
                name="Beta",
                priority="critical",
                planned_end_date=date(2026, 11, 1),
                forecast_end_date=date(2026, 12, 20),
            ),
        )
        hidden = memory.create_project(
            tenant_id,
            Project(name="Hidden Executive Project"),
        )

        memory.add_action_item(
            tenant_id,
            ActionItem(
                project_id=beta.id,
                title="Resolve blocker",
                status=ActionItemStatus.BLOCKED,
                due_date=date(2026, 10, 1),
            ),
        )

        visible_evidence = memory.add_evidence(
            tenant_id,
            Evidence(
                project_id=alpha.id,
                source_type="email",
                source_system="synthetic",
                captured_at=NOW,
                content_excerpt="Approval still pending.",
                permission_scope=["project:read"],
            ),
        )
        memory.add_ai_suggestion(
            tenant_id,
            AISuggestion(
                project_id=alpha.id,
                suggestion_type=SuggestionType.ACTION_PROGRESS,
                reason="Approval remains pending.",
                evidence_ids=[visible_evidence.id],
                confidence=0.91,
            ),
        )

        restricted_evidence = memory.add_evidence(
            tenant_id,
            Evidence(
                project_id=alpha.id,
                source_type="document",
                source_system="synthetic",
                captured_at=NOW,
                content_excerpt="Restricted executive note.",
                permission_scope=["project:read", "source:secret"],
            ),
        )
        memory.add_ai_suggestion(
            tenant_id,
            AISuggestion(
                project_id=alpha.id,
                suggestion_type=SuggestionType.NEW_RISK,
                reason="Restricted suggestion.",
                evidence_ids=[restricted_evidence.id],
                confidence=0.99,
            ),
        )

        hidden_evidence = memory.add_evidence(
            tenant_id,
            Evidence(
                project_id=hidden.id,
                source_type="email",
                source_system="synthetic",
                captured_at=NOW,
                content_excerpt="Hidden project evidence.",
                permission_scope=["project:read"],
            ),
        )
        memory.add_ai_suggestion(
            tenant_id,
            AISuggestion(
                project_id=hidden.id,
                suggestion_type=SuggestionType.NEW_ISSUE,
                reason="Hidden suggestion.",
                evidence_ids=[hidden_evidence.id],
                confidence=0.95,
            ),
        )

        common = {
            "tenant_id": tenant_id,
            "created_at": NOW,
            "updated_at": NOW,
            "provenance": {},
        }
        session.add_all(
            [
                RiskORM(
                    id=uuid4(),
                    project_id=alpha.id,
                    title="Vendor outage",
                    impact="high",
                    status=RiskStatus.OPEN.value,
                    due_date=date(2026, 11, 5),
                    **common,
                ),
                IssueORM(
                    id=uuid4(),
                    project_id=beta.id,
                    title="Production blocker",
                    severity="medium",
                    status=IssueStatus.BLOCKED.value,
                    due_date=date(2026, 10, 30),
                    **common,
                ),
                DependencyORM(
                    id=uuid4(),
                    project_id=hidden.id,
                    title="Hidden dependency",
                    criticality="critical",
                    status=DependencyStatus.BLOCKED.value,
                    **common,
                ),
                DecisionORM(
                    id=uuid4(),
                    project_id=alpha.id,
                    title="Select launch vendor",
                    status=DecisionStatus.PENDING.value,
                    review_date=date(2026, 10, 31),
                    expected_impact="Launch timing",
                    alternatives_considered=[],
                    **common,
                ),
                DecisionORM(
                    id=uuid4(),
                    project_id=hidden.id,
                    title="Hidden decision",
                    status=DecisionStatus.PENDING.value,
                    alternatives_considered=[],
                    **common,
                ),
            ]
        )
        session.commit()

        create_durable_connector_runner(session).run(
            tenant_id=tenant_id,
            project_id=beta.id,
            connector=_FailureConnector(),
        )

        auth = AuthService(session, AccessTokenService(AUTH_SETTINGS))
        user = auth.create_user(
            tenant_id=tenant_id,
            email="executive@example.com",
            display_name="Executive User",
            password="A secure executive password!",
        )
        for project in (alpha, beta):
            auth.grant_project_access(
                tenant_id=tenant_id,
                user_id=user.id,
                project_id=project.id,
                role="director",
                permissions=["project:read", "project:review"],
            )

        no_read = auth.create_user(
            tenant_id=tenant_id,
            email="noread-exec@example.com",
            display_name="No Read Executive",
            password="Another secure executive password!",
        )
        auth.grant_project_access(
            tenant_id=tenant_id,
            user_id=no_read.id,
            project_id=alpha.id,
            role="observer",
            permissions=["project:review"],
        )

    return {
        "tenant_id": tenant_id,
        "alpha": alpha,
        "beta": beta,
        "hidden": hidden,
        "user": user,
        "no_read": no_read,
    }


def test_executive_dashboard_aggregates_authorized_operational_attention(
    executive_env,
) -> None:
    client, factory = executive_env
    seeded = _seed(factory)
    token = _login(
        client,
        seeded["tenant_id"],
        "executive@example.com",
        "A secure executive password!",
    )

    response = client.get(
        "/v1/executive/dashboard",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200
    payload = response.json()
    summary = payload["summary"]

    assert summary["health"]["projects_total"] == 2
    assert summary["pending_inbox"] == 1
    assert summary["deferred_inbox"] == 0
    assert summary["critical_raid"] == 2
    assert summary["pending_decisions"] == 1
    assert summary["source_failures"] == 1

    assert [item["project_name"] for item in payload["inbox_items"]] == ["Alpha"]
    assert {item["project_name"] for item in payload["critical_raid"]} == {
        "Alpha",
        "Beta",
    }
    assert payload["pending_decisions"][0]["title"] == "Select launch vendor"
    assert payload["source_alerts"][0]["project_name"] == "Beta"
    assert payload["source_alerts"][0]["health"] == "failed"


def test_dashboard_does_not_leak_hidden_project_or_restricted_evidence(
    executive_env,
) -> None:
    client, factory = executive_env
    seeded = _seed(factory)
    token = _login(
        client,
        seeded["tenant_id"],
        "executive@example.com",
        "A secure executive password!",
    )

    response = client.get(
        "/v1/executive/dashboard",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200
    text = response.text
    assert "Hidden Executive Project" not in text
    assert "Hidden dependency" not in text
    assert "Hidden decision" not in text
    assert "Hidden suggestion" not in text
    assert "Restricted suggestion" not in text
    assert response.json()["summary"]["pending_inbox"] == 1


def test_dashboard_excludes_membership_without_project_read(executive_env) -> None:
    client, factory = executive_env
    seeded = _seed(factory)
    token = _login(
        client,
        seeded["tenant_id"],
        "noread-exec@example.com",
        "Another secure executive password!",
    )

    response = client.get(
        "/v1/executive/dashboard",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["summary"]["health"]["projects_total"] == 0
    assert payload["summary"]["pending_inbox"] == 0
    assert payload["summary"]["critical_raid"] == 0
    assert payload["attention_projects"] == []
    assert payload["source_alerts"] == []


def test_dashboard_rejects_trusted_header_cross_project_enumeration(
    executive_env,
) -> None:
    client, factory = executive_env
    seeded = _seed(factory)

    response = client.get(
        "/v1/executive/dashboard",
        headers={
            "X-PMWizard-Tenant-ID": str(seeded["tenant_id"]),
            "X-PMWizard-User-ID": str(uuid4()),
            "X-PMWizard-Permissions": "project:read",
        },
    )

    assert response.status_code == 400
    assert "Bearer authentication" in response.json()["detail"]
