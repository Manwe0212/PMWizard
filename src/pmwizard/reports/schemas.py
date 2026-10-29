"""Grounded AI Status Report V0 schemas."""

from __future__ import annotations

from datetime import date, datetime
from enum import StrEnum
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from pmwizard.health import HealthBand, TrendDirection


class StatusReportAudience(StrEnum):
    EXECUTIVE = "executive"
    PROJECT_TEAM = "project_team"


class StatusReportRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    lookback_days: int = Field(default=7, ge=1, le=31)
    audience: StatusReportAudience = StatusReportAudience.EXECUTIVE


class GroundFact(BaseModel):
    model_config = ConfigDict(extra="forbid")

    fact_id: str
    category: str
    text: str
    entity_type: str | None = None
    entity_id: UUID | None = None
    evidence_ids: list[UUID] = Field(default_factory=list)
    observed_at: datetime | None = None


class StatusReportGroundingPacket(BaseModel):
    model_config = ConfigDict(extra="forbid")

    project_id: UUID
    project_name: str
    period_start: date
    period_end: date
    health_score: int | None = Field(default=None, ge=0, le=100)
    health_band: HealthBand
    health_coverage_percent: int = Field(ge=0, le=100)
    trend_direction: TrendDirection
    trend_score_delta: int | None = None
    facts: list[GroundFact]


class ReportStatement(BaseModel):
    model_config = ConfigDict(extra="forbid")

    text: str = Field(min_length=1, max_length=600)
    fact_ids: list[str] = Field(min_length=1, max_length=8)


class StatusReportContent(BaseModel):
    model_config = ConfigDict(extra="forbid")

    executive_summary: list[ReportStatement] = Field(default_factory=list, max_length=5)
    accomplishments: list[ReportStatement] = Field(default_factory=list, max_length=8)
    risks_and_issues: list[ReportStatement] = Field(default_factory=list, max_length=8)
    decisions_needed: list[ReportStatement] = Field(default_factory=list, max_length=6)
    next_steps: list[ReportStatement] = Field(default_factory=list, max_length=8)
    data_quality_notes: list[ReportStatement] = Field(default_factory=list, max_length=4)


class StatusReportValidation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    grounded: bool
    statement_count: int
    cited_fact_count: int
    available_fact_count: int


class StatusReportDraft(BaseModel):
    model_config = ConfigDict(extra="forbid")

    project_id: UUID
    project_name: str
    title: str
    audience: StatusReportAudience
    period_start: date
    period_end: date
    generated_at: datetime
    provider: str
    model: str
    health_score: int | None = Field(default=None, ge=0, le=100)
    health_band: HealthBand
    health_coverage_percent: int = Field(ge=0, le=100)
    trend_direction: TrendDirection
    trend_score_delta: int | None = None
    content: StatusReportContent
    facts: list[GroundFact]
    validation: StatusReportValidation
    disclaimer: str = (
        "AI-generated draft. Facts are grounded in authorized PMWizard state; "
        "wording still requires human review before distribution."
    )
