"""Evidence and temporal event models."""

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import Field

from .base import ProjectScopedEntity


class Evidence(ProjectScopedEntity):
    source_type: str = Field(min_length=1)
    source_system: str | None = None
    source_reference: str | None = None
    external_id: str | None = None
    author: str | None = None

    captured_at: datetime
    effective_at: datetime | None = None

    content_excerpt: str | None = None
    content_hash: str | None = None
    permission_scope: list[str] = Field(default_factory=list)


class Event(ProjectScopedEntity):
    event_type: str = Field(min_length=1)
    occurred_at: datetime
    actor_id: UUID | None = None

    entity_type: str | None = None
    entity_id: UUID | None = None

    previous_value: dict[str, Any] | None = None
    new_value: dict[str, Any] | None = None
    source_evidence_id: UUID | None = None
