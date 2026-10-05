"""Explicit relationships between canonical project entities."""

from datetime import datetime
from uuid import UUID

from pydantic import Field

from .base import ProjectScopedEntity
from .enums import OriginType


class Relationship(ProjectScopedEntity):
    source_entity_type: str = Field(min_length=1)
    source_entity_id: UUID
    relationship_type: str = Field(min_length=1)
    target_entity_type: str = Field(min_length=1)
    target_entity_id: UUID

    valid_from: datetime | None = None
    valid_to: datetime | None = None

    confidence: float | None = Field(default=None, ge=0.0, le=1.0)
    origin: OriginType = OriginType.HUMAN
    source_evidence_id: UUID | None = None
