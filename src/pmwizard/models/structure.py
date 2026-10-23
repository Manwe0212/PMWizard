"""Program and Portfolio structure models."""

from datetime import date
from uuid import UUID

from pydantic import Field

from .base import CanonicalEntity


class Portfolio(CanonicalEntity):
    name: str = Field(min_length=1)
    description: str | None = None
    owner_id: UUID | None = None
    status: str | None = None
    start_date: date | None = None
    end_date: date | None = None
    strategic_objectives: list[str] = Field(default_factory=list)
    source_system: str | None = None
    external_id: str | None = None


class Program(CanonicalEntity):
    portfolio_id: UUID | None = None
    name: str = Field(min_length=1)
    description: str | None = None
    program_manager_id: UUID | None = None
    status: str | None = None
    start_date: date | None = None
    end_date: date | None = None
    objectives: list[str] = Field(default_factory=list)
    source_system: str | None = None
    external_id: str | None = None
