"""Durable persistence primitives for Automation & Scheduler V0."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import UUID, uuid4

from sqlalchemy import or_, select, update
from sqlalchemy.orm import Session

from pmwizard.persistence.orm import (
    AutomationRunORM,
    AutomationScheduleORM,
    ProjectORM,
)

from .contracts import AutomationClaim
from .schemas import (
    AutomationRunStatus,
    AutomationRunView,
    AutomationTaskType,
    AutomationTrigger,
)


class AutomationRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def require_project(self, tenant_id: UUID, project_id: UUID) -> None:
        exists = self.session.scalar(
            select(ProjectORM.id).where(
                ProjectORM.tenant_id == tenant_id,
                ProjectORM.id == project_id,
            )
        )
        if exists is None:
            raise LookupError("Project not found for tenant")

    def create_schedule(
        self,
        *,
        tenant_id: UUID,
        project_id: UUID,
        name: str,
        task_type: AutomationTaskType,
        interval_minutes: int,
        enabled: bool,
        config: dict,
        next_run_at: datetime,
        created_by: UUID | None,
    ) -> AutomationScheduleORM:
        self.require_project(tenant_id, project_id)
        row = AutomationScheduleORM(
            id=uuid4(),
            tenant_id=tenant_id,
            project_id=project_id,
            task_type=task_type.value,
            name=name.strip(),
            interval_minutes=interval_minutes,
            is_enabled=enabled,
            config=config,
            next_run_at=next_run_at,
            pending_trigger=AutomationTrigger.SCHEDULED.value,
            consecutive_failures=0,
            created_by=created_by,
        )
        self.session.add(row)
        self.session.flush()
        return row

    def get_schedule(
        self,
        *,
        tenant_id: UUID,
        project_id: UUID,
        schedule_id: UUID,
    ) -> AutomationScheduleORM | None:
        return self.session.scalar(
            select(AutomationScheduleORM).where(
                AutomationScheduleORM.tenant_id == tenant_id,
                AutomationScheduleORM.project_id == project_id,
                AutomationScheduleORM.id == schedule_id,
            )
        )

    def list_schedules(
        self,
        *,
        tenant_id: UUID,
        project_id: UUID,
    ) -> list[AutomationScheduleORM]:
        self.require_project(tenant_id, project_id)
        return list(
            self.session.scalars(
                select(AutomationScheduleORM)
                .where(
                    AutomationScheduleORM.tenant_id == tenant_id,
                    AutomationScheduleORM.project_id == project_id,
                )
                .order_by(
                    AutomationScheduleORM.name,
                    AutomationScheduleORM.id,
                )
            ).all()
        )

    def list_runs(
        self,
        *,
        tenant_id: UUID,
        project_id: UUID,
        schedule_id: UUID,
        limit: int = 5,
    ) -> list[AutomationRunORM]:
        return list(
            self.session.scalars(
                select(AutomationRunORM)
                .where(
                    AutomationRunORM.tenant_id == tenant_id,
                    AutomationRunORM.project_id == project_id,
                    AutomationRunORM.schedule_id == schedule_id,
                )
                .order_by(
                    AutomationRunORM.started_at.desc(),
                    AutomationRunORM.created_at.desc(),
                )
                .limit(limit)
            ).all()
        )

    def claim_due(
        self,
        *,
        worker_id: str,
        now: datetime,
        lease_seconds: int,
        limit: int,
    ) -> list[AutomationClaim]:
        if limit < 1:
            return []

        candidate_ids = list(
            self.session.scalars(
                select(AutomationScheduleORM.id)
                .where(
                    AutomationScheduleORM.is_enabled.is_(True),
                    AutomationScheduleORM.next_run_at <= now,
                    or_(
                        AutomationScheduleORM.lease_expires_at.is_(None),
                        AutomationScheduleORM.lease_expires_at <= now,
                    ),
                )
                .order_by(
                    AutomationScheduleORM.next_run_at,
                    AutomationScheduleORM.id,
                )
                .limit(limit)
            ).all()
        )

        claims: list[AutomationClaim] = []
        for schedule_id in candidate_ids:
            lease_token = f"{worker_id}:{uuid4()}"
            expires_at = now + timedelta(seconds=lease_seconds)
            result = self.session.execute(
                update(AutomationScheduleORM)
                .where(
                    AutomationScheduleORM.id == schedule_id,
                    AutomationScheduleORM.is_enabled.is_(True),
                    AutomationScheduleORM.next_run_at <= now,
                    or_(
                        AutomationScheduleORM.lease_expires_at.is_(None),
                        AutomationScheduleORM.lease_expires_at <= now,
                    ),
                )
                .values(
                    lease_owner=lease_token,
                    lease_expires_at=expires_at,
                    updated_at=now,
                )
            )
            self.session.commit()

            if result.rowcount != 1:
                continue

            row = self.session.get(AutomationScheduleORM, schedule_id)
            if row is None:
                continue

            self._abandon_stale_runs(
                schedule_id=schedule_id,
                now=now,
            )
            self.session.commit()

            claims.append(
                AutomationClaim(
                    schedule_id=row.id,
                    tenant_id=row.tenant_id,
                    project_id=row.project_id,
                    task_type=AutomationTaskType(row.task_type),
                    trigger=AutomationTrigger(row.pending_trigger),
                    scheduled_for=self._aware(row.next_run_at),
                    interval_minutes=row.interval_minutes,
                    config=row.config,
                    lease_token=lease_token,
                )
            )

        return claims

    def start_run(
        self,
        *,
        claim: AutomationClaim,
        worker_id: str,
        now: datetime,
    ) -> AutomationRunORM:
        row = AutomationRunORM(
            id=uuid4(),
            tenant_id=claim.tenant_id,
            schedule_id=claim.schedule_id,
            project_id=claim.project_id,
            task_type=claim.task_type.value,
            trigger=claim.trigger.value,
            status=AutomationRunStatus.RUNNING.value,
            worker_id=worker_id,
            scheduled_for=claim.scheduled_for,
            started_at=now,
            summary={},
        )
        self.session.add(row)
        self.session.commit()
        self.session.refresh(row)
        return row

    def finish_run(
        self,
        *,
        claim: AutomationClaim,
        run_id: UUID,
        status: AutomationRunStatus,
        now: datetime,
        summary: dict | None = None,
        error_message: str | None = None,
    ) -> AutomationRunORM:
        run = self.session.get(AutomationRunORM, run_id)
        if run is None:
            raise LookupError("Automation run not found")

        schedule = self.session.get(AutomationScheduleORM, claim.schedule_id)
        if schedule is None:
            raise LookupError("Automation schedule not found")

        if schedule.lease_owner != claim.lease_token:
            raise RuntimeError(
                "Automation lease was lost before the run could be finalized"
            )

        run.status = status.value
        run.finished_at = now
        run.summary = summary or {}
        run.error_message = self._sanitize_error(error_message)

        schedule.last_run_at = now
        schedule.last_status = status.value
        schedule.consecutive_failures = (
            0
            if status == AutomationRunStatus.SUCCESS
            else schedule.consecutive_failures + 1
        )
        schedule.next_run_at = now + timedelta(
            minutes=schedule.interval_minutes
        )
        schedule.pending_trigger = AutomationTrigger.SCHEDULED.value
        schedule.lease_owner = None
        schedule.lease_expires_at = None
        schedule.updated_at = now

        self.session.commit()
        self.session.refresh(run)
        return run

    def release_claim_after_start_failure(
        self,
        *,
        claim: AutomationClaim,
        now: datetime,
        error_message: str,
    ) -> None:
        schedule = self.session.get(
            AutomationScheduleORM,
            claim.schedule_id,
        )
        if schedule is None or schedule.lease_owner != claim.lease_token:
            return
        schedule.last_run_at = now
        schedule.last_status = AutomationRunStatus.FAILED.value
        schedule.consecutive_failures += 1
        schedule.next_run_at = now + timedelta(
            minutes=schedule.interval_minutes
        )
        schedule.pending_trigger = AutomationTrigger.SCHEDULED.value
        schedule.lease_owner = None
        schedule.lease_expires_at = None
        schedule.updated_at = now
        self.session.commit()

    def _abandon_stale_runs(
        self,
        *,
        schedule_id: UUID,
        now: datetime,
    ) -> None:
        rows = list(
            self.session.scalars(
                select(AutomationRunORM).where(
                    AutomationRunORM.schedule_id == schedule_id,
                    AutomationRunORM.status
                    == AutomationRunStatus.RUNNING.value,
                    AutomationRunORM.finished_at.is_(None),
                )
            ).all()
        )
        for row in rows:
            row.status = AutomationRunStatus.ABANDONED.value
            row.finished_at = now
            row.error_message = (
                "Previous worker lease expired before completion."
            )

    @staticmethod
    def run_view(row: AutomationRunORM) -> AutomationRunView:
        return AutomationRunView(
            id=row.id,
            schedule_id=row.schedule_id,
            project_id=row.project_id,
            task_type=row.task_type,
            trigger=row.trigger,
            status=row.status,
            worker_id=row.worker_id,
            scheduled_for=row.scheduled_for,
            started_at=row.started_at,
            finished_at=row.finished_at,
            summary=row.summary,
            error_message=row.error_message,
        )

    @staticmethod
    def _aware(value: datetime) -> datetime:
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value

    @staticmethod
    def _sanitize_error(value: str | None) -> str | None:
        if value is None:
            return None
        return value.replace("\x00", "").strip()[:1000]
