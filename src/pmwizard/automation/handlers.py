"""Built-in Automation V0 task handlers."""

from __future__ import annotations

from sqlalchemy.orm import Session

from pmwizard.health import ProjectHealthHistoryService

from .contracts import AutomationClaim
from .schemas import AutomationTaskType


class HealthSnapshotAutomationHandler:
    task_type = AutomationTaskType.HEALTH_SNAPSHOT

    def execute(
        self,
        *,
        session: Session,
        claim: AutomationClaim,
    ) -> dict:
        result = ProjectHealthHistoryService(session).capture(
            tenant_id=claim.tenant_id,
            project_id=claim.project_id,
            captured_by=None,
            capture_source="automation",
        )
        snapshot = result.snapshot
        return {
            "created": result.created,
            "snapshot_id": str(snapshot.id),
            "score": snapshot.score,
            "band": snapshot.band.value,
            "coverage_percent": snapshot.coverage_percent,
            "captured_at": snapshot.captured_at.isoformat(),
        }
