"""Read-only, deliberately redacted Project Activity contracts."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class ActivityCategory(StrEnum):
    EVENT = "event"
    HUMAN_REVIEW = "human_review"
    AUDIT = "audit"
    SOURCE_RUN = "source_run"
    AUTOMATION_RUN = "automation_run"
    HEALTH_SNAPSHOT = "health_snapshot"


class ActivityItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: UUID
    category: ActivityCategory
    occurred_at: datetime
    actor_kind: Literal["human", "worker", "system"]
    actor_id: UUID | None = None
    action: str
    entity_type: str | None = None
    entity_id: UUID | None = None
    status: str | None = None
    summary: str | None = None
    changed_fields: list[str] = Field(default_factory=list)
    evidence_ids: list[UUID] = Field(default_factory=list)


class ActivityTimeline(BaseModel):
    model_config = ConfigDict(extra="forbid")

    project_id: UUID
    count: int
    items: list[ActivityItem] = Field(default_factory=list)
    next_cursor: str | None = None
