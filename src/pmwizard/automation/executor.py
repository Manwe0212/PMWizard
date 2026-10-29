"""Automation task execution over claimed durable schedules."""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy.orm import Session

from .contracts import AutomationClaim, AutomationHandler
from .repository import AutomationRepository
from .schemas import AutomationRunStatus, AutomationTaskType


class AutomationExecutor:
    def __init__(
        self,
        session: Session,
        handlers: list[AutomationHandler],
    ) -> None:
        self.session = session
        self.repository = AutomationRepository(session)
        self.handlers = {
            handler.task_type: handler
            for handler in handlers
        }

    def execute(
        self,
        *,
        claim: AutomationClaim,
        worker_id: str,
        now: datetime | None = None,
    ):
        started_at = now or datetime.now(timezone.utc)
        try:
            run = self.repository.start_run(
                claim=claim,
                worker_id=worker_id,
                now=started_at,
            )
        except Exception as exc:
            self.session.rollback()
            self.repository.release_claim_after_start_failure(
                claim=claim,
                now=datetime.now(timezone.utc),
                error_message=f"{type(exc).__name__}: {exc}",
            )
            raise

        handler = self.handlers.get(claim.task_type)
        if handler is None:
            return self.repository.finish_run(
                claim=claim,
                run_id=run.id,
                status=AutomationRunStatus.FAILED,
                now=datetime.now(timezone.utc),
                error_message=(
                    "No automation handler is registered for "
                    f"{claim.task_type.value}."
                ),
            )

        try:
            summary = handler.execute(
                session=self.session,
                claim=claim,
            )
        except Exception as exc:
            self.session.rollback()
            return self.repository.finish_run(
                claim=claim,
                run_id=run.id,
                status=AutomationRunStatus.FAILED,
                now=datetime.now(timezone.utc),
                error_message=f"{type(exc).__name__}: {exc}",
            )

        return self.repository.finish_run(
            claim=claim,
            run_id=run.id,
            status=AutomationRunStatus.SUCCESS,
            now=datetime.now(timezone.utc),
            summary=summary,
        )
