"""Governance models for Action Items, RAID, and Decisions."""

from datetime import date, datetime
from uuid import UUID

from pydantic import Field

from .base import ProjectScopedEntity
from .enums import (
    ActionItemStatus,
    AssumptionStatus,
    DecisionStatus,
    DependencyStatus,
    IssueStatus,
    RiskStatus,
)


class ActionItem(ProjectScopedEntity):
    title: str = Field(min_length=1)
    description: str | None = None
    owner_id: UUID | None = None
    due_date: date | None = None
    completed_at: datetime | None = None
    status: ActionItemStatus = ActionItemStatus.NOT_STARTED
    priority: str | None = None

    progress_summary: str | None = None
    last_progress_date: datetime | None = None
    latest_evidence_id: UUID | None = None


class Risk(ProjectScopedEntity):
    title: str = Field(min_length=1)
    description: str | None = None
    category: str | None = None
    probability: float | None = Field(default=None, ge=0.0, le=1.0)
    impact: str | None = None
    exposure: float | None = Field(default=None, ge=0.0)
    impact_type: str | None = None
    trigger: str | None = None
    mitigation: str | None = None
    contingency: str | None = None
    owner_id: UUID | None = None
    status: RiskStatus = RiskStatus.OPEN
    due_date: date | None = None
    identified_at: datetime | None = None
    closed_at: datetime | None = None


class Assumption(ProjectScopedEntity):
    title: str = Field(min_length=1)
    description: str | None = None
    category: str | None = None
    owner_id: UUID | None = None
    status: AssumptionStatus = AssumptionStatus.OPEN
    validation_date: date | None = None
    identified_at: datetime | None = None
    validated_at: datetime | None = None
    outcome: str | None = None


class Issue(ProjectScopedEntity):
    title: str = Field(min_length=1)
    description: str | None = None
    category: str | None = None
    severity: str | None = None
    impact_type: str | None = None
    owner_id: UUID | None = None
    status: IssueStatus = IssueStatus.OPEN
    due_date: date | None = None
    identified_at: datetime | None = None
    resolved_at: datetime | None = None
    resolution: str | None = None


class Dependency(ProjectScopedEntity):
    title: str = Field(min_length=1)
    description: str | None = None
    dependency_type: str | None = None
    owner_id: UUID | None = None
    provider: str | None = None
    required_by: date | None = None
    status: DependencyStatus = DependencyStatus.OPEN
    criticality: str | None = None


class Decision(ProjectScopedEntity):
    title: str = Field(min_length=1)
    description: str | None = None
    status: DecisionStatus = DecisionStatus.PROPOSED
    decision_date: datetime | None = None
    decision_maker_id: UUID | None = None
    context: str | None = None
    alternatives_considered: list[str] = Field(default_factory=list)
    rationale: str | None = None
    expected_impact: str | None = None
    review_date: date | None = None
