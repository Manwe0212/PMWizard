"""Tests for explainable Entity Resolution V0."""

from datetime import datetime, timezone
from uuid import uuid4

import pytest

from pmwizard.models import ActionItem, Evidence, Project
from pmwizard.models.enums import ActionItemStatus
from pmwizard.persistence import Base, ProjectMemoryService, create_engine_from_url, create_session_factory
from pmwizard.resolution import (
    ActionItemResolver,
    ProjectMemoryResolutionService,
    ResolutionContext,
    ResolutionOutcome,
)


def _evidence(project_id, text: str) -> Evidence:
    return Evidence(
        project_id=project_id,
        source_type="meeting_note",
        source_system="synthetic",
        captured_at=datetime.now(timezone.utc),
        content_excerpt=text,
        permission_scope=["project:read"],
    )


def test_exact_title_phrase_can_be_deterministically_matched() -> None:
    project_id = uuid4()
    action = ActionItem(
        project_id=project_id,
        title="Verify API access",
        status=ActionItemStatus.IN_PROGRESS,
    )
    evidence = _evidence(
        project_id,
        "The team completed Verify API access today.",
    )

    result = ActionItemResolver().resolve(evidence, [action])

    assert result.outcome == ResolutionOutcome.MATCHED
    assert result.best_candidate is not None
    assert result.best_candidate.entity_id == action.id
    assert result.best_candidate.breakdown.phrase_match == 1.0
    assert result.best_candidate.breakdown.title_coverage == 1.0


def test_semantically_plausible_but_non_exact_update_requires_review() -> None:
    project_id = uuid4()
    action = ActionItem(
        project_id=project_id,
        title="Verify API access",
        status=ActionItemStatus.IN_PROGRESS,
    )
    evidence = _evidence(
        project_id,
        "API access has been verified and is working.",
    )

    result = ActionItemResolver().resolve(evidence, [action])

    assert result.outcome == ResolutionOutcome.NEEDS_REVIEW
    assert result.best_candidate is not None
    assert result.best_candidate.entity_id == action.id
    assert result.best_candidate.breakdown.title_coverage >= 0.66


def test_similar_candidates_are_not_auto_linked_when_ambiguous() -> None:
    project_id = uuid4()
    actions = [
        ActionItem(
            project_id=project_id,
            title="Review API configuration",
            status=ActionItemStatus.IN_PROGRESS,
        ),
        ActionItem(
            project_id=project_id,
            title="Review API credentials",
            status=ActionItemStatus.IN_PROGRESS,
        ),
    ]
    evidence = _evidence(
        project_id,
        "The API review is still in progress.",
    )

    result = ActionItemResolver().resolve(evidence, actions)

    assert result.outcome == ResolutionOutcome.NEEDS_REVIEW
    assert len(result.candidates) == 2


def test_unrelated_evidence_returns_no_match() -> None:
    project_id = uuid4()
    action = ActionItem(
        project_id=project_id,
        title="Review contract",
        status=ActionItemStatus.IN_PROGRESS,
    )
    evidence = _evidence(
        project_id,
        "Marketing campaign assets were approved.",
    )

    result = ActionItemResolver().resolve(evidence, [action])

    assert result.outcome == ResolutionOutcome.NO_MATCH


def test_owner_context_can_disambiguate_identical_titles() -> None:
    project_id = uuid4()
    owner_a = uuid4()
    owner_b = uuid4()
    action_a = ActionItem(
        project_id=project_id,
        title="Confirm access",
        owner_id=owner_a,
        status=ActionItemStatus.IN_PROGRESS,
    )
    action_b = ActionItem(
        project_id=project_id,
        title="Confirm access",
        owner_id=owner_b,
        status=ActionItemStatus.IN_PROGRESS,
    )
    evidence = _evidence(
        project_id,
        "Confirm access was completed.",
    )

    result = ActionItemResolver().resolve(
        evidence,
        [action_a, action_b],
        context=ResolutionContext(owner_id=owner_b),
    )

    assert result.outcome == ResolutionOutcome.MATCHED
    assert result.best_candidate is not None
    assert result.best_candidate.entity_id == action_b.id
    assert result.best_candidate.breakdown.owner_match == 1.0


@pytest.fixture()
def session():
    engine = create_engine_from_url("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    factory = create_session_factory(engine)
    with factory() as session:
        yield session


def test_resolution_service_uses_only_open_items_in_authorized_project(session) -> None:
    tenant_id = uuid4()
    project_memory = ProjectMemoryService(session)
    project = project_memory.create_project(
        tenant_id,
        Project(name="Resolution Service Test"),
    )

    open_action = project_memory.add_action_item(
        tenant_id,
        ActionItem(
            project_id=project.id,
            title="Confirm vendor access",
            status=ActionItemStatus.IN_PROGRESS,
        ),
    )
    project_memory.add_action_item(
        tenant_id,
        ActionItem(
            project_id=project.id,
            title="Confirm vendor access",
            status=ActionItemStatus.COMPLETED,
        ),
    )

    evidence = _evidence(
        project.id,
        "Confirm vendor access was completed today.",
    )

    resolution = ProjectMemoryResolutionService(session)
    result = resolution.resolve_evidence_to_action_items(
        tenant_id,
        evidence,
    )

    assert result.outcome == ResolutionOutcome.MATCHED
    assert result.best_candidate is not None
    assert result.best_candidate.entity_id == open_action.id
    assert len(result.candidates) == 1


def test_resolution_service_blocks_cross_tenant_project_access(session) -> None:
    tenant_a = uuid4()
    tenant_b = uuid4()
    project_memory = ProjectMemoryService(session)
    project = project_memory.create_project(
        tenant_a,
        Project(name="Private Tenant Project"),
    )

    evidence = _evidence(project.id, "Review contract is complete.")
    resolution = ProjectMemoryResolutionService(session)

    with pytest.raises(LookupError):
        resolution.resolve_evidence_to_action_items(
            tenant_b,
            evidence,
        )
