"""Tenant-scoped authentication and project membership persistence."""

from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from pmwizard.persistence.orm import (
    AppUserORM,
    ProjectMembershipORM,
    ProjectORM,
)

from .models import AppUser, ProjectAccess, ProjectMembership


def _now() -> datetime:
    return datetime.now(timezone.utc)


class AuthRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def create_user(
        self,
        *,
        tenant_id: UUID,
        email: str,
        display_name: str,
        password_hash: str,
    ) -> AppUser:
        normalized_email = email.strip().casefold()
        if self.get_user_by_email(tenant_id, normalized_email) is not None:
            raise ValueError("A user with this email already exists in the tenant")

        now = _now()
        row = AppUserORM(
            id=uuid4(),
            tenant_id=tenant_id,
            email=normalized_email,
            display_name=display_name.strip(),
            password_hash=password_hash,
            is_active=True,
            created_at=now,
            updated_at=now,
        )
        self.session.add(row)
        self.session.flush()
        return self._user_from_row(row)

    def get_user(self, tenant_id: UUID, user_id: UUID) -> AppUser | None:
        row = self.session.scalar(
            select(AppUserORM).where(
                AppUserORM.tenant_id == tenant_id,
                AppUserORM.id == user_id,
            )
        )
        return self._user_from_row(row) if row is not None else None

    def get_user_by_email(self, tenant_id: UUID, email: str) -> AppUser | None:
        row = self.session.scalar(
            select(AppUserORM).where(
                AppUserORM.tenant_id == tenant_id,
                AppUserORM.email == email.strip().casefold(),
            )
        )
        return self._user_from_row(row) if row is not None else None

    def get_password_hash(self, tenant_id: UUID, user_id: UUID) -> str | None:
        return self.session.scalar(
            select(AppUserORM.password_hash).where(
                AppUserORM.tenant_id == tenant_id,
                AppUserORM.id == user_id,
            )
        )

    def update_password_hash(
        self,
        tenant_id: UUID,
        user_id: UUID,
        password_hash: str,
    ) -> None:
        row = self.session.scalar(
            select(AppUserORM).where(
                AppUserORM.tenant_id == tenant_id,
                AppUserORM.id == user_id,
            )
        )
        if row is None:
            raise LookupError("User not found for tenant")
        row.password_hash = password_hash
        row.updated_at = _now()
        self.session.flush()

    def add_project_membership(
        self,
        *,
        tenant_id: UUID,
        user_id: UUID,
        project_id: UUID,
        role: str,
        permissions: list[str],
    ) -> ProjectMembership:
        user = self.get_user(tenant_id, user_id)
        if user is None:
            raise LookupError("User not found for tenant")

        project = self.session.scalar(
            select(ProjectORM).where(
                ProjectORM.tenant_id == tenant_id,
                ProjectORM.id == project_id,
            )
        )
        if project is None:
            raise LookupError("Project not found for tenant")

        existing = self.get_project_membership(
            tenant_id=tenant_id,
            user_id=user_id,
            project_id=project_id,
        )
        if existing is not None:
            raise ValueError("Project membership already exists")

        now = _now()
        row = ProjectMembershipORM(
            id=uuid4(),
            tenant_id=tenant_id,
            user_id=user_id,
            project_id=project_id,
            role=role.strip(),
            permissions=sorted(set(permissions)),
            created_at=now,
            updated_at=now,
        )
        self.session.add(row)
        self.session.flush()
        return self._membership_from_row(row)

    def get_project_membership(
        self,
        *,
        tenant_id: UUID,
        user_id: UUID,
        project_id: UUID,
    ) -> ProjectMembership | None:
        row = self.session.scalar(
            select(ProjectMembershipORM).where(
                ProjectMembershipORM.tenant_id == tenant_id,
                ProjectMembershipORM.user_id == user_id,
                ProjectMembershipORM.project_id == project_id,
            )
        )
        return self._membership_from_row(row) if row is not None else None

    def list_project_access(
        self,
        *,
        tenant_id: UUID,
        user_id: UUID,
    ) -> list[ProjectAccess]:
        rows = self.session.execute(
            select(ProjectMembershipORM, ProjectORM)
            .join(
                ProjectORM,
                (ProjectORM.id == ProjectMembershipORM.project_id)
                & (ProjectORM.tenant_id == ProjectMembershipORM.tenant_id),
            )
            .where(
                ProjectMembershipORM.tenant_id == tenant_id,
                ProjectMembershipORM.user_id == user_id,
            )
            .order_by(ProjectORM.name, ProjectORM.id)
        ).all()

        return [
            ProjectAccess(
                project_id=project.id,
                name=project.name,
                status=project.status,
                role=membership.role,
                permissions=membership.permissions,
            )
            for membership, project in rows
        ]

    @staticmethod
    def _user_from_row(row: AppUserORM) -> AppUser:
        return AppUser(
            id=row.id,
            tenant_id=row.tenant_id,
            email=row.email,
            display_name=row.display_name,
            is_active=row.is_active,
            created_at=row.created_at,
            updated_at=row.updated_at,
        )

    @staticmethod
    def _membership_from_row(row: ProjectMembershipORM) -> ProjectMembership:
        return ProjectMembership(
            id=row.id,
            tenant_id=row.tenant_id,
            user_id=row.user_id,
            project_id=row.project_id,
            role=row.role,
            permissions=row.permissions,
            created_at=row.created_at,
            updated_at=row.updated_at,
        )
