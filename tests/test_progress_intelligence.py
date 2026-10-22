"""Tests for deterministic Progress Intelligence V0."""

from datetime import datetime, timezone
from uuid import uuid4

import pytest
from sqlalchemy import func, select

from pmwizard.intelligence import (
    ActionItemProgressClassifier,
    ProgressIntelligenceService,
    ProgressOutcome,
    ProgressPipelineOutcome,
)
from pmwizard.models import ActionItem, Evidence, HumanReview, Project
from pmwizard.models.enums import ActionItemStatus, ReviewStatus
from pmwizard.persistence import (
    Base,
    ProjectMemoryService,
    create_engine_from_url,
    create_session_factory,
)
from pmwizard.persistence.orm import AISuggestionORM


NOW = datetime(2026, 10, 21, 18, 0, tzinfo=timezone.utc)


def _evidence(project_id, text: str) -> Evidence:
    return Evidence(
        project_id=project_id,
        source_type="email",
        source_system="synthetic",
        captured_at=NOW,
        content_excerpt=text,
        permission_scope=["project:read"],
    )


def test_completed_signal_suggests_status_change() -> None:
    project_id = uuid4()
    action = ActionItem(
        project_id=project_id,
        title="Verify API access",
        status=ActionItemStatus.IN_PROGRESS,
        created_at=NOW,
    )

    assessment = ActionItemProgressClassifier().assess(
        action,
        _evidence(project_id, "Verify API access was completed today."),
    )

    assert assessment.outcome == ProgressOutcome.STATUS_CHANGE
    assert assessment.suggested_status == ActionItemStatus.COMPLETED
    assert assessment.confidence >= 0.94


def test_same_status_becomes_progress_update() -> None:
    project_id = uuid4()
    action = ActionItem(
        project_id=project_id,
        title="Prepare migration",
        status=ActionItemStatus.IN_PROGRESS,
        created_at=NOW,
    )

    assessment = ActionItemProgressClassifier().assess(
        action,
        _evidence(project_id, "Prepare migration is in progress."),
    )

    assert assessment.outcome == ProgressOutcome.PROGRESS_UPDATE
    assert assessment.suggested_status == ActionItemStatus.IN_PROGRESS


def test_external_waiting_signal_suggests_pending_external() -> None:
    project_id = uuid4()
    action = ActionItem(
        project_id=project_id,
        title="Receive vendor credentials",
        status=ActionItemStatus.IN_PROGRESS,
        created_at=NOW,
    )

    assessment = ActionItemProgressClassifier().assess(
        action,
        _evidence(
            project_id,
            "Receive vendor credentials is waiting for the vendor response.",
        ),
    )

    assert assessment.outcome == ProgressOutcome.STATUS_CHANGE
    assert assessment.suggested_status == ActionItemStatus.PENDING_EXTERNAL


def test_conflicting_signals_are_ambiguous() -> None:
    project_id = uuid4()
    action = ActionItem(
        project_id=project_id,
        title="Review legal clauses",
        status=ActionItemStatus.IN_PROGRESS,
        created_at=NOW,
    )

    assessment = ActionItemProgressClassifier().assess(
        action,
        _evidence(
            project_id,
            "Review legal clauses was completed, but two clauses remain unresolved.",
        ),
    )

    assert assessment.outcome == ProgressOutcome.AMBIGUOUS
    assert assessment.suggested_status is None
    assert {signal.status for signal in assessment.signals} == {
        ActionItemStatus.COMPLETED,
        ActionItemStatus.BLOCKED,
    }


def test_negated_completion_does_not_mark_complete() -> None:
    project_id = uuid4()
    action = ActionItem(
        project_id=project_id,
        title="Validate integration",
        status=ActionItemStatus.IN_PROGRESS,
        created_at=NOW,
    )

    assessment = ActionItemProgressClassifier().assess(
        action,
        _evidence(project_id, "Validate integration is not completed yet."),
    )

    assert assessment.outcome == ProgressOutcome.PROGRESS_UPDATE
    assert assessment.suggested_status == ActionItemStatus.IN_PROGRESS


def test_no_explicit_signal_does_not_invent_progress() -> None:
    project_id = uuid4()
    action = ActionItem(
        project_id=project_id,
        title="Review architecture",
        status=ActionItemStatus.NOT_STARTED,
        created_at=NOW,
    )

    assessment = ActionItemProgressClassifier().assess(
        action,
        _evidence(project_id, "Review architecture was discussed with the team."),
    )

    assert assessment.outcome == ProgressOutcome.NO_SIGNAL
    assert assessment.suggested_status is None
    assert assessment.confidence == 0.0


def test_classifier_rejects_cross_project_evidence() -> None:
    action = ActionItem(
        project_id=uuid4(),
        title="Review architecture",
        created_at=NOW,
    )

    with pytest.raises(ValueError, match="same project"):
        ActionItemProgressClassifier().assess(
            action,
            _evidence(uuid4(), "Review architecture is complete."),
        )


@pytest.fixture()
def session():
    engine = create_engine_from_url("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    factory = create_session_factory(engine)
    with factory() as session:
        yield session


def test_pipeline_creates_reviewable_suggestion_without_mutating_action(session) -> None:
    tenant_id = uuid4()
    memory = ProjectMemoryService(session)
    project = memory.create_project(
        tenant_id,
        Project(name="Progress Intelligence Demo"),
    )
    action = memory.add_action_item(
        tenant_id,
        ActionItem(
            project_id=project.id,
            title="Verify API access",
            status=ActionItemStatus.IN_PROGRESS,
            created_at=NOW,
        ),
    )
    evidence = memory.add_evidence(
        tenant_id,
        _evidence(
            project.id,
            "Verify API access was completed today.",
        ),
    )

    result = ProgressIntelligenceService(session).analyze_evidence(
        tenant_id,
        evidence,
    )

    assert result.outcome == ProgressPipelineOutcome.SUGGESTION_CREATED
    assert result.suggestion is not None
    assert result.suggestion.target_entity_id == action.id
    assert result.suggestion.proposed_changes["status"] == "completed"
    assert result.suggestion.proposed_changes["latest_evidence_id"] == str(evidence.id)

    governed = memory.repository.get_action_item(tenant_id, action.id)
    assert governed is not None
    assert governed.status == ActionItemStatus.IN_PROGRESS
    assert governed.latest_evidence_id is None


def test_human_acceptance_applies_progress_suggestion_and_evidence_link(session) -> None:
    tenant_id = uuid4()
    reviewer_id = uuid4()
    memory = ProjectMemoryService(session)
    project = memory.create_project(
        tenant_id,
        Project(name="Human Governed Progress"),
    )
    action = memory.add_action_item(
        tenant_id,
        ActionItem(
            project_id=project.id,
            title="Confirm vendor access",
            status=ActionItemStatus.IN_PROGRESS,
            created_at=NOW,
        ),
    )
    evidence = memory.add_evidence(
        tenant_id,
        _evidence(
            project.id,
            "Confirm vendor access was completed today.",
        ),
    )

    result = ProgressIntelligenceService(session).analyze_evidence(
        tenant_id,
        evidence,
    )
    assert result.suggestion is not None

    updated = memory.review_suggestion(
        tenant_id,
        HumanReview(
            project_id=project.id,
            suggestion_id=result.suggestion.id,
            reviewer_id=reviewer_id,
            status=ReviewStatus.ACCEPTED,
            reviewed_at=NOW,
        ),
    )

    assert updated is not None
    assert updated.status == ActionItemStatus.COMPLETED
    assert updated.latest_evidence_id == evidence.id
    assert updated.last_progress_date == NOW
    assert updated.progress_summary == evidence.content_excerpt


def test_pipeline_requires_entity_review_before_progress_analysis(session) -> None:
    tenant_id = uuid4()
    memory = ProjectMemoryService(session)
    project = memory.create_project(tenant_id, Project(name="Ambiguous Entity"))
    memory.add_action_item(
        tenant_id,
        ActionItem(
            project_id=project.id,
            title="Review API configuration",
            status=ActionItemStatus.IN_PROGRESS,
            created_at=NOW,
        ),
    )
    memory.add_action_item(
        tenant_id,
        ActionItem(
            project_id=project.id,
            title="Review API credentials",
            status=ActionItemStatus.IN_PROGRESS,
            created_at=NOW,
        ),
    )
    evidence = memory.add_evidence(
        tenant_id,
        _evidence(project.id, "The API review is in progress."),
    )

    result = ProgressIntelligenceService(session).analyze_evidence(
        tenant_id,
        evidence,
    )

    assert result.outcome == ProgressPipelineOutcome.ENTITY_REVIEW_REQUIRED
    assert result.suggestion is None


def test_pipeline_does_not_create_suggestion_without_progress_signal(session) -> None:
    tenant_id = uuid4()
    memory = ProjectMemoryService(session)
    project = memory.create_project(tenant_id, Project(name="No Progress Signal"))
    memory.add_action_item(
        tenant_id,
        ActionItem(
            project_id=project.id,
            title="Review contract",
            status=ActionItemStatus.IN_PROGRESS,
            created_at=NOW,
        ),
    )
    evidence = memory.add_evidence(
        tenant_id,
        _evidence(project.id, "Review contract was discussed today."),
    )

    result = ProgressIntelligenceService(session).analyze_evidence(
        tenant_id,
        evidence,
    )

    assert result.outcome == ProgressPipelineOutcome.NO_PROGRESS_SIGNAL
    count = session.scalar(select(func.count()).select_from(AISuggestionORM))
    assert count == 0


def test_pipeline_does_not_create_suggestion_for_conflicting_progress(session) -> None:
    tenant_id = uuid4()
    memory = ProjectMemoryService(session)
    project = memory.create_project(tenant_id, Project(name="Conflicting Progress"))
    memory.add_action_item(
        tenant_id,
        ActionItem(
            project_id=project.id,
            title="Review legal clauses",
            status=ActionItemStatus.IN_PROGRESS,
            created_at=NOW,
        ),
    )
    evidence = memory.add_evidence(
        tenant_id,
        _evidence(
            project.id,
            "Review legal clauses was completed but two clauses remain unresolved.",
        ),
    )

    result = ProgressIntelligenceService(session).analyze_evidence(
        tenant_id,
        evidence,
    )

    assert result.outcome == ProgressPipelineOutcome.AMBIGUOUS_PROGRESS
    assert result.suggestion is None
    count = session.scalar(select(func.count()).select_from(AISuggestionORM))
    assert count == 0


def test_pipeline_enforces_tenant_scope(session) -> None:
    tenant_a = uuid4()
    tenant_b = uuid4()
    memory = ProjectMemoryService(session)
    project = memory.create_project(tenant_a, Project(name="Tenant A"))
    evidence = _evidence(project.id, "Confirm access was completed.")

    with pytest.raises(LookupError):
        ProgressIntelligenceService(session).analyze_evidence(
            tenant_b,
            evidence,
        )
