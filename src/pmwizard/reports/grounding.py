"""Deterministic Grounding Packet builder for AI status reports."""

from __future__ import annotations

from datetime import date, datetime, time, timedelta, timezone
from uuid import UUID

from sqlalchemy.orm import Session

from pmwizard.health import ProjectHealthHistoryService, ProjectHealthService
from pmwizard.memory import ProjectMemoryQueryService
from pmwizard.models.enums import (
    ActionItemStatus,
    DecisionStatus,
    DependencyStatus,
    IssueStatus,
    RiskStatus,
)
from pmwizard.sources import SourceHealthStatus, SourcesWorkspaceService

from .schemas import GroundFact, StatusReportGroundingPacket


class StatusReportGroundingService:
    """Convert governed project state into a finite reportable fact set."""

    def __init__(self, session: Session) -> None:
        self.session = session

    def build(
        self,
        *,
        tenant_id: UUID,
        project_id: UUID,
        lookback_days: int,
        as_of: datetime | None = None,
    ) -> StatusReportGroundingPacket:
        timestamp = as_of or datetime.now(timezone.utc)
        period_end = timestamp.date()
        period_start = period_end - timedelta(days=lookback_days - 1)
        period_start_dt = datetime.combine(
            period_start,
            time.min,
            tzinfo=timezone.utc,
        )

        memory = ProjectMemoryQueryService(self.session).snapshot(
            tenant_id=tenant_id,
            project_id=project_id,
        )
        health = ProjectHealthService(self.session).snapshot(
            tenant_id=tenant_id,
            project_id=project_id,
            as_of=period_end,
        )
        history = ProjectHealthHistoryService(self.session).history(
            tenant_id=tenant_id,
            project_id=project_id,
            limit=2,
        )
        sources = SourcesWorkspaceService(self.session).snapshot(
            tenant_id=tenant_id,
            project_id=project_id,
        )

        facts: list[GroundFact] = []
        project = memory.project

        project_parts = [f"Project name: {project.name}."]
        if project.status:
            project_parts.append(f"Current project status: {project.status}.")
        if project.lifecycle_phase:
            project_parts.append(
                f"Lifecycle phase: {project.lifecycle_phase}."
            )
        if project.planned_end_date:
            project_parts.append(
                f"Planned end date: {project.planned_end_date.isoformat()}."
            )
        if project.forecast_end_date:
            project_parts.append(
                f"Forecast end date: {project.forecast_end_date.isoformat()}."
            )
        facts.append(
            GroundFact(
                fact_id="PROJECT-001",
                category="project",
                text=" ".join(project_parts),
                entity_type="Project",
                entity_id=project.id,
                evidence_ids=project.provenance.evidence_ids,
                observed_at=project.updated_at,
            )
        )

        health_score_text = (
            f"{health.score}/100"
            if health.score is not None
            else "not numerically scored"
        )
        facts.append(
            GroundFact(
                fact_id="HEALTH-001",
                category="health",
                text=(
                    f"Project Health is {health.band.value}; score is "
                    f"{health_score_text}; assessment coverage is "
                    f"{health.coverage_percent}% as of {health.assessed_on.isoformat()}."
                ),
                entity_type="Project",
                entity_id=project.id,
                observed_at=timestamp,
            )
        )

        trend = history.trend
        trend_text = f"Latest captured Health trend is {trend.direction.value}."
        if trend.score_delta is not None:
            signed = f"+{trend.score_delta}" if trend.score_delta > 0 else str(trend.score_delta)
            trend_text += f" Latest score delta is {signed} points."
        if trend.coverage_delta is not None:
            signed = (
                f"+{trend.coverage_delta}"
                if trend.coverage_delta > 0
                else str(trend.coverage_delta)
            )
            trend_text += f" Coverage delta is {signed} percentage points."
        facts.append(
            GroundFact(
                fact_id="TREND-001",
                category="trend",
                text=trend_text,
                entity_type="Project",
                entity_id=project.id,
                observed_at=(
                    history.points[-1].captured_at
                    if history.points
                    else timestamp
                ),
            )
        )

        for index, driver in enumerate(health.key_drivers[:8], start=1):
            facts.append(
                GroundFact(
                    fact_id=f"HEALTH-DRIVER-{index:03d}",
                    category="health_driver",
                    text=(
                        f"Health driver: {driver.title}. {driver.detail} "
                        f"Penalty: {driver.penalty} points."
                    ),
                    entity_type=driver.entity_type,
                    entity_id=(
                        driver.entity_ids[0]
                        if len(driver.entity_ids) == 1
                        else None
                    ),
                    observed_at=timestamp,
                )
            )

        completed = sorted(
            [
                item
                for item in memory.action_items
                if item.status == ActionItemStatus.COMPLETED
                and item.completed_at is not None
                and self._aware(item.completed_at) >= period_start_dt
                and self._aware(item.completed_at) <= timestamp
            ],
            key=lambda item: self._aware(item.completed_at),
            reverse=True,
        )
        for index, item in enumerate(completed[:10], start=1):
            facts.append(
                GroundFact(
                    fact_id=f"ACCOMPLISHMENT-{index:03d}",
                    category="accomplishment",
                    text=(
                        f"Action Item completed during the reporting period: "
                        f"{item.title}. Completed at "
                        f"{self._aware(item.completed_at).isoformat()}."
                    ),
                    entity_type="ActionItem",
                    entity_id=item.id,
                    evidence_ids=item.provenance.evidence_ids,
                    observed_at=item.completed_at,
                )
            )

        blocked_or_overdue = sorted(
            [
                item
                for item in memory.action_items
                if item.status
                not in {ActionItemStatus.COMPLETED, ActionItemStatus.CANCELLED}
                and (
                    item.status == ActionItemStatus.BLOCKED
                    or (
                        item.due_date is not None
                        and item.due_date < period_end
                    )
                )
            ],
            key=lambda item: (
                item.status != ActionItemStatus.BLOCKED,
                item.due_date or date.max,
                item.title,
            ),
        )
        for index, item in enumerate(blocked_or_overdue[:10], start=1):
            descriptors: list[str] = []
            if item.status == ActionItemStatus.BLOCKED:
                descriptors.append("blocked")
            if item.due_date is not None and item.due_date < period_end:
                descriptors.append(
                    f"overdue since {item.due_date.isoformat()}"
                )
            facts.append(
                GroundFact(
                    fact_id=f"ACTION-ATTENTION-{index:03d}",
                    category="action_attention",
                    text=(
                        f"Open Action Item requiring attention: {item.title}. "
                        f"Status: {item.status.value}. "
                        f"Condition: {', '.join(descriptors)}."
                    ),
                    entity_type="ActionItem",
                    entity_id=item.id,
                    evidence_ids=item.provenance.evidence_ids,
                    observed_at=item.updated_at,
                )
            )

        next_actions = sorted(
            [
                item
                for item in memory.action_items
                if item.status
                not in {ActionItemStatus.COMPLETED, ActionItemStatus.CANCELLED}
            ],
            key=lambda item: (
                item.due_date is None,
                item.due_date or date.max,
                item.title,
            ),
        )
        for index, item in enumerate(next_actions[:10], start=1):
            due_text = (
                item.due_date.isoformat()
                if item.due_date is not None
                else "not set"
            )
            summary_text = (
                f" Progress: {item.progress_summary}"
                if item.progress_summary
                else ""
            )
            facts.append(
                GroundFact(
                    fact_id=f"NEXT-ACTION-{index:03d}",
                    category="next_action",
                    text=(
                        f"Open Action Item: {item.title}. "
                        f"Status: {item.status.value}. Due date: {due_text}."
                        f"{summary_text}"
                    ),
                    entity_type="ActionItem",
                    entity_id=item.id,
                    evidence_ids=item.provenance.evidence_ids,
                    observed_at=item.updated_at,
                )
            )

        active_risks = sorted(
            [item for item in memory.risks if item.status != RiskStatus.CLOSED],
            key=lambda item: (
                item.status != RiskStatus.MATERIALIZED,
                self._severity_rank(item.impact),
                item.due_date or date.max,
                item.title,
            ),
        )
        for index, item in enumerate(active_risks[:10], start=1):
            facts.append(
                GroundFact(
                    fact_id=f"RISK-{index:03d}",
                    category="risk",
                    text=(
                        f"Active Risk: {item.title}. Status: {item.status.value}. "
                        f"Impact: {item.impact or 'not set'}. "
                        f"Mitigation: {item.mitigation or 'not documented'}."
                    ),
                    entity_type="Risk",
                    entity_id=item.id,
                    evidence_ids=item.provenance.evidence_ids,
                    observed_at=item.updated_at,
                )
            )

        active_issues = sorted(
            [
                item
                for item in memory.issues
                if item.status not in {IssueStatus.RESOLVED, IssueStatus.CLOSED}
            ],
            key=lambda item: (
                item.status != IssueStatus.BLOCKED,
                self._severity_rank(item.severity),
                item.due_date or date.max,
                item.title,
            ),
        )
        for index, item in enumerate(active_issues[:10], start=1):
            facts.append(
                GroundFact(
                    fact_id=f"ISSUE-{index:03d}",
                    category="issue",
                    text=(
                        f"Active Issue: {item.title}. Status: {item.status.value}. "
                        f"Severity: {item.severity or 'not set'}."
                    ),
                    entity_type="Issue",
                    entity_id=item.id,
                    evidence_ids=item.provenance.evidence_ids,
                    observed_at=item.updated_at,
                )
            )

        active_dependencies = sorted(
            [
                item
                for item in memory.dependencies
                if item.status
                not in {
                    DependencyStatus.SATISFIED,
                    DependencyStatus.WAIVED,
                    DependencyStatus.CLOSED,
                }
            ],
            key=lambda item: (
                item.status != DependencyStatus.BLOCKED,
                self._severity_rank(item.criticality),
                item.required_by or date.max,
                item.title,
            ),
        )
        for index, item in enumerate(active_dependencies[:10], start=1):
            required_by = (
                item.required_by.isoformat()
                if item.required_by is not None
                else "not set"
            )
            facts.append(
                GroundFact(
                    fact_id=f"DEPENDENCY-{index:03d}",
                    category="dependency",
                    text=(
                        f"Active Dependency: {item.title}. "
                        f"Status: {item.status.value}. "
                        f"Criticality: {item.criticality or 'not set'}. "
                        f"Required by: {required_by}."
                    ),
                    entity_type="Dependency",
                    entity_id=item.id,
                    evidence_ids=item.provenance.evidence_ids,
                    observed_at=item.updated_at,
                )
            )

        reportable_decisions = sorted(
            [
                item
                for item in memory.decisions
                if (
                    item.status in {DecisionStatus.PROPOSED, DecisionStatus.PENDING}
                    or (
                        item.decision_date is not None
                        and self._aware(item.decision_date) >= period_start_dt
                        and self._aware(item.decision_date) <= timestamp
                    )
                )
            ],
            key=lambda item: (
                item.status not in {DecisionStatus.PENDING, DecisionStatus.PROPOSED},
                item.review_date is None,
                item.review_date or date.max,
                item.title,
            ),
        )
        for index, item in enumerate(reportable_decisions[:10], start=1):
            review_text = (
                item.review_date.isoformat()
                if item.review_date is not None
                else "not set"
            )
            facts.append(
                GroundFact(
                    fact_id=f"DECISION-{index:03d}",
                    category="decision",
                    text=(
                        f"Decision: {item.title}. Status: {item.status.value}. "
                        f"Review date: {review_text}. "
                        f"Expected impact: {item.expected_impact or 'not documented'}."
                    ),
                    entity_type="Decision",
                    entity_id=item.id,
                    evidence_ids=item.provenance.evidence_ids,
                    observed_at=item.decision_date or item.updated_at,
                )
            )

        source_alerts = [
            item
            for item in sources.sources
            if item.health
            in {
                SourceHealthStatus.FAILED,
                SourceHealthStatus.ATTENTION,
                SourceHealthStatus.NEVER_SYNCED,
            }
        ]
        for index, item in enumerate(source_alerts[:10], start=1):
            facts.append(
                GroundFact(
                    fact_id=f"SOURCE-{index:03d}",
                    category="data_quality",
                    text=(
                        f"Source connection {item.display_name} "
                        f"({item.source_system}) is {item.health.value}."
                    ),
                    entity_type="SourceConnection",
                    entity_id=item.id,
                    observed_at=(
                        item.latest_run.finished_at
                        if item.latest_run is not None
                        else item.checkpoint_updated_at
                    ),
                )
            )

        if health.coverage_percent < 75:
            facts.append(
                GroundFact(
                    fact_id="DATA-QUALITY-001",
                    category="data_quality",
                    text=(
                        f"Project Health assessment coverage is "
                        f"{health.coverage_percent}%, so status interpretation "
                        "should acknowledge incomplete governed data."
                    ),
                    entity_type="Project",
                    entity_id=project.id,
                    observed_at=timestamp,
                )
            )

        return StatusReportGroundingPacket(
            project_id=project.id,
            project_name=project.name,
            period_start=period_start,
            period_end=period_end,
            health_score=health.score,
            health_band=health.band,
            health_coverage_percent=health.coverage_percent,
            trend_direction=trend.direction,
            trend_score_delta=trend.score_delta,
            facts=facts,
        )

    @staticmethod
    def _aware(value: datetime | None) -> datetime:
        if value is None:
            return datetime.min.replace(tzinfo=timezone.utc)
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value

    @staticmethod
    def _severity_rank(value: str | None) -> int:
        normalized = (value or "").strip().casefold()
        return {
            "critical": 0,
            "severe": 0,
            "very high": 0,
            "high": 1,
            "major": 1,
            "medium": 2,
            "moderate": 2,
            "low": 3,
            "minor": 3,
        }.get(normalized, 4)
