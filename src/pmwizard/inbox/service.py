"""Project Inbox application service."""

from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy.orm import Session

from pmwizard.models import HumanReview
from pmwizard.models.enums import ReviewStatus
from pmwizard.persistence import ProjectMemoryService

from .schemas import (
    InboxEvidenceView,
    InboxListResponse,
    InboxSuggestionDetail,
    InboxSuggestionSummary,
    ReviewCommand,
    ReviewResponse,
)


class ProjectInboxService:
    """Read and review AI suggestions within an authorized project scope."""

    DEFAULT_STATUSES = [ReviewStatus.PENDING, ReviewStatus.DEFERRED]

    def __init__(self, session: Session) -> None:
        self.memory = ProjectMemoryService(session)
        self.repository = self.memory.repository

    def list_items(
        self,
        *,
        tenant_id: UUID,
        project_id: UUID,
        permissions: set[str],
        statuses: list[ReviewStatus] | None = None,
        limit: int = 100,
    ) -> InboxListResponse:
        self._require_project(tenant_id, project_id)
        selected_statuses = statuses or self.DEFAULT_STATUSES
        suggestions = self.repository.list_ai_suggestions(
            tenant_id,
            project_id,
            statuses=selected_statuses,
            limit=limit,
        )

        items: list[InboxSuggestionSummary] = []
        for suggestion in suggestions:
            evidence = self._load_authorized_evidence(
                tenant_id=tenant_id,
                project_id=project_id,
                evidence_ids=suggestion.evidence_ids,
                permissions=permissions,
            )
            if evidence is None:
                continue
            items.append(self._summary(suggestion, evidence))

        return InboxListResponse(
            project_id=project_id,
            count=len(items),
            items=items,
        )

    def get_item(
        self,
        *,
        tenant_id: UUID,
        project_id: UUID,
        suggestion_id: UUID,
        permissions: set[str],
    ) -> InboxSuggestionDetail | None:
        self._require_project(tenant_id, project_id)
        suggestion = self.repository.get_ai_suggestion(tenant_id, suggestion_id)
        if suggestion is None or suggestion.project_id != project_id:
            return None

        evidence = self._load_authorized_evidence(
            tenant_id=tenant_id,
            project_id=project_id,
            evidence_ids=suggestion.evidence_ids,
            permissions=permissions,
        )
        if evidence is None:
            return None

        target_action = None
        if (
            suggestion.target_entity_type == "ActionItem"
            and suggestion.target_entity_id is not None
        ):
            target_action = self.repository.get_action_item(
                tenant_id,
                suggestion.target_entity_id,
            )
            if target_action is not None and target_action.project_id != project_id:
                target_action = None

        return InboxSuggestionDetail(
            suggestion=self._summary(suggestion, evidence),
            target_action_item=target_action,
            evidence=[self._evidence_view(item) for item in evidence],
        )

    def review_item(
        self,
        *,
        tenant_id: UUID,
        project_id: UUID,
        suggestion_id: UUID,
        reviewer_id: UUID,
        permissions: set[str],
        command: ReviewCommand,
    ) -> ReviewResponse | None:
        detail = self.get_item(
            tenant_id=tenant_id,
            project_id=project_id,
            suggestion_id=suggestion_id,
            permissions=permissions,
        )
        if detail is None:
            return None

        updated = self.memory.review_suggestion(
            tenant_id,
            HumanReview(
                project_id=project_id,
                suggestion_id=suggestion_id,
                reviewer_id=reviewer_id,
                status=command.status,
                reviewed_at=datetime.now(timezone.utc),
                reviewer_note=command.reviewer_note,
                final_changes=command.final_changes,
            ),
        )

        suggestion = self.repository.get_ai_suggestion(tenant_id, suggestion_id)
        if suggestion is None:
            raise RuntimeError("Reviewed suggestion disappeared after commit")

        return ReviewResponse(
            suggestion_id=suggestion_id,
            review_status=suggestion.review_status,
            updated_action_item=updated,
        )

    def _load_authorized_evidence(
        self,
        *,
        tenant_id: UUID,
        project_id: UUID,
        evidence_ids: list[UUID],
        permissions: set[str],
    ):
        evidence = []
        for evidence_id in evidence_ids:
            item = self.repository.get_evidence(tenant_id, evidence_id)
            if item is None or item.project_id != project_id:
                return None
            if not self._can_view_evidence(item.permission_scope, permissions):
                return None
            evidence.append(item)
        return evidence

    @staticmethod
    def _can_view_evidence(
        required_scopes: list[str],
        permissions: set[str],
    ) -> bool:
        return set(required_scopes).issubset(permissions)

    @staticmethod
    def _summary(suggestion, evidence) -> InboxSuggestionSummary:
        sources = sorted(
            {
                item.source_system or item.source_type
                for item in evidence
            }
        )
        return InboxSuggestionSummary(
            id=suggestion.id,
            project_id=suggestion.project_id,
            suggestion_type=suggestion.suggestion_type,
            target_entity_type=suggestion.target_entity_type,
            target_entity_id=suggestion.target_entity_id,
            proposed_changes=suggestion.proposed_changes,
            reason=suggestion.reason,
            confidence=suggestion.confidence,
            review_status=suggestion.review_status,
            evidence_count=len(evidence),
            evidence_sources=sources,
            created_at=suggestion.created_at,
        )

    @staticmethod
    def _evidence_view(evidence) -> InboxEvidenceView:
        return InboxEvidenceView(
            id=evidence.id,
            source_type=evidence.source_type,
            source_system=evidence.source_system,
            source_reference=evidence.source_reference,
            author=evidence.author,
            captured_at=evidence.captured_at,
            content_excerpt=evidence.content_excerpt,
            permission_scope=evidence.permission_scope,
        )

    def _require_project(self, tenant_id: UUID, project_id: UUID) -> None:
        if self.repository.get_project(tenant_id, project_id) is None:
            raise LookupError("Project not found for tenant")
