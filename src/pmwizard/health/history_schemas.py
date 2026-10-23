"""Persisted Project Health history and trend schemas."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from .schemas import CoverageBand, HealthBand, HealthSignal


class TrendDirection(StrEnum):
    IMPROVING = "improving"
    STABLE = "stable"
    DETERIORATING = "deteriorating"
    INSUFFICIENT_HISTORY = "insufficient_history"


class HealthHistoryPoint(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: UUID
    captured_at: datetime
    captured_by: UUID | None = None
    capture_source: str
    model_version: str
    score: int | None = Field(default=None, ge=0, le=100)
    band: HealthBand
    coverage_percent: int = Field(ge=0, le=100)
    coverage_band: CoverageBand
    factor_scores: dict[str, int | None]
    key_drivers: list[HealthSignal] = Field(default_factory=list)


class HealthSnapshotCaptureResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    created: bool
    snapshot: HealthHistoryPoint


class HealthTrendSummary(BaseModel):
    model_config = ConfigDict(extra="forbid")

    direction: TrendDirection
    from_snapshot_id: UUID | None = None
    to_snapshot_id: UUID | None = None
    score_delta: int | None = None
    coverage_delta: int | None = None
    factor_deltas: dict[str, int] = Field(default_factory=dict)
    new_drivers: list[str] = Field(default_factory=list)
    resolved_drivers: list[str] = Field(default_factory=list)
    elapsed_hours: float | None = None
    explanation: str


class ProjectHealthHistory(BaseModel):
    model_config = ConfigDict(extra="forbid")

    project_id: UUID
    count: int
    points: list[HealthHistoryPoint]
    trend: HealthTrendSummary
