"""Governed, tenant-bound membership management for existing user accounts.

Membership roles are deliberately fixed presets. No arbitrary permissions,
tenant-wide powers, new account registration, or credential access is exposed.
"""

from __future__ import annotations

from datetime import datetime, timezone
from enum import StrEnum
from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from pmwizard.auth import AuthRepository
from pmwizard.persistence.orm import (
    AppUserORM,
    AuditLogORM,
    ProjectMembershipORM,
    ProjectORM,
)


MANAGE_PERMISSION = "project:manage_members"


class ProjectRole(StrEnum):
    VIEWER = "viewer"
    REVIEWER = "reviewer"
    PROJECT_MANAGER = "project_manager"


ROLE_PERMISSIONS: dict[ProjectRole, tuple[str, ...]] = {
    ProjectRole.VIEWER: ("project:read",),
    ProjectRole.REVIEWER: ("project:read", "project:review"),
    ProjectRole.PROJECT_MANAGER: (
        "project:read",
        "project:review",
        MANAGE_PERMISSION,
    ),
}


class AddProjectMemberRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    email: EmailStr
    role: ProjectRole = ProjectRole.VIEWER


class ChangeProjectMemberRoleRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    role: ProjectRole


class MemberView(BaseModel):
    model_config = ConfigDict(extra="forbid")

    user_id: UUID
    email: EmailStr
    display_name: str
    role: ProjectRole
    permissions: list[str]
    is_active: bool
    is_owner: bool = False
    joined_at: datetime


class MembersPage(BaseModel):
    model_config = ConfigDict(extra="forbid")

    project_id: UUID
    items: list[MemberView] = Field(default_factory=list)
    count: int
    next_offset: int | None


def _utc(value: datetime) -> datetime:
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)


class ProjectMemberService:
    """Project-scoped manager operations, audited within one DB transaction."""

    def __init__(self, session: Session) -> None:
        self.session = session
        self.repository = AuthRepository(session)

    def _authorize(
        self,
        tenant_id: UUID,
        project_id: UUID,
        actor_id: UUID,
        *,
        lock: bool = False,
    ) -> ProjectORM:
        query = select(ProjectORM).where(
            ProjectORM.tenant_id == tenant_id,
            ProjectORM.id == project_id,
        )
        if lock:
            query = query.with_for_update()
        project = self.session.scalar(query)
        if project is None:
            raise LookupError("Project not found or not authorized")
        membership = self.repository.get_project_membership(
            tenant_id=tenant_id, project_id=project_id, user_id=actor_id,
        )
        if membership is None:
            raise LookupError("Project not found or not authorized")
        if MANAGE_PERMISSION not in membership.permissions:
            raise PermissionError("Missing required permission: project:manage_members")
        return project

    def _view(
        self, membership: ProjectMembershipORM, user: AppUserORM,
        owner_id: UUID | None,
    ) -> MemberView:
        return MemberView(
            user_id=user.id,
            email=user.email,
            display_name=user.display_name,
            role=(
                ProjectRole(membership.role)
                if membership.role in ProjectRole._value2member_map_
                else ProjectRole.VIEWER
            ),
            permissions=list(membership.permissions),
            is_active=user.is_active,
            is_owner=user.id == owner_id,
            joined_at=_utc(membership.created_at),
        )

    def list_members(
        self,
        *,
        tenant_id: UUID,
        project_id: UUID,
        actor_id: UUID,
        limit: int = 50,
        offset: int = 0,
    ) -> MembersPage:
        project = self._authorize(tenant_id, project_id, actor_id)
        if type(limit) is not int or not 1 <= limit <= 100:
            raise ValueError("limit must be between 1 and 100")
        if type(offset) is not int or offset < 0:
            raise ValueError("offset cannot be negative")
        rows = self.session.execute(
            select(ProjectMembershipORM, AppUserORM)
            .join(
                AppUserORM,
                (AppUserORM.tenant_id == ProjectMembershipORM.tenant_id)
                & (AppUserORM.id == ProjectMembershipORM.user_id),
            )
            .where(
                ProjectMembershipORM.tenant_id == tenant_id,
                ProjectMembershipORM.project_id == project_id,
            )
            .order_by(AppUserORM.email, ProjectMembershipORM.id)
            .offset(offset)
            .limit(limit + 1)
        ).all()
        # Older operator-created roles may not match the fixed presets. Present
        # such rows as a conservative viewer; updating them requires explicit
        # selection of a supported role.
        items = [
            self._view(membership, user, project.project_manager_id)
            for membership, user in rows[:limit]
        ]
        return MembersPage(
            project_id=project_id,
            items=items,
            count=len(items),
            next_offset=offset + limit if len(rows) > limit else None,
        )

    def add_member(
        self,
        *,
        tenant_id: UUID,
        project_id: UUID,
        actor_id: UUID,
        command: AddProjectMemberRequest,
    ) -> MemberView:
        project = self._authorize(tenant_id, project_id, actor_id, lock=True)
        user = self.repository.get_user_by_email(tenant_id, str(command.email))
        if user is None or not user.is_active:
            raise LookupError("Eligible account not found in this workspace")
        membership = self.repository.get_project_membership(
            tenant_id=tenant_id, project_id=project_id, user_id=user.id,
        )
        if membership is not None:
            raise ValueError("Account is already a member of this project")
        try:
            created = self.repository.add_project_membership(
                tenant_id=tenant_id,
                project_id=project_id,
                user_id=user.id,
                role=command.role.value,
                permissions=list(ROLE_PERMISSIONS[command.role]),
            )
            self._audit(
                tenant_id=tenant_id,
                project_id=project_id,
                actor_id=actor_id,
                subject_id=user.id,
                action="project_member_added",
                previous=None,
                final={"role": command.role.value},
            )
            self.session.commit()
        except Exception:
            self.session.rollback()
            raise
        return MemberView(
            user_id=user.id,
            email=user.email,
            display_name=user.display_name,
            role=command.role,
            permissions=list(ROLE_PERMISSIONS[command.role]),
            is_active=user.is_active,
            is_owner=user.id == project.project_manager_id,
            joined_at=_utc(created.created_at),
        )

    def change_role(
        self,
        *,
        tenant_id: UUID,
        project_id: UUID,
        actor_id: UUID,
        member_id: UUID,
        command: ChangeProjectMemberRoleRequest,
    ) -> MemberView:
        project = self._authorize(tenant_id, project_id, actor_id, lock=True)
        membership = self._member_row(tenant_id, project_id, member_id)
        if membership is None:
            raise LookupError("Project member not found")
        if member_id == actor_id or member_id == project.project_manager_id:
            raise ValueError("Cannot alter your own or the original project owner's membership")
        user = self.session.scalar(
            select(AppUserORM).where(
                AppUserORM.tenant_id == tenant_id,
                AppUserORM.id == member_id,
            )
        )
        if user is None:
            raise LookupError("Project member not found")
        old_role = membership.role
        permissions = list(ROLE_PERMISSIONS[command.role])
        if old_role == command.role.value and set(membership.permissions) == set(permissions):
            return self._view(membership, user, project.project_manager_id)
        try:
            membership.role = command.role.value
            membership.permissions = permissions
            membership.updated_at = datetime.now(timezone.utc)
            self._audit(
                tenant_id=tenant_id,
                project_id=project_id,
                actor_id=actor_id,
                subject_id=member_id,
                action="project_member_role_changed",
                previous={"role": old_role},
                final={"role": command.role.value},
            )
            self.session.commit()
        except Exception:
            self.session.rollback()
            raise
        return self._view(membership, user, project.project_manager_id)

    def remove_member(
        self,
        *,
        tenant_id: UUID,
        project_id: UUID,
        actor_id: UUID,
        member_id: UUID,
    ) -> None:
        project = self._authorize(tenant_id, project_id, actor_id, lock=True)
        membership = self._member_row(tenant_id, project_id, member_id)
        if membership is None:
            raise LookupError("Project member not found")
        if member_id == actor_id or member_id == project.project_manager_id:
            raise ValueError("Cannot remove yourself or the original project owner")
        try:
            old_role = membership.role
            self.session.delete(membership)
            self._audit(
                tenant_id=tenant_id,
                project_id=project_id,
                actor_id=actor_id,
                subject_id=member_id,
                action="project_member_removed",
                previous={"role": old_role},
                final=None,
            )
            self.session.commit()
        except Exception:
            self.session.rollback()
            raise

    def _member_row(
        self, tenant_id: UUID, project_id: UUID, member_id: UUID,
    ) -> ProjectMembershipORM | None:
        return self.session.scalar(
            select(ProjectMembershipORM).where(
                ProjectMembershipORM.tenant_id == tenant_id,
                ProjectMembershipORM.project_id == project_id,
                ProjectMembershipORM.user_id == member_id,
            )
        )

    def _audit(
        self,
        *,
        tenant_id: UUID,
        project_id: UUID,
        actor_id: UUID,
        subject_id: UUID,
        action: str,
        previous: dict | None,
        final: dict | None,
    ) -> None:
        self.session.add(AuditLogORM(
            tenant_id=tenant_id,
            project_id=project_id,
            actor_id=actor_id,
            action=action,
            entity_type="ProjectMembership",
            entity_id=subject_id,
            previous_state=previous,
            proposed_state=None,
            final_state=final,
            evidence_ids=[],
        ))
