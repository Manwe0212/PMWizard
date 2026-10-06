"""End-to-end tests for Project Memory V0."""

from datetime import datetime, timezone
from uuid import uuid4

import pytest
from sqlalchemy import select

from pmwizard.models import AISuggestion, ActionItem, Evidence, HumanReview, Project
from pmwizard.models.enums import ActionItemStatus, ReviewStatus, SuggestionType
from pmwizard.persistence import Base, ProjectMemoryService, create_engine_from_url, create_session_factory
from pmwizard.persistence.orm import AuditLogORM


@pytest.fixture()
def session():
    engine = create_engine_from_url("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    factory = create_session_factory(engine)
    with factory() as session:
        yield session


def test_human_acceptance_applies_ai_suggestion(session) -> None:
    tenant_id = uuid4()
    reviewer_id = uuid4()
    service = ProjectMemoryService(session)

    project = service.create_project(
        tenant_id,
        Project(name="Synthetic Project Memory Demo"),
    )

    action = service.add_action_item(
        tenant_id,
        ActionItem(
            project_id=project.id,
            title="Verify API access",
            status=ActionItemStatus.IN_PROGRESS,
        ),
    )

    evidence = service.add_evidence(
        tenant_id,
        Evidence(
            project_id=project.id,
            source_type="email",
            source_system="synthetic",
            captured_at=datetime.now(timezone.utc),
            content_excerpt="API access has been verified and is working.",
            permission_scope=["project:read"],
        ),
    )

    suggestion = service.add_ai_suggestion(
        tenant_id,
        AISuggestion(
            project_id=project.id,
            suggestion_type=SuggestionType.ACTION_PROGRESS,
            target_entity_type="ActionItem",
            target_entity_id=action.id,
            proposed_changes={
                "status": "completed",
                "progress_summary": "Access verified successfully.",
            },
            reason="New evidence explicitly says the API access is working.",
            evidence_ids=[evidence.id],
            confidence=0.96,
        ),
    )

    # The AI suggestion alone must not mutate governed state.
    before_review = service.repository.get_action_item(tenant_id, action.id)
    assert before_review is not None
    assert before_review.status == ActionItemStatus.IN_PROGRESS

    updated = service.review_suggestion(
        tenant_id,
        HumanReview(
            project_id=project.id,
            suggestion_id=suggestion.id,
            reviewer_id=reviewer_id,
            status=ReviewStatus.ACCEPTED,
            reviewed_at=datetime.now(timezone.utc),
        ),
    )

    assert updated is not None
    assert updated.status == ActionItemStatus.COMPLETED
    assert updated.progress_summary == "Access verified successfully."

    governed = service.repository.get_action_item(tenant_id, action.id)
    assert governed is not None
    assert governed.status == ActionItemStatus.COMPLETED

    stored_suggestion = service.repository.get_ai_suggestion(tenant_id, suggestion.id)
    assert stored_suggestion is not None
    assert stored_suggestion.review_status == ReviewStatus.ACCEPTED

    audit_rows = session.scalars(select(AuditLogORM)).all()
    assert len(audit_rows) == 1
    assert audit_rows[0].action == "suggestion_accepted"


def test_rejected_suggestion_does_not_change_action_item(session) -> None:
    tenant_id = uuid4()
    service = ProjectMemoryService(session)
    project = service.create_project(tenant_id, Project(name="Rejection Test"))

    action = service.add_action_item(
        tenant_id,
        ActionItem(
            project_id=project.id,
            title="Review contract",
            status=ActionItemStatus.IN_PROGRESS,
        ),
    )

    suggestion = service.add_ai_suggestion(
        tenant_id,
        AISuggestion(
            project_id=project.id,
            suggestion_type=SuggestionType.ACTION_PROGRESS,
            target_entity_type="ActionItem",
            target_entity_id=action.id,
            proposed_changes={"status": "completed"},
            reason="A meeting note may imply completion.",
            confidence=0.71,
        ),
    )

    updated = service.review_suggestion(
        tenant_id,
        HumanReview(
            project_id=project.id,
            suggestion_id=suggestion.id,
            reviewer_id=uuid4(),
            status=ReviewStatus.REJECTED,
            reviewed_at=datetime.now(timezone.utc),
            reviewer_note="The work is only partially complete.",
        ),
    )

    assert updated is None
    governed = service.repository.get_action_item(tenant_id, action.id)
    assert governed is not None
    assert governed.status == ActionItemStatus.IN_PROGRESS


def test_edited_review_overrides_ai_proposal(session) -> None:
    tenant_id = uuid4()
    service = ProjectMemoryService(session)
    project = service.create_project(tenant_id, Project(name="Edited Review Test"))

    action = service.add_action_item(
        tenant_id,
        ActionItem(
            project_id=project.id,
            title="Legal approval",
            status=ActionItemStatus.IN_PROGRESS,
        ),
    )

    suggestion = service.add_ai_suggestion(
        tenant_id,
        AISuggestion(
            project_id=project.id,
            suggestion_type=SuggestionType.ACTION_PROGRESS,
            target_entity_type="ActionItem",
            target_entity_id=action.id,
            proposed_changes={"status": "completed"},
            reason="An email indicates legal reviewed the document.",
            confidence=0.89,
        ),
    )

    updated = service.review_suggestion(
        tenant_id,
        HumanReview(
            project_id=project.id,
            suggestion_id=suggestion.id,
            reviewer_id=uuid4(),
            status=ReviewStatus.EDITED,
            reviewed_at=datetime.now(timezone.utc),
            final_changes={
                "status": "blocked",
                "progress_summary": "Review completed; two clauses remain unresolved.",
            },
        ),
    )

    assert updated is not None
    assert updated.status == ActionItemStatus.BLOCKED
    assert updated.progress_summary == "Review completed; two clauses remain unresolved."


def test_tenant_isolation_blocks_cross_tenant_access(session) -> None:
    tenant_a = uuid4()
    tenant_b = uuid4()
    service = ProjectMemoryService(session)

    project = service.create_project(tenant_a, Project(name="Tenant A Project"))

    assert service.repository.get_project(tenant_b, project.id) is None

    with pytest.raises(LookupError):
        service.get_open_action_items(tenant_b, project.id)
