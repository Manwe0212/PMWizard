"""Base classes shared by PMWizard canonical models."""

from datetime import datetime, timezone
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field

from .enums import OriginType


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class Provenance(BaseModel):
    """Describes where a canonical fact or proposed interpretation came from."""

    model_config = ConfigDict(extra="forbid")

    origin: OriginType = OriginType.HUMAN
    source_system: str | None = None
    source_type: str | None = None
    source_id: str | None = None
    evidence_ids: list[UUID] = Field(default_factory=list)
    confidence: float | None = Field(default=None, ge=0.0, le=1.0)
    human_verified: bool = False


class CanonicalEntity(BaseModel):
    """Base entity with durable identity, timestamps, and provenance."""

    model_config = ConfigDict(extra="forbid", validate_assignment=True)

    id: UUID = Field(default_factory=uuid4)
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)
    provenance: Provenance = Field(default_factory=Provenance)


class ProjectScopedEntity(CanonicalEntity):
    """Canonical entity that belongs to one Project."""

    project_id: UUID
