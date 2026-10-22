"""Authentication and project-access domain models."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr, Field


class AppUser(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: UUID
    tenant_id: UUID
    email: EmailStr
    display_name: str = Field(min_length=1, max_length=255)
    is_active: bool = True
    created_at: datetime
    updated_at: datetime


class ProjectMembership(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: UUID
    tenant_id: UUID
    user_id: UUID
    project_id: UUID
    role: str = Field(min_length=1, max_length=100)
    permissions: list[str] = Field(default_factory=list)
    created_at: datetime
    updated_at: datetime


class ProjectAccess(BaseModel):
    model_config = ConfigDict(extra="forbid")

    project_id: UUID
    name: str
    status: str | None = None
    role: str
    permissions: list[str] = Field(default_factory=list)


class AuthenticatedSession(BaseModel):
    model_config = ConfigDict(extra="forbid")

    user: AppUser
    access_token: str
    expires_in: int
