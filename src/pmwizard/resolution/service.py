"""Bridge Project Memory with deterministic entity resolution."""

from uuid import UUID

from sqlalchemy.orm import Session

from pmwizard.models import Evidence
from pmwizard.persistence.repositories import ProjectMemoryRepository

from .engine import ActionItemResolver
from .models import ResolutionContext, ResolutionResult


class ProjectMemoryResolutionService:
    """Resolve evidence only against authorized tenant/project memory."""

    def __init__(
        self,
        session: Session,
        resolver: ActionItemResolver | None = None,
    ) -> None:
        self.repository = ProjectMemoryRepository(session)
        self.resolver = resolver or ActionItemResolver()

    def resolve_evidence_to_action_items(
        self,
        tenant_id: UUID,
        evidence: Evidence,
        *,
        context: ResolutionContext | None = None,
    ) -> ResolutionResult:
        project = self.repository.get_project(tenant_id, evidence.project_id)
        if project is None:
            raise LookupError("Project not found for tenant")

        action_items = self.repository.get_open_action_items(
            tenant_id, evidence.project_id
        )
        return self.resolver.resolve(
            evidence,
            action_items,
            context=context,
        )
