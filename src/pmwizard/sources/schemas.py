"""Read-only Sources Workspace schemas."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

from pmwizard.connectors import ConnectorRunStatus


class SourceHealthStatus(StrEnum):
    HEALTHY = "healthy"
    ATTENTION = "attention"
    FAILED = "failed"
    NEVER_SYNCED = "never_synced"
    DISABLED = "disabled"


class SourceRunView(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: UUID
    status: ConnectorRunStatus
    started_at: datetime
    finished_at: datetime
    duration_seconds: float
    pages_processed: int
    fetched: int
    ingested: int
    duplicates: int
    source_changed: int
    empty_content: int
    skipped: int
    errors: list[dict[str, Any]] = Field(default_factory=list)
    skips: list[dict[str, Any]] = Field(default_factory=list)
    start_checkpoint_present: bool
    end_checkpoint_present: bool
    checkpoint_fingerprint: str | None = None


class SourceConnectionView(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: UUID
    connector_key: str
    source_type: str
    source_system: str
    display_name: str
    permission_scope: list[str]
    safe_config: dict[str, Any]
    is_enabled: bool
    credential_configured: bool
    health: SourceHealthStatus
    checkpoint_present: bool
    checkpoint_fingerprint: str | None = None
    checkpoint_updated_at: datetime | None = None
    latest_run: SourceRunView | None = None
    recent_runs: list[SourceRunView] = Field(default_factory=list)


class SourcesSummary(BaseModel):
    model_config = ConfigDict(extra="forbid")

    total: int
    healthy: int
    attention: int
    failed: int
    never_synced: int
    disabled: int
    total_ingested: int
    total_skipped: int
    total_errors: int


class SourcesWorkspaceSnapshot(BaseModel):
    model_config = ConfigDict(extra="forbid")

    project_id: UUID
    summary: SourcesSummary
    sources: list[SourceConnectionView]


class BindSourceCredentialRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    credential_ref: str = Field(min_length=5, max_length=68)

    @field_validator("credential_ref")
    @classmethod
    def _validate_ref(cls, value: str) -> str:
        value = value.strip()
        if not value.startswith("env:"):
            raise ValueError("credential_ref must use env:ALIAS")
        alias = value[4:]
        if (
            not alias
            or len(alias) > 64
            or any(
                character not in "ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_"
                for character in alias
            )
        ):
            raise ValueError(
                "credential_ref alias must use uppercase letters, digits, or underscores"
            )
        return value


class SourceCredentialStatus(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source_connection_id: UUID
    credential_configured: bool
