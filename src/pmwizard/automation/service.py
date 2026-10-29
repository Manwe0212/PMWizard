"""Application services for Automation & Scheduler V0."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import UUID

from sqlalchemy.orm import Session

from .repository import AutomationRepository
from .schemas import (
    AutomationRunStatus,
    AutomationScheduleView,
    AutomationsSummary,
    AutomationsWorkspaceSnapshot,
    AutomationTrigger,
    CreateAutomationScheduleRequest,
    RunNowResponse,
    UpdateAutomationScheduleRequest,
)


class AutomationScheduleService:
    def __init__(self, session: Session) -> None:
        self.session = session
        self.repository = AutomationRepository(session)

    def create(
        self,
        *,
        tenant_id: UUID,
        project_id: UUID,
        created_by: UUID | None,
        command: CreateAutomationScheduleRequest,
        now: datetime | None = None,
    ) -> AutomationScheduleView:
        timestamp = self._aware(now or datetime.now(timezone.utc))
        next_run_at = (
            self._aware(command.start_at)
            if command.start_at is not None
            else timestamp + timedelta(minutes=command.interval_minutes)
        )
        row = self.repository.create_schedule(
            tenant_id=tenant_id,
            project_id=project_id,
            name=command.name,
            task_type=command.task_type,
            interval_minutes=command.interval_minutes,
            enabled=command.enabled,
            config=command.config,
            next_run_at=next_run_at,
            created_by=created_by,
        )
        self.session.commit()
        self.session.refresh(row)
        return self._view(row, now=timestamp)

    def update(
        self,
        *,
        tenant_id: UUID,
        project_id: UUID,
        schedule_id: UUID,
        command: UpdateAutomationScheduleRequest,
        now: datetime | None = None,
    ) -> AutomationScheduleView:
        timestamp = self._aware(now or datetime.now(timezone.utc))
        row = self.repository.get_schedule(
            tenant_id=tenant_id,
            project_id=project_id,
            schedule_id=schedule_id,
        )
        if row is None:
            raise LookupError("Automation schedule not found")

        if command.name is not None:
            row.name = command.name.strip()

        interval_changed = command.interval_minutes is not None
        if command.interval_minutes is not None:
            row.interval_minutes = command.interval_minutes

        if command.enabled is not None:
            was_enabled = row.is_enabled
            row.is_enabled = command.enabled
            if command.enabled and not was_enabled:
                row.next_run_at = timestamp + timedelta(
                    minutes=row.interval_minutes
                )
                row.pending_trigger = AutomationTrigger.SCHEDULED.value

        if (
            interval_changed
            and row.pending_trigger != AutomationTrigger.MANUAL.value
        ):
            row.next_run_at = timestamp + timedelta(
                minutes=row.interval_minutes
            )

        row.updated_at = timestamp
        self.session.commit()
        self.session.refresh(row)
        return self._view(row, now=timestamp)

    def run_now(
        self,
        *,
        tenant_id: UUID,
        project_id: UUID,
        schedule_id: UUID,
        now: datetime | None = None,
    ) -> RunNowResponse:
        timestamp = self._aware(now or datetime.now(timezone.utc))
        row = self.repository.get_schedule(
            tenant_id=tenant_id,
            project_id=project_id,
            schedule_id=schedule_id,
        )
        if row is None:
            raise LookupError("Automation schedule not found")

        if self._running(row, timestamp):
            raise ValueError("Automation schedule is currently running")

        if not row.is_enabled:
            raise ValueError(
                "Enable the automation schedule before requesting run now"
            )

        row.next_run_at = timestamp
        row.pending_trigger = AutomationTrigger.MANUAL.value
        row.updated_at = timestamp
        self.session.commit()

        return RunNowResponse(
            schedule_id=row.id,
            queued=True,
            next_run_at=timestamp,
        )

    def snapshot(
        self,
        *,
        tenant_id: UUID,
        project_id: UUID,
        now: datetime | None = None,
    ) -> AutomationsWorkspaceSnapshot:
        timestamp = self._aware(now or datetime.now(timezone.utc))
        rows = self.repository.list_schedules(
            tenant_id=tenant_id,
            project_id=project_id,
        )
        views = [self._view(row, now=timestamp) for row in rows]

        return AutomationsWorkspaceSnapshot(
            project_id=project_id,
            generated_at=timestamp,
            summary=AutomationsSummary(
                total=len(views),
                enabled=sum(item.enabled for item in views),
                running=sum(item.running for item in views),
                failing=sum(
                    item.last_status
                    in {
                        AutomationRunStatus.FAILED,
                        AutomationRunStatus.ABANDONED,
                    }
                    for item in views
                ),
                due_now=sum(
                    item.enabled
                    and not item.running
                    and self._aware(item.next_run_at) <= timestamp
                    for item in views
                ),
            ),
            schedules=views,
        )

    def _view(
        self,
        row,
        *,
        now: datetime,
    ) -> AutomationScheduleView:
        runs = self.repository.list_runs(
            tenant_id=row.tenant_id,
            project_id=row.project_id,
            schedule_id=row.id,
            limit=5,
        )
        return AutomationScheduleView(
            id=row.id,
            project_id=row.project_id,
            name=row.name,
            task_type=row.task_type,
            interval_minutes=row.interval_minutes,
            enabled=row.is_enabled,
            config=row.config,
            next_run_at=self._aware(row.next_run_at),
            pending_trigger=row.pending_trigger,
            last_run_at=(
                self._aware(row.last_run_at)
                if row.last_run_at is not None
                else None
            ),
            last_status=row.last_status,
            consecutive_failures=row.consecutive_failures,
            created_by=row.created_by,
            running=self._running(row, now),
            created_at=self._aware(row.created_at),
            updated_at=self._aware(row.updated_at),
            recent_runs=[
                self.repository.run_view(run)
                for run in runs
            ],
        )

    @classmethod
    def _running(cls, row, now: datetime) -> bool:
        return (
            row.lease_owner is not None
            and row.lease_expires_at is not None
            and cls._aware(row.lease_expires_at) > now
        )

    @staticmethod
    def _aware(value: datetime) -> datetime:
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value
