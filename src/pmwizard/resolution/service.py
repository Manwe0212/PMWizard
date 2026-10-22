"""Bridge Project Memory with deterministic entity resolution."""

from uuid import UUID

from sqlalchemy.orm import Session

from pmwizard.models import Evidence
from pmwizard.persistence.repositories import ProjectMemoryRepository

from .engine import ActionItemResolver
from .models import ResolutionContext, ResolutionResult


class ProjectMemoryResolutionService:
    """Load tenant/project-scoped candidates without persisting resolution.

    The caller supplies a trusted tenant ID and authorizes user/project access
    and source evidence permissions before invoking this service.
    """

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
