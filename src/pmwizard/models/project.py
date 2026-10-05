"""Project model: the primary PMWizard intelligence boundary."""

from datetime import date
from uuid import UUID

from pydantic import Field

from .base import CanonicalEntity


class Project(CanonicalEntity):
    name: str = Field(min_length=1)
    description: str | None = None
    objective: str | None = None

    portfolio_id: UUID | None = None
    program_id: UUID | None = None

    project_manager_id: UUID | None = None
    sponsor_id: UUID | None = None

    methodology: str | None = None
    industry: str | None = None
    lifecycle_phase: str | None = None
    status: str | None = None
    priority: str | None = None

    start_date: date | None = None
    planned_end_date: date | None = None
    forecast_end_date: date | None = None
    actual_end_date: date | None = None

    business_value: str | None = None
    source_system: str | None = None
    external_id: str | None = None
