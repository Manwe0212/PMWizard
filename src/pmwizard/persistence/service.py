"""Application service for human-governed Project Memory."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from sqlalchemy.orm import Session

from pmwizard.models import AISuggestion, ActionItem, Evidence, HumanReview, Project
from pmwizard.models.enums import ReviewStatus

from .repositories import ProjectMemoryRepository


class ProjectMemoryService:
    """Coordinates Project Memory transactions and human-reviewed changes."""

    _ACTION_ITEM_EDITABLE_FIELDS = {
        "status",
        "progress_summary",
        "last_progress_date",
        "completed_at",
        "due_date",
        "priority",
    }

    def __init__(self, session: Session) -> None:
        self.session = session
        self.repository = ProjectMemoryRepository(session)

    def create_project(self, tenant_id: UUID, project: Project) -> Project:
        result = self.repository.add_project(tenant_id, project)
        self.session.commit()
        return result

    def add_action_item(self, tenant_id: UUID, action: ActionItem) -> ActionItem:
        self._require_project(tenant_id, action.project_id)
        result = self.repository.add_action_item(tenant_id, action)
        self.session.commit()
        return result

    def add_evidence(self, tenant_id: UUID, evidence: Evidence) -> Evidence:
        self._require_project(tenant_id, evidence.project_id)
        result = self.repository.add_evidence(tenant_id, evidence)
        self.session.commit()
        return result

    def add_ai_suggestion(
        self, tenant_id: UUID, suggestion: AISuggestion
    ) -> AISuggestion:
        self._require_project(tenant_id, suggestion.project_id)
        result = self.repository.add_ai_suggestion(tenant_id, suggestion)
        self.session.commit()
        return result

    def get_open_action_items(
        self, tenant_id: UUID, project_id: UUID
    ) -> list[ActionItem]:
        self._require_project(tenant_id, project_id)
        return self.repository.get_open_action_items(tenant_id, project_id)

    def review_suggestion(
        self, tenant_id: UUID, review: HumanReview
    ) -> ActionItem | None:
        """Persist a human review and apply approved ActionItem changes.

        V0 intentionally supports governed write-through only for ActionItem
        updates. Other suggestion targets remain reviewable but do not mutate
        governed state yet.
        """
        suggestion = self.repository.get_ai_suggestion(
            tenant_id, review.suggestion_id
        )
        if suggestion is None:
            raise LookupError("Suggestion not found for tenant")
        if suggestion.project_id != review.project_id:
            raise ValueError("Review project does not match suggestion project")

        self.repository.add_human_review(tenant_id, review)
        self.repository.set_suggestion_review_status(
            tenant_id, suggestion.id, review.status
        )

        updated_action: ActionItem | None = None
        previous_state: dict[str, Any] | None = None
        final_state: dict[str, Any] | None = None

        if review.status in {ReviewStatus.ACCEPTED, ReviewStatus.EDITED}:
            if (
                suggestion.target_entity_type == "ActionItem"
                and suggestion.target_entity_id is not None
            ):
                action = self.repository.get_action_item(
                    tenant_id, suggestion.target_entity_id
                )
                if action is None:
                    raise LookupError("Target ActionItem not found for tenant")
                if action.project_id != suggestion.project_id:
                    raise ValueError("Target ActionItem belongs to another project")

                previous_state = action.model_dump(mode="json")
                changes = (
                    review.final_changes
                    if review.status == ReviewStatus.EDITED
                    else suggestion.proposed_changes
                )
                safe_changes = {
                    key: value
                    for key, value in changes.items()
                    if key in self._ACTION_ITEM_EDITABLE_FIELDS
                }

                candidate = {
                    **action.model_dump(mode="python"),
                    **safe_changes,
                    "updated_at": datetime.now(timezone.utc),
                }
                updated_action = ActionItem.model_validate(candidate)
                self.repository.update_action_item(tenant_id, updated_action)
                final_state = updated_action.model_dump(mode="json")

        self.repository.add_audit_entry(
            tenant_id=tenant_id,
            project_id=review.project_id,
            actor_id=review.reviewer_id,
            action=f"suggestion_{review.status.value}",
            entity_type=suggestion.target_entity_type or "AISuggestion",
            entity_id=suggestion.target_entity_id or suggestion.id,
            previous_state=previous_state,
            proposed_state=suggestion.proposed_changes,
            final_state=final_state,
            evidence_ids=suggestion.evidence_ids,
        )
        self.session.commit()
        return updated_action

    def _require_project(self, tenant_id: UUID, project_id: UUID) -> Project:
        project = self.repository.get_project(tenant_id, project_id)
        if project is None:
            raise LookupError("Project not found for tenant")
        return project
