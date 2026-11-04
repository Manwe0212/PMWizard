"""Authentication and project authorization application service."""

from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy.orm import Session

from .models import AppUser, AuthenticatedSession, ProjectAccess, ProjectMembership
from .repository import AuthRepository
from .security import (
    AccessTokenService,
    AuthenticationError,
    PasswordService,
)


class AuthService:
    def __init__(
        self,
        session: Session,
        token_service: AccessTokenService,
        *,
        password_service: PasswordService | None = None,
    ) -> None:
        self.session = session
        self.repository = AuthRepository(session)
        self.token_service = token_service
        self.password_service = password_service or PasswordService()

    def create_user(
        self,
        *,
        tenant_id: UUID,
        email: str,
        display_name: str,
        password: str,
    ) -> AppUser:
        user = self.repository.create_user(
            tenant_id=tenant_id,
            email=email,
            display_name=display_name,
            password_hash=self.password_service.hash(password),
        )
        self.session.commit()
        return user

    def grant_project_access(
        self,
        *,
        tenant_id: UUID,
        user_id: UUID,
        project_id: UUID,
        role: str,
        permissions: list[str],
    ) -> ProjectMembership:
        membership = self.repository.add_project_membership(
            tenant_id=tenant_id,
            user_id=user_id,
            project_id=project_id,
            role=role,
            permissions=permissions,
        )
        self.session.commit()
        return membership

    def login(
        self,
        *,
        tenant_id: UUID,
        email: str,
        password: str,
    ) -> AuthenticatedSession:
        user = self.repository.get_user_by_email(tenant_id, email)
        if user is None or not user.is_active:
            raise AuthenticationError("Invalid email or password")

        password_hash = self.repository.get_password_hash(tenant_id, user.id)
        if password_hash is None or not self.password_service.verify(
            password_hash,
            password,
        ):
            raise AuthenticationError("Invalid email or password")

        if self.password_service.needs_rehash(password_hash):
            self.repository.update_password_hash(
                tenant_id,
                user.id,
                self.password_service.hash(password),
            )
            self.session.commit()

        token = self.token_service.issue(
            user_id=user.id,
            tenant_id=tenant_id,
            auth_version=self.repository.get_auth_version(tenant_id, user.id) or 0,
        )
        return AuthenticatedSession(
            user=user,
            access_token=token,
            expires_in=self.token_service.expires_in_seconds,
        )

    def authenticate_token(self, token: str) -> AppUser:
        claims = self.token_service.decode(token)
        user = self.repository.get_user(claims.tenant_id, claims.sub)
        if user is None or not user.is_active:
            raise AuthenticationError("Authenticated user is not active")
        version = self.repository.get_auth_version(claims.tenant_id, claims.sub)
        if version is None or claims.ver != version:
            raise AuthenticationError("Session has been revoked")
        if self.repository.is_token_revoked(claims.tenant_id, claims.sub, claims.jti):
            raise AuthenticationError("Session has been revoked")
        return user

    def logout_token(self, token: str) -> None:
        """Invalidate only the current JWT, not the user's other sessions."""
        self.authenticate_token(token)
        claims = self.token_service.decode(token)
        self.repository.revoke_token(
            tenant_id=claims.tenant_id,
            user_id=claims.sub,
            jti=claims.jti,
            expires_at=datetime.fromtimestamp(claims.exp, tz=timezone.utc),
        )

    def logout_all(self, token: str) -> None:
        """Invalidate every issued access token via a DB-backed version change."""
        self.authenticate_token(token)
        claims = self.token_service.decode(token)
        self.repository.bump_auth_version(claims.tenant_id, claims.sub)
        self.session.commit()

    def list_projects(self, user: AppUser) -> list[ProjectAccess]:
        return self.repository.list_project_access(
            tenant_id=user.tenant_id,
            user_id=user.id,
        )
