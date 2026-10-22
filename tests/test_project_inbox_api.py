"""Tests for Project Inbox V0 + FastAPI."""

from datetime import datetime, timezone
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from pmwizard.api import create_app
from pmwizard.inbox import ProjectInboxService, ReviewCommand
from pmwizard.models import AISuggestion, ActionItem, Evidence, Project
from pmwizard.models.enums import (
    ActionItemStatus,
    ReviewStatus,
    SuggestionType,
)
from pmwizard.persistence import Base, ProjectMemoryService


NOW = datetime(2026, 10, 22, 12, 0, tzinfo=timezone.utc)


@pytest.fixture()
def api_env():
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
    app = create_app(factory)
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


def _seed(
    factory,
    *,
    evidence_scopes=None,
    suggested_status="completed",
):
    tenant_id = uuid4()
    reviewer_id = uuid4()
    with factory() as session:
        memory = ProjectMemoryService(session)
        project = memory.create_project(
            tenant_id,
            Project(name="Inbox API Demo"),
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
                source_reference="https://example.test/message/1",
                captured_at=NOW,
                content_excerpt="Verify API access was completed today.",
                permission_scope=evidence_scopes
                or ["project:read", "source:mail"],
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
                    "status": suggested_status,
                    "progress_summary": "API access verified.",
                },
                reason="Evidence states the action is complete.",
                evidence_ids=[evidence.id],
                confidence=0.94,
            ),
        )
    return tenant_id, reviewer_id, project, action, evidence, suggestion


def test_healthz_requires_no_identity(api_env) -> None:
    client, _ = api_env

    response = client.get("/healthz")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_list_inbox_returns_authorized_pending_suggestions(api_env) -> None:
    client, factory = api_env
    tenant_id, reviewer_id, project, _, _, suggestion = _seed(factory)

    response = client.get(
        f"/v1/projects/{project.id}/inbox",
        headers=_headers(
            tenant_id,
            reviewer_id,
            "project:read",
            "source:mail",
        ),
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["count"] == 1
    assert payload["items"][0]["id"] == str(suggestion.id)
    assert payload["items"][0]["review_status"] == "pending"
    assert payload["items"][0]["evidence_count"] == 1
    assert payload["items"][0]["evidence_sources"] == [
        "microsoft_graph_mail"
    ]


def test_inbox_hides_suggestion_when_evidence_scope_is_missing(api_env) -> None:
    client, factory = api_env
    tenant_id, reviewer_id, project, _, _, _ = _seed(factory)

    response = client.get(
        f"/v1/projects/{project.id}/inbox",
        headers=_headers(
            tenant_id,
            reviewer_id,
            "project:read",
        ),
    )

    assert response.status_code == 200
    assert response.json()["count"] == 0


def test_detail_returns_evidence_and_current_target_state(api_env) -> None:
    client, factory = api_env
    tenant_id, reviewer_id, project, action, evidence, suggestion = _seed(
        factory
    )

    response = client.get(
        f"/v1/projects/{project.id}/inbox/{suggestion.id}",
        headers=_headers(
            tenant_id,
            reviewer_id,
            "project:read",
            "source:mail",
        ),
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["suggestion"]["id"] == str(suggestion.id)
    assert payload["target_action_item"]["id"] == str(action.id)
    assert payload["target_action_item"]["status"] == "in_progress"
    assert payload["evidence"][0]["id"] == str(evidence.id)
    assert (
        payload["evidence"][0]["content_excerpt"]
        == "Verify API access was completed today."
    )


def test_accept_review_updates_action_and_removes_item_from_default_inbox(
    api_env,
) -> None:
    client, factory = api_env
    tenant_id, reviewer_id, project, action, _, suggestion = _seed(factory)
    headers = _headers(
        tenant_id,
        reviewer_id,
        "project:read",
        "project:review",
        "source:mail",
    )

    response = client.post(
        f"/v1/projects/{project.id}/inbox/{suggestion.id}/review",
        headers=headers,
        json={"status": "accepted"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["review_status"] == "accepted"
    assert payload["updated_action_item"]["status"] == "completed"

    with factory() as session:
        governed = ProjectMemoryService(session).repository.get_action_item(
            tenant_id,
            action.id,
        )
        assert governed is not None
        assert governed.status == ActionItemStatus.COMPLETED

    inbox = client.get(
        f"/v1/projects/{project.id}/inbox",
        headers=headers,
    )
    assert inbox.status_code == 200
    assert inbox.json()["count"] == 0


def test_edit_review_applies_only_supported_action_fields(api_env) -> None:
    client, factory = api_env
    tenant_id, reviewer_id, project, _, _, suggestion = _seed(factory)
    headers = _headers(
        tenant_id,
        reviewer_id,
        "project:read",
        "project:review",
        "source:mail",
    )

    response = client.post(
        f"/v1/projects/{project.id}/inbox/{suggestion.id}/review",
        headers=headers,
        json={
            "status": "edited",
            "reviewer_note": "Still blocked on legal.",
            "final_changes": {
                "status": "blocked",
                "progress_summary": "API reviewed; legal approval remains.",
            },
        },
    )

    assert response.status_code == 200
    assert response.json()["updated_action_item"]["status"] == "blocked"

    bad_tenant, bad_user, bad_project, _, _, bad_suggestion = _seed(factory)
    bad = client.post(
        f"/v1/projects/{bad_project.id}/inbox/{bad_suggestion.id}/review",
        headers=_headers(
            bad_tenant,
            bad_user,
            "project:read",
            "project:review",
            "source:mail",
        ),
        json={
            "status": "edited",
            "final_changes": {"title": "Unauthorized title edit"},
        },
    )
    assert bad.status_code == 409
    assert "Unsupported ActionItem review fields" in bad.json()["detail"]


def test_reject_and_defer_do_not_mutate_governed_action(api_env) -> None:
    client, factory = api_env

    tenant_a, reviewer_a, project_a, action_a, _, suggestion_a = _seed(factory)
    headers_a = _headers(
        tenant_a,
        reviewer_a,
        "project:read",
        "project:review",
        "source:mail",
    )
    rejected = client.post(
        f"/v1/projects/{project_a.id}/inbox/{suggestion_a.id}/review",
        headers=headers_a,
        json={
            "status": "rejected",
            "reviewer_note": "Evidence is not sufficient.",
        },
    )
    assert rejected.status_code == 200
    assert rejected.json()["updated_action_item"] is None

    tenant_b, reviewer_b, project_b, action_b, _, suggestion_b = _seed(factory)
    headers_b = _headers(
        tenant_b,
        reviewer_b,
        "project:read",
        "project:review",
        "source:mail",
    )
    deferred = client.post(
        f"/v1/projects/{project_b.id}/inbox/{suggestion_b.id}/review",
        headers=headers_b,
        json={
            "status": "deferred",
            "reviewer_note": "Review tomorrow.",
        },
    )
    assert deferred.status_code == 200
    assert deferred.json()["review_status"] == "deferred"
    assert deferred.json()["updated_action_item"] is None

    with factory() as session:
        repository = ProjectMemoryService(session).repository
        assert (
            repository.get_action_item(tenant_a, action_a.id).status
            == ActionItemStatus.IN_PROGRESS
        )
        assert (
            repository.get_action_item(tenant_b, action_b.id).status
            == ActionItemStatus.IN_PROGRESS
        )

    inbox = client.get(
        f"/v1/projects/{project_b.id}/inbox",
        headers=headers_b,
    )
    assert inbox.json()["count"] == 1
    assert inbox.json()["items"][0]["review_status"] == "deferred"


def test_deferred_suggestion_can_later_be_accepted(api_env) -> None:
    client, factory = api_env
    tenant_id, reviewer_id, project, _, _, suggestion = _seed(factory)
    headers = _headers(
        tenant_id,
        reviewer_id,
        "project:read",
        "project:review",
        "source:mail",
    )

    first = client.post(
        f"/v1/projects/{project.id}/inbox/{suggestion.id}/review",
        headers=headers,
        json={"status": "deferred"},
    )
    second = client.post(
        f"/v1/projects/{project.id}/inbox/{suggestion.id}/review",
        headers=headers,
        json={"status": "accepted"},
    )

    assert first.status_code == 200
    assert second.status_code == 200
    assert second.json()["review_status"] == "accepted"


def test_terminal_suggestion_cannot_be_reviewed_twice(api_env) -> None:
    client, factory = api_env
    tenant_id, reviewer_id, project, _, _, suggestion = _seed(factory)
    headers = _headers(
        tenant_id,
        reviewer_id,
        "project:read",
        "project:review",
        "source:mail",
    )

    first = client.post(
        f"/v1/projects/{project.id}/inbox/{suggestion.id}/review",
        headers=headers,
        json={"status": "accepted"},
    )
    second = client.post(
        f"/v1/projects/{project.id}/inbox/{suggestion.id}/review",
        headers=headers,
        json={"status": "rejected"},
    )

    assert first.status_code == 200
    assert second.status_code == 409
    assert "already terminal" in second.json()["detail"]


def test_pending_is_not_a_valid_human_review_transition(api_env) -> None:
    client, factory = api_env
    tenant_id, reviewer_id, project, _, _, suggestion = _seed(factory)

    response = client.post(
        f"/v1/projects/{project.id}/inbox/{suggestion.id}/review",
        headers=_headers(
            tenant_id,
            reviewer_id,
            "project:read",
            "project:review",
            "source:mail",
        ),
        json={"status": "pending"},
    )

    assert response.status_code == 409
    assert "cannot set status back to pending" in response.json()["detail"]


def test_review_requires_project_review_permission(api_env) -> None:
    client, factory = api_env
    tenant_id, reviewer_id, project, _, _, suggestion = _seed(factory)

    response = client.post(
        f"/v1/projects/{project.id}/inbox/{suggestion.id}/review",
        headers=_headers(
            tenant_id,
            reviewer_id,
            "project:read",
            "source:mail",
        ),
        json={"status": "accepted"},
    )

    assert response.status_code == 403
    assert "project:review" in response.json()["detail"]


def test_read_requires_project_read_permission(api_env) -> None:
    client, factory = api_env
    tenant_id, reviewer_id, project, _, _, _ = _seed(factory)

    response = client.get(
        f"/v1/projects/{project.id}/inbox",
        headers=_headers(
            tenant_id,
            reviewer_id,
            "source:mail",
        ),
    )

    assert response.status_code == 403
    assert "project:read" in response.json()["detail"]


def test_cross_tenant_inbox_access_is_not_found(api_env) -> None:
    client, factory = api_env
    tenant_id, reviewer_id, project, _, _, suggestion = _seed(factory)
    other_tenant = uuid4()

    list_response = client.get(
        f"/v1/projects/{project.id}/inbox",
        headers=_headers(
            other_tenant,
            reviewer_id,
            "project:read",
            "source:mail",
        ),
    )
    detail_response = client.get(
        f"/v1/projects/{project.id}/inbox/{suggestion.id}",
        headers=_headers(
            other_tenant,
            reviewer_id,
            "project:read",
            "source:mail",
        ),
    )

    assert list_response.status_code == 404
    assert detail_response.status_code == 404


def test_status_filter_can_query_terminal_items(api_env) -> None:
    client, factory = api_env
    tenant_id, reviewer_id, project, _, _, suggestion = _seed(factory)
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

    response = client.get(
        f"/v1/projects/{project.id}/inbox",
        params=[("review_status", "accepted")],
        headers=headers,
    )

    assert response.status_code == 200
    assert response.json()["count"] == 1
    assert response.json()["items"][0]["review_status"] == "accepted"


def test_service_hides_multi_evidence_suggestion_if_any_evidence_is_unauthorized(
    api_env,
) -> None:
    _, factory = api_env
    tenant_id = uuid4()
    with factory() as session:
        memory = ProjectMemoryService(session)
        project = memory.create_project(tenant_id, Project(name="Scope Union"))
        visible = memory.add_evidence(
            tenant_id,
            Evidence(
                project_id=project.id,
                source_type="email",
                captured_at=NOW,
                content_excerpt="Visible",
                permission_scope=["project:read", "source:mail"],
            ),
        )
        restricted = memory.add_evidence(
            tenant_id,
            Evidence(
                project_id=project.id,
                source_type="document",
                captured_at=NOW,
                content_excerpt="Restricted",
                permission_scope=["project:read", "source:secret"],
            ),
        )
        memory.add_ai_suggestion(
            tenant_id,
            AISuggestion(
                project_id=project.id,
                suggestion_type=SuggestionType.CONTRADICTION,
                proposed_changes={},
                reason="Sources conflict.",
                evidence_ids=[visible.id, restricted.id],
                confidence=0.7,
            ),
        )

        inbox = ProjectInboxService(session).list_items(
            tenant_id=tenant_id,
            project_id=project.id,
            permissions={"project:read", "source:mail"},
        )

        assert inbox.count == 0


def test_edited_review_requires_changes(api_env) -> None:
    client, factory = api_env
    tenant_id, reviewer_id, project, _, _, suggestion = _seed(factory)

    response = client.post(
        f"/v1/projects/{project.id}/inbox/{suggestion.id}/review",
        headers=_headers(
            tenant_id,
            reviewer_id,
            "project:read",
            "project:review",
            "source:mail",
        ),
        json={"status": "edited", "final_changes": {}},
    )

    assert response.status_code == 409
    assert "require final_changes" in response.json()["detail"]
