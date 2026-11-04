"""Tenant-scoped, one-use password recovery over verified SMTP.

All reset tokens are stored as SHA-256 digests. Only already verified, active
accounts receive mail. Unknown, inactive, and unverified accounts are treated
identically to callers, preventing user directory enumeration.
"""

from __future__ import annotations

import hashlib
import re
import secrets
from datetime import datetime, timedelta, timezone
from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from pmwizard.auth import PasswordService
from pmwizard.invitations.email_delivery import InvitationEmailDelivery
from pmwizard.persistence.orm import AppUserORM, AuditLogORM, PasswordResetORM

RESET_TTL = timedelta(minutes=30)
RESET_COOLDOWN = timedelta(minutes=15)
GENERIC_MESSAGE = "If this verified account exists, password reset instructions will be emailed."
INVALID_TOKEN = "Reset link is invalid, expired or already used."
TOKEN_FORMAT = re.compile(r"^[A-Za-z0-9_-]{40,128}$")


class PasswordResetRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    tenant_id: UUID
    email: EmailStr


class PasswordResetConfirm(BaseModel):
    model_config = ConfigDict(extra="forbid")
    token: str = Field(min_length=40, max_length=128)
    password: str = Field(min_length=12, max_length=256)


class PasswordResetMessage(BaseModel):
    model_config = ConfigDict(extra="forbid")
    message: str = GENERIC_MESSAGE


def _utc(timestamp: datetime) -> datetime:
    return (
        timestamp.replace(tzinfo=timezone.utc)
        if timestamp.tzinfo is None
        else timestamp.astimezone(timezone.utc)
    )


class PasswordRecoveryService:
    def __init__(self, session: Session, email_delivery: InvitationEmailDelivery) -> None:
        self.session = session
        self.email_delivery = email_delivery

    def request(self, command: PasswordResetRequest) -> None:
        now = datetime.now(timezone.utc)
        user = self.session.scalar(
            select(AppUserORM).where(
                AppUserORM.tenant_id == command.tenant_id,
                AppUserORM.email == str(command.email).casefold(),
                AppUserORM.is_active.is_(True),
                AppUserORM.email_verified_at.is_not(None),
            ).with_for_update()
        )
        if user is None:
            return

        # A persisted per-account cooldown limits repeated mail. Unknown,
        # unverified or throttled accounts all receive the same response.
        recent = self.session.scalar(
            select(PasswordResetORM.id).where(
                PasswordResetORM.tenant_id == user.tenant_id,
                PasswordResetORM.user_id == user.id,
                PasswordResetORM.created_at > now - RESET_COOLDOWN,
            ).limit(1)
        )
        if recent is not None:
            return

        token = secrets.token_urlsafe(32)
        row = PasswordResetORM(
            tenant_id=user.tenant_id,
            user_id=user.id,
            token_hash=hashlib.sha256(token.encode("ascii")).hexdigest(),
            expires_at=now + RESET_TTL,
            used_at=None,
        )
        try:
            self.session.add(row)
            self.session.flush()
            link = f"{self.email_delivery.public_base_url}/reset-password#token={token}"
            self.email_delivery.provider.send(
                to_email=user.email,
                subject="[PMWizard] Reset your password",
                text=(
                    "A request to reset your PMWizard password was received.\n\n"
                    "Open this single-use link to set a new password:\n"
                    f"{link}\n\n"
                    "This link expires in 30 minutes. If you did not request "
                    "this change, you can ignore this email. Do not forward the link."
                ),
            )
            self.session.commit()
        except Exception:
            self.session.rollback()
            # Caller must not learn whether the email address exists nor see
            # SMTP errors or raw token material.
            return

    def confirm(self, command: PasswordResetConfirm) -> None:
        if not TOKEN_FORMAT.fullmatch(command.token):
            raise ValueError(INVALID_TOKEN)
        now = datetime.now(timezone.utc)
        token_hash = hashlib.sha256(command.token.encode("ascii")).hexdigest()
        reset = self.session.scalar(
            select(PasswordResetORM)
            .where(PasswordResetORM.token_hash == token_hash)
            .with_for_update()
        )
        if (
            reset is None
            or reset.used_at is not None
            or _utc(reset.expires_at) <= now
        ):
            raise ValueError(INVALID_TOKEN)

        user = self.session.scalar(
            select(AppUserORM).where(
                AppUserORM.id == reset.user_id,
                AppUserORM.tenant_id == reset.tenant_id,
                AppUserORM.is_active.is_(True),
                AppUserORM.email_verified_at.is_not(None),
            ).with_for_update()
        )
        if user is None:
            raise ValueError(INVALID_TOKEN)

        password_hash = PasswordService().hash(command.password)
        try:
            user.password_hash = password_hash
            user.auth_version += 1
            user.updated_at = now
            # Invalidate OTHER outstanding recovery tokens for this account.
            outstanding = self.session.scalars(
                select(PasswordResetORM).where(
                    PasswordResetORM.tenant_id == user.tenant_id,
                    PasswordResetORM.user_id == user.id,
                    PasswordResetORM.used_at.is_(None),
                )
            ).all()
            for row in outstanding:
                row.used_at = now
            self.session.add(AuditLogORM(
                tenant_id=user.tenant_id,
                project_id=None,
                actor_id=user.id,
                action="account_password_reset",
                entity_type="AppUser",
                entity_id=user.id,
                previous_state=None,
                proposed_state=None,
                final_state={"sessions_revoked": True},
                evidence_ids=[],
            ))
            self.session.commit()
        except Exception:
            self.session.rollback()
            raise
