"""Authenticated, tenant-scoped project creation with atomic creator membership.

Existing account holders can start their own project. This deliberately does
not implement user registration, invitations, or tenant-wide admin privileges.
"""

from __future__ import annotations

from datetime import date
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
from sqlalchemy.orm import Session

from pmwizard.auth import AuthRepository
from pmwizard.auth.models import ProjectAccess
from pmwizard.models import Project
from pmwizard.persistence.orm import AuditLogORM
from pmwizard.persistence.repositories import ProjectMemoryRepository


CREATOR_PERMISSIONS = ("project:read", "project:review")


class CreateProjectRequest(BaseModel):
    """Allowlisted fields only; client cannot choose tenant, owner or privileges."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    name: str = Field(min_length=3, max_length=120)
    description: str | None = Field(default=None, max_length=1000)
    objective: str | None = Field(default=None, max_length=500)
    methodology: Literal["agile", "waterfall", "hybrid", "other"] | None = None
    start_date: date | None = None
    planned_end_date: date | None = None

    @field_validator("name")
    @classmethod
    def name_must_have_content(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("Project name is required")
        return value.strip()

    @model_validator(mode="after")
    def dates_must_be_ordered(self) -> "CreateProjectRequest":
        if (
            self.start_date is not None
            and self.planned_end_date is not None
            and self.planned_end_date < self.start_date
        ):
            raise ValueError("planned_end_date cannot be before start_date")
        return self


class ProjectOnboardingService:
    """Create the governed project, membership and audit event as one unit."""

    def __init__(self, session: Session) -> None:
        self.session = session

    def create(
        self,
        *,
        tenant_id: UUID,
        actor_id: UUID,
        command: CreateProjectRequest,
    ) -> ProjectAccess:
        repository = AuthRepository(self.session)
        user = repository.get_user(tenant_id, actor_id)
        if user is None or not user.is_active:
            raise PermissionError("Active account required")

        project = Project(
            name=command.name,
            description=command.description,
            objective=command.objective,
            methodology=command.methodology,
            start_date=command.start_date,
            planned_end_date=command.planned_end_date,
            project_manager_id=actor_id,
            lifecycle_phase="initiation",
            status="planning",
        )

        try:
            ProjectMemoryRepository(self.session).add_project(tenant_id, project)
            repository.add_project_membership(
                tenant_id=tenant_id,
                user_id=actor_id,
                project_id=project.id,
                role="project_manager",
                permissions=list(CREATOR_PERMISSIONS),
            )
            self.session.add(
                AuditLogORM(
                    tenant_id=tenant_id,
                    project_id=project.id,
                    actor_id=actor_id,
                    action="project_created",
                    entity_type="Project",
                    entity_id=project.id,
                    previous_state=None,
                    proposed_state=None,
                    final_state={"status": "planning"},
                    evidence_ids=[],
                )
            )
            self.session.commit()
        except Exception:
            self.session.rollback()
            raise

        return ProjectAccess(
            project_id=project.id,
            name=project.name,
            status=project.status,
            role="project_manager",
            permissions=list(CREATOR_PERMISSIONS),
        )
