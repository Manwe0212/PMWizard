"""Canonical ingestion contracts for PMWizard V0."""

from datetime import datetime
from enum import StrEnum
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from pmwizard.models import Evidence


class IngestionOutcome(StrEnum):
    INGESTED = "ingested"
    DUPLICATE = "duplicate"
    SOURCE_CHANGED = "source_changed"
    EMPTY_CONTENT = "empty_content"


class SourceRecord(BaseModel):
    """Authorized raw source payload before canonical Evidence creation."""

    model_config = ConfigDict(extra="forbid")

    project_id: UUID
    source_type: str = Field(min_length=1)
    source_system: str = Field(min_length=1)
    external_id: str | None = None
    source_reference: str | None = None
    author: str | None = None

    captured_at: datetime
    effective_at: datetime | None = None

    content: str
    permission_scope: list[str] = Field(min_length=1)


class IngestionResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    outcome: IngestionOutcome
    evidence: Evidence | None = None
    duplicate_of: UUID | None = None
    reason: str
