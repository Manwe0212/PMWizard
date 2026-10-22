"""Password hashing and signed access tokens for local Authentication V0."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import UUID, uuid4

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerifyMismatchError
from pydantic import BaseModel, ConfigDict, Field


class AuthenticationError(ValueError):
    pass


class AuthSettings(BaseModel):
    model_config = ConfigDict(extra="forbid")

    secret_key: str = Field(min_length=32)
    issuer: str = "pmwizard"
    audience: str = "pmwizard-api"
    access_token_minutes: int = Field(default=30, ge=5, le=1440)


class TokenClaims(BaseModel):
    model_config = ConfigDict(extra="ignore")

    sub: UUID
    tenant_id: UUID
    iss: str
    aud: str
    iat: int
    exp: int
    jti: UUID


class PasswordService:
    """OWASP-aligned Argon2id password hashing configuration."""

    def __init__(self) -> None:
        self._hasher = PasswordHasher(
            time_cost=2,
            memory_cost=19456,
            parallelism=1,
        )

    def hash(self, password: str) -> str:
        self._validate_password(password)
        return self._hasher.hash(password)

    def verify(self, password_hash: str, password: str) -> bool:
        try:
            return self._hasher.verify(password_hash, password)
        except (VerifyMismatchError, InvalidHashError):
            return False

    def needs_rehash(self, password_hash: str) -> bool:
        try:
            return self._hasher.check_needs_rehash(password_hash)
        except InvalidHashError:
            return True

    @staticmethod
    def _validate_password(password: str) -> None:
        if len(password) < 12:
            raise ValueError("Password must contain at least 12 characters")
        if len(password) > 256:
            raise ValueError("Password must not exceed 256 characters")


class AccessTokenService:
    def __init__(self, settings: AuthSettings) -> None:
        self.settings = settings

    @property
    def expires_in_seconds(self) -> int:
        return self.settings.access_token_minutes * 60

    def issue(self, *, user_id: UUID, tenant_id: UUID) -> str:
        now = datetime.now(timezone.utc)
        payload = {
            "sub": str(user_id),
            "tenant_id": str(tenant_id),
            "iss": self.settings.issuer,
            "aud": self.settings.audience,
            "iat": int(now.timestamp()),
            "exp": int(
                (now + timedelta(minutes=self.settings.access_token_minutes)).timestamp()
            ),
            "jti": str(uuid4()),
        }
        return jwt.encode(
            payload,
            self.settings.secret_key,
            algorithm="HS256",
        )

    def decode(self, token: str) -> TokenClaims:
        try:
            payload = jwt.decode(
                token,
                self.settings.secret_key,
                algorithms=["HS256"],
                audience=self.settings.audience,
                issuer=self.settings.issuer,
                options={
                    "require": [
                        "sub",
                        "tenant_id",
                        "iss",
                        "aud",
                        "iat",
                        "exp",
                        "jti",
                    ]
                },
            )
            return TokenClaims.model_validate(payload)
        except (jwt.PyJWTError, ValueError) as exc:
            raise AuthenticationError("Invalid or expired access token") from exc
