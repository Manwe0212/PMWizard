"""Project Health V0 composition service."""

from __future__ import annotations

from datetime import date, datetime, timezone
from uuid import UUID

from sqlalchemy.orm import Session

from pmwizard.memory import ProjectMemoryQueryService
from pmwizard.sources import SourcesWorkspaceService

from .schemas import ProjectHealthSnapshot
from .scoring import evaluate_project_health


class ProjectHealthService:
    def __init__(self, session: Session) -> None:
        self.session = session

    def snapshot(
        self,
        *,
        tenant_id: UUID,
        project_id: UUID,
        as_of: date | None = None,
    ) -> ProjectHealthSnapshot:
        memory = ProjectMemoryQueryService(self.session).snapshot(
            tenant_id=tenant_id,
            project_id=project_id,
        )
        sources = SourcesWorkspaceService(self.session).snapshot(
            tenant_id=tenant_id,
            project_id=project_id,
        )
        return evaluate_project_health(
            memory,
            sources,
            as_of=as_of or datetime.now(timezone.utc).date(),
        )
