"""Authentication API schemas."""

from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr, Field

from .models import AppUser, ProjectAccess


class LoginRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    tenant_id: UUID
    email: EmailStr
    password: str = Field(min_length=1, max_length=256)


class LoginResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    access_token: str
    token_type: str = "bearer"
    expires_in: int
    user: AppUser


class MeResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    user: AppUser


class ProjectsResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    count: int
    items: list[ProjectAccess]
