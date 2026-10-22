"""Authentication context helpers for PMWizard API."""

from __future__ import annotations

from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class ApiPrincipal(BaseModel):
    model_config = ConfigDict(extra="forbid")

    tenant_id: UUID
    user_id: UUID
    permissions: set[str] = Field(default_factory=set)
    auth_method: Literal["bearer", "trusted_headers"] = "bearer"
