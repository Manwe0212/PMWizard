"""Read-only Project Memory workspace schemas."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict

from pmwizard.models import (
    ActionItem,
    Assumption,
    Decision,
    Dependency,
    Issue,
    Project,
    Risk,
)


class ProjectMemorySummary(BaseModel):
    model_config = ConfigDict(extra="forbid")

    action_items_total: int
    action_items_open: int
    action_items_blocked: int
    risks_open: int
    assumptions_open: int
    issues_open: int
    dependencies_open: int
    decisions_total: int
    decisions_approved: int


class ProjectMemorySnapshot(BaseModel):
    model_config = ConfigDict(extra="forbid")

    project: Project
    summary: ProjectMemorySummary
    action_items: list[ActionItem]
    risks: list[Risk]
    assumptions: list[Assumption]
    issues: list[Issue]
    dependencies: list[Dependency]
    decisions: list[Decision]
