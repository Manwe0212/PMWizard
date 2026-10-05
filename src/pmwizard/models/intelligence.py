"""AI suggestion and human-review models.

AI suggestions are intentionally separated from governed project state.
"""

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import Field

from .base import ProjectScopedEntity
from .enums import ReviewStatus, SuggestionType


class AISuggestion(ProjectScopedEntity):
    suggestion_type: SuggestionType
    target_entity_type: str | None = None
    target_entity_id: UUID | None = None

    proposed_changes: dict[str, Any] = Field(default_factory=dict)
    reason: str = Field(min_length=1)
    evidence_ids: list[UUID] = Field(default_factory=list)
    confidence: float = Field(ge=0.0, le=1.0)

    review_status: ReviewStatus = ReviewStatus.PENDING
    model_provider: str | None = None
    model_name: str | None = None


class HumanReview(ProjectScopedEntity):
    suggestion_id: UUID
    reviewer_id: UUID
    status: ReviewStatus

    reviewed_at: datetime
    reviewer_note: str | None = None
    final_changes: dict[str, Any] = Field(default_factory=dict)
