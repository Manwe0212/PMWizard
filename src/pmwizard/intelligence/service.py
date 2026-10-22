"""End-to-end Progress Intelligence V0 pipeline."""

from __future__ import annotations

from enum import StrEnum
from uuid import UUID

from pydantic import BaseModel, ConfigDict

from sqlalchemy.orm import Session

from pmwizard.models import AISuggestion, Evidence
from pmwizard.models.enums import SuggestionType
from pmwizard.persistence.repositories import ProjectMemoryRepository
from pmwizard.persistence.service import ProjectMemoryService
from pmwizard.resolution import (
    ProjectMemoryResolutionService,
    ResolutionContext,
    ResolutionOutcome,
    ResolutionResult,
)

from .progress import (
    ActionItemProgressClassifier,
    ProgressAssessment,
    ProgressOutcome,
)


class ProgressPipelineOutcome(StrEnum):
    SUGGESTION_CREATED = "suggestion_created"
    ENTITY_REVIEW_REQUIRED = "entity_review_required"
    NO_ENTITY_MATCH = "no_entity_match"
    NO_PROGRESS_SIGNAL = "no_progress_signal"
    AMBIGUOUS_PROGRESS = "ambiguous_progress"


class ProgressIntelligenceResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    outcome: ProgressPipelineOutcome
    resolution: ResolutionResult
    assessment: ProgressAssessment | None = None
    suggestion: AISuggestion | None = None
    explanation: str


class ProgressIntelligenceService:
    """Resolve Evidence, assess progress, and persist a reviewable suggestion."""

    def __init__(
        self,
        session: Session,
        *,
        classifier: ActionItemProgressClassifier | None = None,
    ) -> None:
        self.session = session
        self.repository = ProjectMemoryRepository(session)
        self.memory = ProjectMemoryService(session)
        self.resolution = ProjectMemoryResolutionService(session)
        self.classifier = classifier or ActionItemProgressClassifier()

    def analyze_evidence(
        self,
        tenant_id: UUID,
        evidence: Evidence,
        *,
        context: ResolutionContext | None = None,
    ) -> ProgressIntelligenceResult:
        resolution = self.resolution.resolve_evidence_to_action_items(
            tenant_id,
            evidence,
            context=context,
        )

        if resolution.outcome == ResolutionOutcome.NO_MATCH:
            return ProgressIntelligenceResult(
                outcome=ProgressPipelineOutcome.NO_ENTITY_MATCH,
                resolution=resolution,
                explanation=(
                    "Evidence could not be linked to an existing open Action Item. "
                    "No progress suggestion was created."
                ),
            )

        if resolution.outcome == ResolutionOutcome.NEEDS_REVIEW:
            return ProgressIntelligenceResult(
                outcome=ProgressPipelineOutcome.ENTITY_REVIEW_REQUIRED,
                resolution=resolution,
                explanation=(
                    "Entity resolution is ambiguous. The Action Item must be "
                    "confirmed before progress intelligence can propose a change."
                ),
            )

        assert resolution.best_candidate is not None
        action = self.repository.get_action_item(
            tenant_id, resolution.best_candidate.entity_id
        )
        if action is None:
            raise LookupError("Resolved Action Item is no longer available")

        assessment = self.classifier.assess(action, evidence)

        if assessment.outcome == ProgressOutcome.NO_SIGNAL:
            return ProgressIntelligenceResult(
                outcome=ProgressPipelineOutcome.NO_PROGRESS_SIGNAL,
                resolution=resolution,
                assessment=assessment,
                explanation=(
                    "Evidence was linked to an Action Item, but no explicit V0 "
                    "progress signal was found. No suggestion was created."
                ),
            )

        if assessment.outcome == ProgressOutcome.AMBIGUOUS:
            return ProgressIntelligenceResult(
                outcome=ProgressPipelineOutcome.AMBIGUOUS_PROGRESS,
                resolution=resolution,
                assessment=assessment,
                explanation=(
                    "Evidence contains conflicting progress signals. PMWizard "
                    "will not propose a governed-state update automatically."
                ),
            )

        proposed_changes = {
            "progress_summary": assessment.progress_summary,
            "last_progress_date": (
                evidence.effective_at or evidence.captured_at
            ).isoformat(),
            "latest_evidence_id": str(evidence.id),
        }
        if assessment.suggested_status is not None:
            proposed_changes["status"] = assessment.suggested_status.value

        suggestion = AISuggestion(
            project_id=evidence.project_id,
            suggestion_type=SuggestionType.ACTION_PROGRESS,
            target_entity_type="ActionItem",
            target_entity_id=action.id,
            proposed_changes=proposed_changes,
            reason=assessment.reason,
            evidence_ids=[evidence.id],
            confidence=assessment.confidence,
            model_provider="deterministic",
            model_name="progress-intelligence-v0",
        )

        persisted = self.memory.add_ai_suggestion(tenant_id, suggestion)

        return ProgressIntelligenceResult(
            outcome=ProgressPipelineOutcome.SUGGESTION_CREATED,
            resolution=resolution,
            assessment=assessment,
            suggestion=persisted,
            explanation=(
                "An evidence-backed Action Item progress suggestion was created. "
                "Governed state remains unchanged until Human Review."
            ),
        )
