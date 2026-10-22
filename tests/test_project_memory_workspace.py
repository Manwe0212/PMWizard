"""Tests for governed Project Memory Workspace V0."""

from datetime import datetime, timezone
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from pmwizard.api import create_app
from pmwizard.models import AISuggestion, ActionItem, Evidence, Project
from pmwizard.models.enums import (
    ActionItemStatus,
    SuggestionType,
)
from pmwizard.persistence import Base, ProjectMemoryService
from pmwizard.persistence.orm import (
    AssumptionORM,
    DecisionORM,
    DependencyORM,
    IssueORM,
    RiskORM,
)


NOW = datetime(2026, 10, 22, 15, 0, tzinfo=timezone.utc)


@pytest.fixture()
def memory_env():
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
    app = create_app(factory, allow_trusted_headers=True)
    with TestClient(app) as client:
        yield client, factory


def _headers(
    tenant_id: UUID,
    user_id: UUID,
    *permissions: str,
) -> dict[str, str]:
    return {
        "X-PMWizard-Tenant-ID": str(tenant_id),
        "X-PMWizard-User-ID": str(user_id),
        "X-PMWizard-Permissions": ",".join(permissions),
    }


def _seed_snapshot(factory):
    tenant_id = uuid4()
    reviewer_id = uuid4()
    with factory() as session:
        memory = ProjectMemoryService(session)
        project = memory.create_project(
            tenant_id,
            Project(
                name="Memory Workspace Demo",
                status="active",
                priority="high",
                objective="Deliver a governed project intelligence workspace.",
            ),
        )

        open_action = memory.add_action_item(
            tenant_id,
            ActionItem(
                project_id=project.id,
                title="Verify API access",
                status=ActionItemStatus.IN_PROGRESS,
                priority="high",
                progress_summary="Technical validation underway.",
            ),
        )
        blocked_action = memory.add_action_item(
            tenant_id,
            ActionItem(
                project_id=project.id,
                title="Approve legal language",
                status=ActionItemStatus.BLOCKED,
                progress_summary="Waiting for counsel.",
            ),
        )
        completed_action = memory.add_action_item(
            tenant_id,
            ActionItem(
                project_id=project.id,
                title="Create initial project plan",
                status=ActionItemStatus.COMPLETED,
                progress_summary="Baseline plan approved.",
                completed_at=NOW,
            ),
        )

        common = {
            "tenant_id": tenant_id,
            "project_id": project.id,
            "created_at": NOW,
            "updated_at": NOW,
            "provenance": {},
        }
        session.add_all(
            [
                RiskORM(
                    id=uuid4(),
                    title="Vendor response delay",
                    description="Vendor may miss the planned response date.",
                    category="schedule",
                    probability=0.6,
                    impact="high",
                    exposure=0.6,
                    status="mitigating",
                    mitigation="Escalate weekly.",
                    **common,
                ),
                RiskORM(
                    id=uuid4(),
                    title="Closed migration risk",
                    status="closed",
                    **common,
                ),
                AssumptionORM(
                    id=uuid4(),
                    title="API remains available",
                    status="open",
                    **common,
                ),
                IssueORM(
                    id=uuid4(),
                    title="Legal approval pending",
                    severity="high",
                    status="blocked",
                    **common,
                ),
                DependencyORM(
                    id=uuid4(),
                    title="External vendor walkthrough",
                    provider="Vendor",
                    criticality="high",
                    status="open",
                    **common,
                ),
                DecisionORM(
                    id=uuid4(),
                    title="Use PMWizard as intelligence layer",
                    description="Keep source tools and centralize governed intelligence.",
                    status="approved",
                    decision_date=NOW,
                    rationale="Avoid replacing operational systems.",
                    alternatives_considered=["Replace Jira", "Replace SharePoint"],
                    **common,
                ),
                DecisionORM(
                    id=uuid4(),
                    title="Future graph database",
                    status="proposed",
                    **common,
                ),
            ]
        )
        session.commit()

    return (
        tenant_id,
        reviewer_id,
        project,
        open_action,
        blocked_action,
        completed_action,
    )


def test_memory_snapshot_returns_governed_project_state(memory_env) -> None:
    client, factory = memory_env
    (
        tenant_id,
        reviewer_id,
        project,
        open_action,
        blocked_action,
        _,
    ) = _seed_snapshot(factory)

    response = client.get(
        f"/v1/projects/{project.id}/memory",
        headers=_headers(tenant_id, reviewer_id, "project:read"),
    )

    assert response.status_code == 200
    payload = response.json()

    assert payload["project"]["name"] == "Memory Workspace Demo"
    assert payload["summary"] == {
        "action_items_total": 3,
        "action_items_open": 2,
        "action_items_blocked": 1,
        "risks_open": 1,
        "assumptions_open": 1,
        "issues_open": 1,
        "dependencies_open": 1,
        "decisions_total": 2,
        "decisions_approved": 1,
    }

    actions = {item["id"]: item for item in payload["action_items"]}
    assert actions[str(open_action.id)]["status"] == "in_progress"
    assert actions[str(blocked_action.id)]["status"] == "blocked"
    assert payload["risks"][0]["title"] in {
        "Vendor response delay",
        "Closed migration risk",
    }
    assert payload["assumptions"][0]["title"] == "API remains available"
    assert payload["issues"][0]["title"] == "Legal approval pending"
    assert payload["dependencies"][0]["title"] == "External vendor walkthrough"
    assert {
        item["status"] for item in payload["decisions"]
    } == {"approved", "proposed"}


def test_project_memory_requires_project_read(memory_env) -> None:
    client, factory = memory_env
    tenant_id, reviewer_id, project, *_ = _seed_snapshot(factory)

    response = client.get(
        f"/v1/projects/{project.id}/memory",
        headers=_headers(tenant_id, reviewer_id),
    )

    assert response.status_code == 403
    assert "project:read" in response.json()["detail"]


def test_project_memory_is_tenant_scoped(memory_env) -> None:
    client, factory = memory_env
    _, reviewer_id, project, *_ = _seed_snapshot(factory)

    response = client.get(
        f"/v1/projects/{project.id}/memory",
        headers=_headers(uuid4(), reviewer_id, "project:read"),
    )

    assert response.status_code == 404
    assert response.json()["detail"] == "Project not found for tenant"


def test_accepted_inbox_change_is_reflected_in_project_memory(memory_env) -> None:
    client, factory = memory_env
    tenant_id = uuid4()
    reviewer_id = uuid4()

    with factory() as session:
        memory = ProjectMemoryService(session)
        project = memory.create_project(
            tenant_id,
            Project(name="Governed Flow"),
        )
        action = memory.add_action_item(
            tenant_id,
            ActionItem(
                project_id=project.id,
                title="Verify API access",
                status=ActionItemStatus.IN_PROGRESS,
            ),
        )
        evidence = memory.add_evidence(
            tenant_id,
            Evidence(
                project_id=project.id,
                source_type="email",
                source_system="microsoft_graph_mail",
                captured_at=NOW,
                content_excerpt="Verify API access was completed.",
                permission_scope=["project:read", "source:mail"],
            ),
        )
        suggestion = memory.add_ai_suggestion(
            tenant_id,
            AISuggestion(
                project_id=project.id,
                suggestion_type=SuggestionType.ACTION_PROGRESS,
                target_entity_type="ActionItem",
                target_entity_id=action.id,
                proposed_changes={
                    "status": "completed",
                    "progress_summary": "API access verified.",
                },
                reason="Evidence states completion.",
                evidence_ids=[evidence.id],
                confidence=0.95,
            ),
        )

    headers = _headers(
        tenant_id,
        reviewer_id,
        "project:read",
        "project:review",
        "source:mail",
    )
    accepted = client.post(
        f"/v1/projects/{project.id}/inbox/{suggestion.id}/review",
        headers=headers,
        json={"status": "accepted"},
    )
    assert accepted.status_code == 200

    memory_response = client.get(
        f"/v1/projects/{project.id}/memory",
        headers=headers,
    )
    assert memory_response.status_code == 200

    payload = memory_response.json()
    assert payload["summary"]["action_items_open"] == 0
    assert payload["action_items"][0]["status"] == "completed"
    assert (
        payload["action_items"][0]["progress_summary"]
        == "API access verified."
    )


def test_memory_snapshot_empty_sections_are_explicit(memory_env) -> None:
    client, factory = memory_env
    tenant_id = uuid4()
    reviewer_id = uuid4()

    with factory() as session:
        project = ProjectMemoryService(session).create_project(
            tenant_id,
            Project(name="Empty Memory"),
        )

    response = client.get(
        f"/v1/projects/{project.id}/memory",
        headers=_headers(tenant_id, reviewer_id, "project:read"),
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["summary"]["action_items_total"] == 0
    assert payload["action_items"] == []
    assert payload["risks"] == []
    assert payload["assumptions"] == []
    assert payload["issues"] == []
    assert payload["dependencies"] == []
    assert payload["decisions"] == []
