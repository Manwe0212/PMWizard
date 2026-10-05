"""Initial tests for PMWizard canonical models."""

from datetime import datetime, timezone
from uuid import uuid4

import pytest
from pydantic import ValidationError

from pmwizard.models import AISuggestion, ActionItem, Evidence, Project
from pmwizard.models.enums import ActionItemStatus, SuggestionType


def test_project_can_exist_without_program_or_portfolio() -> None:
    project = Project(name="Synthetic Integration Project")

    assert project.name == "Synthetic Integration Project"
    assert project.program_id is None
    assert project.portfolio_id is None


def test_action_item_defaults_to_not_started() -> None:
    action = ActionItem(project_id=uuid4(), title="Review integration mapping")

    assert action.status == ActionItemStatus.NOT_STARTED


def test_evidence_preserves_permission_scope() -> None:
    evidence = Evidence(
        project_id=uuid4(),
        source_type="meeting_minutes",
        source_system="synthetic",
        captured_at=datetime.now(timezone.utc),
        permission_scope=["project:read"],
    )

    assert evidence.permission_scope == ["project:read"]


def test_ai_suggestion_requires_bounded_confidence() -> None:
    with pytest.raises(ValidationError):
        AISuggestion(
            project_id=uuid4(),
            suggestion_type=SuggestionType.ACTION_PROGRESS,
            reason="Synthetic test",
            confidence=1.2,
        )


def test_ai_suggestion_does_not_change_action_item() -> None:
    action = ActionItem(
        project_id=uuid4(),
        title="Verify API access",
        status=ActionItemStatus.IN_PROGRESS,
    )

    suggestion = AISuggestion(
        project_id=action.project_id,
        suggestion_type=SuggestionType.ACTION_PROGRESS,
        target_entity_type="ActionItem",
        target_entity_id=action.id,
        proposed_changes={"status": "completed"},
        reason="New evidence suggests the work may be complete.",
        confidence=0.94,
    )

    assert action.status == ActionItemStatus.IN_PROGRESS
    assert suggestion.proposed_changes["status"] == "completed"
