"""Repository operations for governed Project Memory."""

from __future__ import annotations

from enum import Enum
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from pmwizard.models import (
    AISuggestion,
    ActionItem,
    Evidence,
    HumanReview,
    Project,
    Provenance,
)
from pmwizard.models.enums import ActionItemStatus, ReviewStatus

from .orm import (
    AISuggestionORM,
    ActionItemORM,
    AuditLogORM,
    EvidenceORM,
    HumanReviewORM,
    ProjectORM,
)


def _enum_value(value: Any) -> Any:
    return value.value if isinstance(value, Enum) else value


def _provenance_json(provenance: Provenance) -> dict[str, Any]:
    return provenance.model_dump(mode="json")


class ProjectMemoryRepository:
    """Tenant-scoped persistence operations.

    Repository methods flush but do not commit. Transaction boundaries belong
    to the application service.
    """

    def __init__(self, session: Session) -> None:
        self.session = session

    def add_project(self, tenant_id: UUID, project: Project) -> Project:
        row = ProjectORM(
            id=project.id,
            tenant_id=tenant_id,
            name=project.name,
            description=project.description,
            objective=project.objective,
            portfolio_id=project.portfolio_id,
            program_id=project.program_id,
            project_manager_id=project.project_manager_id,
            sponsor_id=project.sponsor_id,
            methodology=project.methodology,
            industry=project.industry,
            lifecycle_phase=project.lifecycle_phase,
            status=project.status,
            priority=project.priority,
            start_date=project.start_date,
            planned_end_date=project.planned_end_date,
            forecast_end_date=project.forecast_end_date,
            actual_end_date=project.actual_end_date,
            business_value=project.business_value,
            source_system=project.source_system,
            external_id=project.external_id,
            created_at=project.created_at,
            updated_at=project.updated_at,
            provenance=_provenance_json(project.provenance),
        )
        self.session.add(row)
        self.session.flush()
        return project

    def get_project(self, tenant_id: UUID, project_id: UUID) -> Project | None:
        row = self.session.scalar(
            select(ProjectORM).where(
                ProjectORM.tenant_id == tenant_id,
                ProjectORM.id == project_id,
            )
        )
        if row is None:
            return None
        return Project(
            id=row.id,
            name=row.name,
            description=row.description,
            objective=row.objective,
            portfolio_id=row.portfolio_id,
            program_id=row.program_id,
            project_manager_id=row.project_manager_id,
            sponsor_id=row.sponsor_id,
            methodology=row.methodology,
            industry=row.industry,
            lifecycle_phase=row.lifecycle_phase,
            status=row.status,
            priority=row.priority,
            start_date=row.start_date,
            planned_end_date=row.planned_end_date,
            forecast_end_date=row.forecast_end_date,
            actual_end_date=row.actual_end_date,
            business_value=row.business_value,
            source_system=row.source_system,
            external_id=row.external_id,
            created_at=row.created_at,
            updated_at=row.updated_at,
            provenance=Provenance.model_validate(row.provenance),
        )

    def add_action_item(self, tenant_id: UUID, action: ActionItem) -> ActionItem:
        row = ActionItemORM(
            id=action.id,
            tenant_id=tenant_id,
            project_id=action.project_id,
            title=action.title,
            description=action.description,
            owner_id=action.owner_id,
            due_date=action.due_date,
            completed_at=action.completed_at,
            status=action.status.value,
            priority=action.priority,
            progress_summary=action.progress_summary,
            last_progress_date=action.last_progress_date,
            latest_evidence_id=action.latest_evidence_id,
            created_at=action.created_at,
            updated_at=action.updated_at,
            provenance=_provenance_json(action.provenance),
        )
        self.session.add(row)
        self.session.flush()
        return action

    def get_action_item(self, tenant_id: UUID, action_id: UUID) -> ActionItem | None:
        row = self.session.scalar(
            select(ActionItemORM).where(
                ActionItemORM.tenant_id == tenant_id,
                ActionItemORM.id == action_id,
            )
        )
        return self._action_from_row(row) if row is not None else None

    def get_open_action_items(
        self, tenant_id: UUID, project_id: UUID
    ) -> list[ActionItem]:
        closed = {
            ActionItemStatus.COMPLETED.value,
            ActionItemStatus.CANCELLED.value,
        }
        rows = self.session.scalars(
            select(ActionItemORM)
            .where(
                ActionItemORM.tenant_id == tenant_id,
                ActionItemORM.project_id == project_id,
                ActionItemORM.status.not_in(closed),
            )
            .order_by(ActionItemORM.created_at)
        ).all()
        return [self._action_from_row(row) for row in rows]

    def update_action_item(self, tenant_id: UUID, action: ActionItem) -> ActionItem:
        row = self.session.scalar(
            select(ActionItemORM).where(
                ActionItemORM.tenant_id == tenant_id,
                ActionItemORM.id == action.id,
            )
        )
        if row is None:
            raise LookupError(f"ActionItem {action.id} not found for tenant")

        row.title = action.title
        row.description = action.description
        row.owner_id = action.owner_id
        row.due_date = action.due_date
        row.completed_at = action.completed_at
        row.status = action.status.value
        row.priority = action.priority
        row.progress_summary = action.progress_summary
        row.last_progress_date = action.last_progress_date
        row.latest_evidence_id = action.latest_evidence_id
        row.updated_at = action.updated_at
        row.provenance = _provenance_json(action.provenance)
        self.session.flush()
        return action

    def add_evidence(self, tenant_id: UUID, evidence: Evidence) -> Evidence:
        row = EvidenceORM(
            id=evidence.id,
            tenant_id=tenant_id,
            project_id=evidence.project_id,
            source_type=evidence.source_type,
            source_system=evidence.source_system,
            source_reference=evidence.source_reference,
            external_id=evidence.external_id,
            author=evidence.author,
            captured_at=evidence.captured_at,
            effective_at=evidence.effective_at,
            content_excerpt=evidence.content_excerpt,
            content_hash=evidence.content_hash,
            permission_scope=evidence.permission_scope,
            created_at=evidence.created_at,
            updated_at=evidence.updated_at,
            provenance=_provenance_json(evidence.provenance),
        )
        self.session.add(row)
        self.session.flush()
        return evidence

    def add_ai_suggestion(
        self, tenant_id: UUID, suggestion: AISuggestion
    ) -> AISuggestion:
        row = AISuggestionORM(
            id=suggestion.id,
            tenant_id=tenant_id,
            project_id=suggestion.project_id,
            suggestion_type=suggestion.suggestion_type.value,
            target_entity_type=suggestion.target_entity_type,
            target_entity_id=suggestion.target_entity_id,
            proposed_changes=suggestion.model_dump(mode="json")["proposed_changes"],
            reason=suggestion.reason,
            evidence_ids=[str(value) for value in suggestion.evidence_ids],
            confidence=suggestion.confidence,
            review_status=suggestion.review_status.value,
            model_provider=suggestion.model_provider,
            model_name=suggestion.model_name,
            created_at=suggestion.created_at,
            updated_at=suggestion.updated_at,
            provenance=_provenance_json(suggestion.provenance),
        )
        self.session.add(row)
        self.session.flush()
        return suggestion

    def get_ai_suggestion(
        self, tenant_id: UUID, suggestion_id: UUID
    ) -> AISuggestion | None:
        row = self.session.scalar(
            select(AISuggestionORM).where(
                AISuggestionORM.tenant_id == tenant_id,
                AISuggestionORM.id == suggestion_id,
            )
        )
        if row is None:
            return None
        return AISuggestion(
            id=row.id,
            project_id=row.project_id,
            suggestion_type=row.suggestion_type,
            target_entity_type=row.target_entity_type,
            target_entity_id=row.target_entity_id,
            proposed_changes=row.proposed_changes,
            reason=row.reason,
            evidence_ids=row.evidence_ids,
            confidence=row.confidence,
            review_status=row.review_status,
            model_provider=row.model_provider,
            model_name=row.model_name,
            created_at=row.created_at,
            updated_at=row.updated_at,
            provenance=Provenance.model_validate(row.provenance),
        )

    def set_suggestion_review_status(
        self, tenant_id: UUID, suggestion_id: UUID, status: ReviewStatus
    ) -> None:
        row = self.session.scalar(
            select(AISuggestionORM).where(
                AISuggestionORM.tenant_id == tenant_id,
                AISuggestionORM.id == suggestion_id,
            )
        )
        if row is None:
            raise LookupError(f"AISuggestion {suggestion_id} not found for tenant")
        row.review_status = status.value
        self.session.flush()

    def add_human_review(self, tenant_id: UUID, review: HumanReview) -> HumanReview:
        row = HumanReviewORM(
            id=review.id,
            tenant_id=tenant_id,
            project_id=review.project_id,
            suggestion_id=review.suggestion_id,
            reviewer_id=review.reviewer_id,
            status=review.status.value,
            reviewed_at=review.reviewed_at,
            reviewer_note=review.reviewer_note,
            final_changes=review.model_dump(mode="json")["final_changes"],
            created_at=review.created_at,
            updated_at=review.updated_at,
            provenance=_provenance_json(review.provenance),
        )
        self.session.add(row)
        self.session.flush()
        return review

    def add_audit_entry(
        self,
        *,
        tenant_id: UUID,
        project_id: UUID,
        actor_id: UUID | None,
        action: str,
        entity_type: str,
        entity_id: UUID,
        previous_state: dict[str, Any] | None,
        proposed_state: dict[str, Any] | None,
        final_state: dict[str, Any] | None,
        evidence_ids: list[UUID],
    ) -> None:
        row = AuditLogORM(
            tenant_id=tenant_id,
            project_id=project_id,
            actor_id=actor_id,
            action=action,
            entity_type=entity_type,
            entity_id=entity_id,
            previous_state=previous_state,
            proposed_state=proposed_state,
            final_state=final_state,
            evidence_ids=[str(value) for value in evidence_ids],
        )
        self.session.add(row)
        self.session.flush()

    @staticmethod
    def _action_from_row(row: ActionItemORM) -> ActionItem:
        return ActionItem(
            id=row.id,
            project_id=row.project_id,
            title=row.title,
            description=row.description,
            owner_id=row.owner_id,
            due_date=row.due_date,
            completed_at=row.completed_at,
            status=row.status,
            priority=row.priority,
            progress_summary=row.progress_summary,
            last_progress_date=row.last_progress_date,
            latest_evidence_id=row.latest_evidence_id,
            created_at=row.created_at,
            updated_at=row.updated_at,
            provenance=Provenance.model_validate(row.provenance),
        )
