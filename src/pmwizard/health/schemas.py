"""Explainable Project Health V0 schemas."""

from __future__ import annotations

from datetime import date
from enum import StrEnum
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class HealthBand(StrEnum):
    GREEN = "green"
    AMBER = "amber"
    RED = "red"
    INSUFFICIENT_DATA = "insufficient_data"


class CoverageBand(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class SignalSeverity(StrEnum):
    POSITIVE = "positive"
    INFO = "info"
    WARNING = "warning"
    CRITICAL = "critical"


class HealthSignal(BaseModel):
    model_config = ConfigDict(extra="forbid")

    severity: SignalSeverity
    title: str
    detail: str
    penalty: int = Field(default=0, ge=0, le=100)
    entity_type: str | None = None
    entity_ids: list[UUID] = Field(default_factory=list)


class HealthFactor(BaseModel):
    model_config = ConfigDict(extra="forbid")

    key: str
    name: str
    weight: int = Field(ge=0, le=100)
    available: bool
    score: int | None = Field(default=None, ge=0, le=100)
    band: HealthBand
    signals: list[HealthSignal] = Field(default_factory=list)


class ProjectHealthSnapshot(BaseModel):
    model_config = ConfigDict(extra="forbid")

    project_id: UUID
    project_name: str
    assessed_on: date
    score: int | None = Field(default=None, ge=0, le=100)
    band: HealthBand
    coverage_percent: int = Field(ge=0, le=100)
    coverage_band: CoverageBand
    available_weight: int = Field(ge=0, le=100)
    explanation: str
    factors: list[HealthFactor]
    key_drivers: list[HealthSignal] = Field(default_factory=list)
