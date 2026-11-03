"""Expiring, one-use project invitations for previously unregistered users.

Token material exists only in the one-time creation response and the recipient
browser; the database and audit history contain only its SHA-256 digest.
"""

from __future__ import annotations

import hashlib
import re
import secrets
from datetime import datetime, timedelta, timezone
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from pmwizard.auth import (
    AccessTokenService,
    AppUser,
    AuthRepository,
    PasswordService,
)
from pmwizard.members import ProjectMemberService, ProjectRole, ROLE_PERMISSIONS
from pmwizard.persistence.orm import (
    AppUserORM,
    AuditLogORM,
    ProjectInvitationORM,
    ProjectORM,
)
from .email_delivery import InvitationEmailDelivery, InvitationDeliveryUnavailable

INVITE_TTL = timedelta(days=7)
MAX_PENDING_PER_PROJECT = 25
_TOKEN_PATTERN = re.compile(r"^[a-zA-Z0-9_-]{40,128}$")
INVALID_INVITE = "Invitation is invalid, expired or already used."


def utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def digest_token(token: str) -> str:
    return hashlib.sha256(token.encode("ascii")).hexdigest()


class CreateInvitationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    email: EmailStr
    role: ProjectRole = ProjectRole.VIEWER
    delivery_method: Literal["manual", "email"] = "manual"


class AcceptInvitationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    token: str = Field(min_length=40, max_length=128)
    display_name: str = Field(min_length=2, max_length=120)
    password: str = Field(min_length=12, max_length=256)


class InvitationView(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: UUID
    email: EmailStr
    role: ProjectRole
    status: str
    invited_by: UUID
    created_at: datetime
    expires_at: datetime
    delivery_method: Literal["manual", "email"] = "manual"
    delivery_status: Literal["not_applicable", "sent"] = "not_applicable"
    delivered_at: datetime | None = None


class InvitationCreated(BaseModel):
    model_config = ConfigDict(extra="forbid")
    invitation: InvitationView
    token: str | None  # Manual only; never returned for verified email delivery


class InvitationPage(BaseModel):
    model_config = ConfigDict(extra="forbid")
    items: list[InvitationView]
    count: int
    next_offset: int | None


class InvitationAcceptance(BaseModel):
    model_config = ConfigDict(extra="forbid")
    access_token: str
    expires_in: int
    user: AppUser
    project_id: UUID


class ProjectInvitationService:
    def __init__(self, session: Session) -> None:
        self.session = session
        self.auth = AuthRepository(session)

    def _view(self, invitation: ProjectInvitationORM, now: datetime) -> InvitationView:
        status = invitation.status
        if status == "pending" and utc(invitation.expires_at) <= now:
            status = "expired"
        return InvitationView(
            id=invitation.id,
            email=invitation.invited_email,
            role=ProjectRole(invitation.role),
            status=status,
            invited_by=invitation.invited_by,
            created_at=utc(invitation.created_at),
            expires_at=utc(invitation.expires_at),
            delivery_method=invitation.delivery_method,
            delivery_status=invitation.delivery_status,
            delivered_at=utc(invitation.delivered_at) if invitation.delivered_at else None,
        )

    def list(
        self, *, tenant_id: UUID, project_id: UUID, actor_id: UUID,
        limit: int = 50, offset: int = 0,
    ) -> InvitationPage:
        ProjectMemberService(self.session)._authorize(tenant_id, project_id, actor_id)
        now = datetime.now(timezone.utc)
        rows = self.session.scalars(
            select(ProjectInvitationORM)
            .where(
                ProjectInvitationORM.tenant_id == tenant_id,
                ProjectInvitationORM.project_id == project_id,
            )
            .order_by(ProjectInvitationORM.created_at.desc(), ProjectInvitationORM.id.desc())
            .offset(offset)
            .limit(limit + 1)
        ).all()
        return InvitationPage(
            items=[self._view(x, now) for x in rows[:limit]],
            count=min(limit, len(rows)),
            next_offset=offset + limit if len(rows) > limit else None,
        )

    def create(
        self, *, tenant_id: UUID, project_id: UUID, actor_id: UUID,
        command: CreateInvitationRequest,
        email_delivery: InvitationEmailDelivery | None = None,
    ) -> InvitationCreated:
        ProjectMemberService(self.session)._authorize(tenant_id, project_id, actor_id, lock=True)
        if command.delivery_method == "email" and email_delivery is None:
            raise InvitationDeliveryUnavailable("Verified invitation email is not configured.")
        email = str(command.email).strip().casefold()
        now = datetime.now(timezone.utc)
        if self.auth.get_user_by_email(tenant_id, email) is not None:
            raise ValueError("Account already exists; use Add existing member instead.")

        active = self.session.scalars(
            select(ProjectInvitationORM)
            .where(
                ProjectInvitationORM.tenant_id == tenant_id,
                ProjectInvitationORM.project_id == project_id,
                ProjectInvitationORM.status == "pending",
                ProjectInvitationORM.expires_at > now,
            )
        ).all()
        if len(active) >= MAX_PENDING_PER_PROJECT:
            raise ValueError("Too many pending invitations for this project.")
        if any(inv.invited_email == email for inv in active):
            raise ValueError("A pending invitation already exists for this email.")

        token = secrets.token_urlsafe(32)
        row = ProjectInvitationORM(
            tenant_id=tenant_id,
            project_id=project_id,
            invited_email=email,
            role=command.role.value,
            token_hash=digest_token(token),
            invited_by=actor_id,
            expires_at=now + INVITE_TTL,
            status="pending",
            delivery_method=command.delivery_method,
            delivery_status="not_applicable",
        )
        try:
            self.session.add(row)
            self.session.flush()
            self.session.add(AuditLogORM(
                tenant_id=tenant_id,
                project_id=project_id,
                actor_id=actor_id,
                action="project_invitation_created",
                entity_type="ProjectInvitation",
                entity_id=row.id,
                previous_state=None,
                proposed_state=None,
                final_state={"status": "pending", "role": row.role, "delivery_method": row.delivery_method},
                evidence_ids=[],
            ))
            if command.delivery_method == "email":
                assert email_delivery is not None
                email_delivery.send(email=email, token=token, role=row.role)
                row.delivery_status = "sent"
                row.delivered_at = datetime.now(timezone.utc)
            self.session.commit()
        except Exception:
            self.session.rollback()
            raise
        return InvitationCreated(
            invitation=self._view(row, now),
            token=token if command.delivery_method == "manual" else None,
        )

    def revoke(
        self, *, tenant_id: UUID, project_id: UUID, actor_id: UUID,
        invitation_id: UUID,
    ) -> None:
        ProjectMemberService(self.session)._authorize(tenant_id, project_id, actor_id, lock=True)
        row = self.session.scalar(
            select(ProjectInvitationORM)
            .where(
                ProjectInvitationORM.tenant_id == tenant_id,
                ProjectInvitationORM.project_id == project_id,
                ProjectInvitationORM.id == invitation_id,
            )
            .with_for_update()
        )
        if row is None:
            raise LookupError("Invitation not found.")
        if row.status != "pending":
            raise ValueError("Invitation is no longer pending.")
        try:
            row.status = "revoked"
            row.revoked_at = datetime.now(timezone.utc)
            self.session.add(AuditLogORM(
                tenant_id=tenant_id,
                project_id=project_id,
                actor_id=actor_id,
                action="project_invitation_revoked",
                entity_type="ProjectInvitation",
                entity_id=row.id,
                previous_state={"status": "pending"},
                proposed_state=None,
                final_state={"status": "revoked"},
                evidence_ids=[],
            ))
            self.session.commit()
        except Exception:
            self.session.rollback()
            raise

    def accept(
        self, *, command: AcceptInvitationRequest,
        token_service: AccessTokenService,
    ) -> InvitationAcceptance:
        if not _TOKEN_PATTERN.fullmatch(command.token):
            raise ValueError(INVALID_INVITE)
        token_hash = digest_token(command.token)
        row = self.session.scalar(
            select(ProjectInvitationORM)
            .where(ProjectInvitationORM.token_hash == token_hash)
            .with_for_update()
        )
        now = datetime.now(timezone.utc)
        if (
            row is None or row.status != "pending"
            or utc(row.expires_at) <= now
        ):
            raise ValueError(INVALID_INVITE)
        project = self.session.scalar(
            select(ProjectORM).where(
                ProjectORM.id == row.project_id,
                ProjectORM.tenant_id == row.tenant_id,
            )
        )
        if project is None:
            raise ValueError(INVALID_INVITE)
        if self.auth.get_user_by_email(row.tenant_id, row.invited_email) is not None:
            raise ValueError(INVALID_INVITE)

        # Password hashing before any mutation and strictly transactional
        # account + project membership + token consumption + audit.
        password_hash = PasswordService().hash(command.password)
        try:
            user = self.auth.create_user(
                tenant_id=row.tenant_id,
                email=row.invited_email,
                display_name=command.display_name.strip(),
                password_hash=password_hash,
            )
            if row.delivery_method == "email":
                if row.delivery_status != "sent":
                    raise ValueError(INVALID_INVITE)
                user_row = self.session.get(AppUserORM, user.id)
                if user_row is None:
                    raise ValueError(INVALID_INVITE)
                user_row.email_verified_at = now
            self.auth.add_project_membership(
                tenant_id=row.tenant_id,
                project_id=row.project_id,
                user_id=user.id,
                role=row.role,
                permissions=list(ROLE_PERMISSIONS[ProjectRole(row.role)]),
            )
            row.status = "accepted"
            row.accepted_at = now
            row.accepted_user_id = user.id
            self.session.add(AuditLogORM(
                tenant_id=row.tenant_id,
                project_id=row.project_id,
                actor_id=user.id,
                action="project_invitation_accepted",
                entity_type="ProjectInvitation",
                entity_id=row.id,
                previous_state={"status": "pending"},
                proposed_state=None,
                final_state={"status": "accepted", "role": row.role},
                evidence_ids=[],
            ))
            self.session.commit()
        except Exception:
            self.session.rollback()
            raise

        return InvitationAcceptance(
            access_token=token_service.issue(user_id=user.id, tenant_id=row.tenant_id),
            expires_in=token_service.expires_in_seconds,
            user=self.auth.get_user(row.tenant_id, user.id),
            project_id=row.project_id,
        )
