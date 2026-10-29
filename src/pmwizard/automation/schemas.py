"""Automation & Scheduler V0 schemas."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class AutomationTaskType(StrEnum):
    HEALTH_SNAPSHOT = "health_snapshot"
    SOURCE_SYNC = "source_sync"


class AutomationRunStatus(StrEnum):
    RUNNING = "running"
    SUCCESS = "success"
    FAILED = "failed"
    ABANDONED = "abandoned"


class AutomationTrigger(StrEnum):
    SCHEDULED = "scheduled"
    MANUAL = "manual"


class CreateAutomationScheduleRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=255)
    task_type: AutomationTaskType = AutomationTaskType.HEALTH_SNAPSHOT
    interval_minutes: int = Field(default=1440, ge=5, le=10080)
    enabled: bool = True
    start_at: datetime | None = None
    config: dict = Field(default_factory=dict)


class UpdateAutomationScheduleRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str | None = Field(default=None, min_length=1, max_length=255)
    interval_minutes: int | None = Field(default=None, ge=5, le=10080)
    enabled: bool | None = None


class AutomationRunView(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: UUID
    schedule_id: UUID
    project_id: UUID
    task_type: AutomationTaskType
    trigger: AutomationTrigger
    status: AutomationRunStatus
    worker_id: str
    scheduled_for: datetime
    started_at: datetime
    finished_at: datetime | None = None
    summary: dict = Field(default_factory=dict)
    error_message: str | None = None


class AutomationScheduleView(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: UUID
    project_id: UUID
    name: str
    task_type: AutomationTaskType
    interval_minutes: int
    enabled: bool
    config: dict = Field(default_factory=dict)
    next_run_at: datetime
    pending_trigger: AutomationTrigger
    last_run_at: datetime | None = None
    last_status: AutomationRunStatus | None = None
    consecutive_failures: int = 0
    created_by: UUID | None = None
    running: bool = False
    created_at: datetime
    updated_at: datetime
    recent_runs: list[AutomationRunView] = Field(default_factory=list)


class AutomationsSummary(BaseModel):
    model_config = ConfigDict(extra="forbid")

    total: int
    enabled: int
    running: int
    failing: int
    due_now: int


class AutomationsWorkspaceSnapshot(BaseModel):
    model_config = ConfigDict(extra="forbid")

    project_id: UUID
    generated_at: datetime
    summary: AutomationsSummary
    schedules: list[AutomationScheduleView]


class RunNowResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schedule_id: UUID
    queued: bool = True
    next_run_at: datetime
