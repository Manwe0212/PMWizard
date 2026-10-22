"""Project Inbox view models."""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from pmwizard.models import ActionItem
from pmwizard.models.enums import ReviewStatus, SuggestionType


class InboxEvidenceView(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: UUID
    source_type: str
    source_system: str | None = None
    source_reference: str | None = None
    author: str | None = None
    captured_at: datetime
    content_excerpt: str | None = None
    permission_scope: list[str] = Field(default_factory=list)


class InboxSuggestionSummary(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: UUID
    project_id: UUID
    suggestion_type: SuggestionType
    target_entity_type: str | None = None
    target_entity_id: UUID | None = None
    proposed_changes: dict[str, Any] = Field(default_factory=dict)
    reason: str
    confidence: float
    review_status: ReviewStatus
    evidence_count: int
    evidence_sources: list[str] = Field(default_factory=list)
    created_at: datetime


class InboxSuggestionDetail(BaseModel):
    model_config = ConfigDict(extra="forbid")

    suggestion: InboxSuggestionSummary
    target_action_item: ActionItem | None = None
    evidence: list[InboxEvidenceView] = Field(default_factory=list)


class InboxListResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    project_id: UUID
    count: int
    items: list[InboxSuggestionSummary]


class ReviewCommand(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: ReviewStatus
    reviewer_note: str | None = None
    final_changes: dict[str, Any] = Field(default_factory=dict)


class ReviewResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    suggestion_id: UUID
    review_status: ReviewStatus
    updated_action_item: ActionItem | None = None
