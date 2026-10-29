"""Executive Dashboard V0 schemas."""

from __future__ import annotations

from datetime import date, datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from pmwizard.health import HealthBand
from pmwizard.models.enums import ReviewStatus, SuggestionType
from pmwizard.portfolio import CrossProjectSignal, ProjectRollupItem, RollupSummary
from pmwizard.sources import SourceHealthStatus


class ExecutiveSummary(BaseModel):
    model_config = ConfigDict(extra="forbid")

    health: RollupSummary
    projects_needing_attention: int
    pending_inbox: int
    deferred_inbox: int
    critical_raid: int
    pending_decisions: int
    source_failures: int
    source_attention: int
    cross_project_signals: int


class ExecutiveInboxItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    suggestion_id: UUID
    project_id: UUID
    project_name: str
    suggestion_type: SuggestionType
    review_status: ReviewStatus
    reason: str
    confidence: float
    created_at: datetime


class ExecutiveRAIDItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    entity_type: Literal["Risk", "Assumption", "Issue", "Dependency"]
    entity_id: UUID
    project_id: UUID
    project_name: str
    title: str
    status: str
    severity: str
    due_date: date | None = None
    reason: str


class ExecutiveDecisionItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    decision_id: UUID
    project_id: UUID
    project_name: str
    title: str
    status: str
    review_date: date | None = None
    expected_impact: str | None = None


class ExecutiveSourceAlert(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source_id: UUID
    project_id: UUID
    project_name: str
    display_name: str
    source_system: str
    health: SourceHealthStatus
    latest_status: str | None = None
    latest_finished_at: datetime | None = None
    error_count: int = 0
    skipped: int = 0


class ExecutiveDashboardSnapshot(BaseModel):
    model_config = ConfigDict(extra="forbid")

    generated_at: datetime
    summary: ExecutiveSummary
    attention_projects: list[ProjectRollupItem]
    inbox_items: list[ExecutiveInboxItem]
    critical_raid: list[ExecutiveRAIDItem]
    pending_decisions: list[ExecutiveDecisionItem]
    source_alerts: list[ExecutiveSourceAlert]
    cross_project_signals: list[CrossProjectSignal]
