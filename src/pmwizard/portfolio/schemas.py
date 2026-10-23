"""Program and Portfolio Intelligence V0 schemas."""

from __future__ import annotations

from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from pmwizard.health import HealthBand, TrendDirection


class RollupSummary(BaseModel):
    model_config = ConfigDict(extra="forbid")

    projects_total: int
    projects_scored: int
    score: int | None = Field(default=None, ge=0, le=100)
    band: HealthBand
    average_coverage_percent: int = Field(ge=0, le=100)
    green: int
    amber: int
    red: int
    insufficient_data: int
    improving: int
    stable: int
    deteriorating: int
    insufficient_history: int


class ProjectRollupItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    project_id: UUID
    name: str
    status: str | None = None
    priority: str | None = None
    program_id: UUID | None = None
    program_name: str | None = None
    portfolio_id: UUID | None = None
    portfolio_name: str | None = None
    health_score: int | None = Field(default=None, ge=0, le=100)
    health_band: HealthBand
    health_coverage_percent: int = Field(ge=0, le=100)
    trend_direction: TrendDirection
    trend_score_delta: int | None = None
    top_drivers: list[str] = Field(default_factory=list)


class ProgramRollup(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: UUID
    name: str
    description: str | None = None
    status: str | None = None
    portfolio_id: UUID | None = None
    portfolio_name: str | None = None
    summary: RollupSummary
    projects: list[ProjectRollupItem]


class PortfolioRollup(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: UUID
    name: str
    description: str | None = None
    status: str | None = None
    strategic_objectives: list[str] = Field(default_factory=list)
    summary: RollupSummary
    programs: list[ProgramRollup]
    direct_projects: list[ProjectRollupItem]


class CrossProjectSignal(BaseModel):
    model_config = ConfigDict(extra="forbid")

    signal_type: Literal["risk", "dependency"]
    title: str
    project_count: int
    project_ids: list[UUID]
    project_names: list[str]
    statuses: list[str]
    severity_labels: list[str] = Field(default_factory=list)
    explanation: str


class ProgramPortfolioOverview(BaseModel):
    model_config = ConfigDict(extra="forbid")

    summary: RollupSummary
    portfolios: list[PortfolioRollup]
    standalone_programs: list[ProgramRollup]
    standalone_projects: list[ProjectRollupItem]
    attention_projects: list[ProjectRollupItem]
    cross_project_signals: list[CrossProjectSignal]
