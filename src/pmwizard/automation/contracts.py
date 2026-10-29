"""Internal automation execution contracts."""

from __future__ import annotations

from typing import Protocol
from uuid import UUID

from sqlalchemy.orm import Session

from .schemas import AutomationTaskType, AutomationTrigger


class AutomationClaim:
    def __init__(
        self,
        *,
        schedule_id: UUID,
        tenant_id: UUID,
        project_id: UUID,
        task_type: AutomationTaskType,
        trigger: AutomationTrigger,
        scheduled_for,
        interval_minutes: int,
        config: dict,
        lease_token: str,
    ) -> None:
        self.schedule_id = schedule_id
        self.tenant_id = tenant_id
        self.project_id = project_id
        self.task_type = task_type
        self.trigger = trigger
        self.scheduled_for = scheduled_for
        self.interval_minutes = interval_minutes
        self.config = config
        self.lease_token = lease_token


class AutomationHandler(Protocol):
    task_type: AutomationTaskType

    def execute(
        self,
        *,
        session: Session,
        claim: AutomationClaim,
    ) -> dict: ...
