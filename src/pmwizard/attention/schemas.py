"""Project Attention Center V0 schemas."""

from __future__ import annotations

from datetime import date, datetime
from enum import StrEnum
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class AttentionSeverity(StrEnum):
    CRITICAL = "critical"
    WARNING = "warning"
    INFO = "info"


class AttentionCategory(StrEnum):
    HEALTH = "health"
    EXECUTION = "execution"
    RAID = "raid"
    DECISION = "decision"
    SOURCE = "source"
    AUTOMATION = "automation"
    REVIEW = "review"


class AttentionUserState(StrEnum):
    UNREAD = "unread"
    SEEN = "seen"
    ACKNOWLEDGED = "acknowledged"
    SNOOZED = "snoozed"


class AttentionSignalView(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    signal_key: str
    category: AttentionCategory
    severity: AttentionSeverity
    title: str
    detail: str
    target_view: str
    action_label: str
    entity_type: str | None = None
    entity_id: UUID | None = None
    due_date: date | None = None
    observed_at: datetime | None = None
    state: AttentionUserState = AttentionUserState.UNREAD
    snoozed_until: datetime | None = None


class AttentionSummary(BaseModel):
    model_config = ConfigDict(extra="forbid")

    active: int
    unread: int
    critical: int
    warning: int
    info: int
    acknowledged: int
    snoozed: int


class AttentionCenterSnapshot(BaseModel):
    model_config = ConfigDict(extra="forbid")

    project_id: UUID
    generated_at: datetime
    summary: AttentionSummary
    signals: list[AttentionSignalView] = Field(default_factory=list)


class AttentionStateCommand(BaseModel):
    model_config = ConfigDict(extra="forbid")

    action: Literal["seen", "acknowledge", "snooze", "reset"]
    snoozed_until: datetime | None = None


class AttentionStateResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    signal: AttentionSignalView
