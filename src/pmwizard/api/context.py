"""Trusted API identity context for PMWizard V0."""

from __future__ import annotations

from uuid import UUID

from fastapi import Header
from pydantic import BaseModel, ConfigDict, Field


class ApiPrincipal(BaseModel):
    model_config = ConfigDict(extra="forbid")

    tenant_id: UUID
    user_id: UUID
    permissions: set[str] = Field(default_factory=set)


def get_api_principal(
    tenant_id: UUID = Header(alias="X-PMWizard-Tenant-ID"),
    user_id: UUID = Header(alias="X-PMWizard-User-ID"),
    permissions_header: str = Header(
        default="",
        alias="X-PMWizard-Permissions",
    ),
) -> ApiPrincipal:
    permissions = {
        item.strip()
        for item in permissions_header.split(",")
        if item.strip()
    }
    return ApiPrincipal(
        tenant_id=tenant_id,
        user_id=user_id,
        permissions=permissions,
    )
