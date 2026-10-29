"""Authorization-preserving Executive Dashboard V0."""

from __future__ import annotations

from datetime import date, datetime, timezone
from uuid import UUID

from sqlalchemy.orm import Session

from pmwizard.inbox import ProjectInboxService
from pmwizard.memory import ProjectMemoryQueryService
from pmwizard.models.enums import (
    AssumptionStatus,
    DecisionStatus,
    DependencyStatus,
    IssueStatus,
    ReviewStatus,
    RiskStatus,
)
from pmwizard.portfolio import ProgramPortfolioIntelligenceService
from pmwizard.sources import SourceHealthStatus, SourcesWorkspaceService

from .schemas import (
    ExecutiveDashboardSnapshot,
    ExecutiveDecisionItem,
    ExecutiveInboxItem,
    ExecutiveRAIDItem,
    ExecutiveSourceAlert,
    ExecutiveSummary,
)


class ExecutiveDashboardService:
    """Compose an executive read model from already-authorized Project truth."""

    _SEVERE_LABELS = {"critical", "high", "severe"}

    def __init__(self, session: Session) -> None:
        self.session = session

    def snapshot(
        self,
        *,
        tenant_id: UUID,
        project_permissions: dict[UUID, set[str]],
        project_names: dict[UUID, str],
    ) -> ExecutiveDashboardSnapshot:
        readable = {
            project_id: permissions
            for project_id, permissions in project_permissions.items()
            if "project:read" in permissions
        }
        authorized_ids = set(readable)

        overview = ProgramPortfolioIntelligenceService(self.session).overview(
            tenant_id=tenant_id,
            authorized_project_ids=authorized_ids,
        )

        inbox_items: list[ExecutiveInboxItem] = []
        critical_raid: list[ExecutiveRAIDItem] = []
        pending_decisions: list[ExecutiveDecisionItem] = []
        source_alerts: list[ExecutiveSourceAlert] = []

        pending_count = 0
        deferred_count = 0
        source_failures = 0
        source_attention = 0

        for project_id, permissions in readable.items():
            project_name = project_names.get(project_id, str(project_id))

            inbox = ProjectInboxService(self.session).list_items(
                tenant_id=tenant_id,
                project_id=project_id,
                permissions=permissions,
                limit=100,
            )
            pending_count += sum(
                item.review_status == ReviewStatus.PENDING
                for item in inbox.items
            )
            deferred_count += sum(
                item.review_status == ReviewStatus.DEFERRED
                for item in inbox.items
            )
            inbox_items.extend(
                ExecutiveInboxItem(
                    suggestion_id=item.id,
                    project_id=project_id,
                    project_name=project_name,
                    suggestion_type=item.suggestion_type,
                    review_status=item.review_status,
                    reason=item.reason,
                    confidence=item.confidence,
                    created_at=item.created_at,
                )
                for item in inbox.items
            )

            memory = ProjectMemoryQueryService(self.session).snapshot(
                tenant_id=tenant_id,
                project_id=project_id,
            )
            critical_raid.extend(
                self._critical_raid(
                    project_id=project_id,
                    project_name=project_name,
                    memory=memory,
                )
            )
            pending_decisions.extend(
                ExecutiveDecisionItem(
                    decision_id=decision.id,
                    project_id=project_id,
                    project_name=project_name,
                    title=decision.title,
                    status=decision.status.value,
                    review_date=decision.review_date,
                    expected_impact=decision.expected_impact,
                )
                for decision in memory.decisions
                if decision.status
                in {DecisionStatus.PROPOSED, DecisionStatus.PENDING}
            )

            sources = SourcesWorkspaceService(self.session).snapshot(
                tenant_id=tenant_id,
                project_id=project_id,
            )
            source_failures += sources.summary.failed
            source_attention += (
                sources.summary.attention + sources.summary.never_synced
            )
            source_alerts.extend(
                ExecutiveSourceAlert(
                    source_id=source.id,
                    project_id=project_id,
                    project_name=project_name,
                    display_name=source.display_name,
                    source_system=source.source_system,
                    health=source.health,
                    latest_status=(
                        source.latest_run.status.value
                        if source.latest_run is not None
                        else None
                    ),
                    latest_finished_at=(
                        source.latest_run.finished_at
                        if source.latest_run is not None
                        else None
                    ),
                    error_count=(
                        len(source.latest_run.errors)
                        if source.latest_run is not None
                        else 0
                    ),
                    skipped=(
                        source.latest_run.skipped
                        if source.latest_run is not None
                        else 0
                    ),
                )
                for source in sources.sources
                if source.health
                in {
                    SourceHealthStatus.FAILED,
                    SourceHealthStatus.ATTENTION,
                    SourceHealthStatus.NEVER_SYNCED,
                }
            )

        attention_projects = [
            item
            for item in overview.attention_projects
            if (
                item.health_band.value in {"red", "amber"}
                or item.trend_direction.value == "deteriorating"
            )
        ]

        inbox_items.sort(
            key=lambda item: (
                item.review_status != ReviewStatus.PENDING,
                -item.created_at.timestamp(),
                item.project_name,
            )
        )
        critical_raid.sort(
            key=lambda item: (
                self._severity_rank(item.severity),
                item.due_date or date.max,
                item.project_name,
                item.title,
            )
        )
        pending_decisions.sort(
            key=lambda item: (
                item.review_date is None,
                item.review_date or date.max,
                item.project_name,
                item.title,
            )
        )
        source_alerts.sort(
            key=lambda item: (
                self._source_rank(item.health),
                item.project_name,
                item.display_name,
            )
        )

        return ExecutiveDashboardSnapshot(
            generated_at=datetime.now(timezone.utc),
            summary=ExecutiveSummary(
                health=overview.summary,
                projects_needing_attention=len(attention_projects),
                pending_inbox=pending_count,
                deferred_inbox=deferred_count,
                critical_raid=len(critical_raid),
                pending_decisions=len(pending_decisions),
                source_failures=source_failures,
                source_attention=source_attention,
                cross_project_signals=len(overview.cross_project_signals),
            ),
            attention_projects=attention_projects[:10],
            inbox_items=inbox_items[:10],
            critical_raid=critical_raid[:12],
            pending_decisions=pending_decisions[:10],
            source_alerts=source_alerts[:10],
            cross_project_signals=overview.cross_project_signals[:10],
        )

    def _critical_raid(
        self,
        *,
        project_id: UUID,
        project_name: str,
        memory,
    ) -> list[ExecutiveRAIDItem]:
        items: list[ExecutiveRAIDItem] = []

        for risk in memory.risks:
            severity = (risk.impact or "").casefold()
            if (
                risk.status == RiskStatus.MATERIALIZED
                or (
                    risk.status != RiskStatus.CLOSED
                    and severity in self._SEVERE_LABELS
                )
            ):
                items.append(
                    ExecutiveRAIDItem(
                        entity_type="Risk",
                        entity_id=risk.id,
                        project_id=project_id,
                        project_name=project_name,
                        title=risk.title,
                        status=risk.status.value,
                        severity=(
                            "critical"
                            if risk.status == RiskStatus.MATERIALIZED
                            else severity or "high"
                        ),
                        due_date=risk.due_date,
                        reason=(
                            "Risk has materialized."
                            if risk.status == RiskStatus.MATERIALIZED
                            else f"Active risk impact is {risk.impact}."
                        ),
                    )
                )

        for assumption in memory.assumptions:
            if assumption.status == AssumptionStatus.INVALIDATED:
                items.append(
                    ExecutiveRAIDItem(
                        entity_type="Assumption",
                        entity_id=assumption.id,
                        project_id=project_id,
                        project_name=project_name,
                        title=assumption.title,
                        status=assumption.status.value,
                        severity="high",
                        due_date=assumption.validation_date,
                        reason="A governed project assumption was invalidated.",
                    )
                )

        for issue in memory.issues:
            severity = (issue.severity or "").casefold()
            if (
                issue.status == IssueStatus.BLOCKED
                or (
                    issue.status
                    not in {IssueStatus.RESOLVED, IssueStatus.CLOSED}
                    and severity in self._SEVERE_LABELS
                )
            ):
                items.append(
                    ExecutiveRAIDItem(
                        entity_type="Issue",
                        entity_id=issue.id,
                        project_id=project_id,
                        project_name=project_name,
                        title=issue.title,
                        status=issue.status.value,
                        severity=(
                            "critical"
                            if issue.status == IssueStatus.BLOCKED
                            else severity or "high"
                        ),
                        due_date=issue.due_date,
                        reason=(
                            "Issue is blocked."
                            if issue.status == IssueStatus.BLOCKED
                            else f"Active issue severity is {issue.severity}."
                        ),
                    )
                )

        for dependency in memory.dependencies:
            severity = (dependency.criticality or "").casefold()
            if (
                dependency.status == DependencyStatus.BLOCKED
                or (
                    dependency.status
                    not in {
                        DependencyStatus.SATISFIED,
                        DependencyStatus.WAIVED,
                        DependencyStatus.CLOSED,
                    }
                    and severity in self._SEVERE_LABELS
                )
            ):
                items.append(
                    ExecutiveRAIDItem(
                        entity_type="Dependency",
                        entity_id=dependency.id,
                        project_id=project_id,
                        project_name=project_name,
                        title=dependency.title,
                        status=dependency.status.value,
                        severity=(
                            "critical"
                            if dependency.status == DependencyStatus.BLOCKED
                            else severity or "high"
                        ),
                        due_date=dependency.required_by,
                        reason=(
                            "Dependency is blocked."
                            if dependency.status == DependencyStatus.BLOCKED
                            else (
                                "Active dependency criticality is "
                                f"{dependency.criticality}."
                            )
                        ),
                    )
                )

        return items

    @staticmethod
    def _severity_rank(value: str) -> int:
        return {
            "critical": 0,
            "severe": 1,
            "high": 2,
            "medium": 3,
            "low": 4,
        }.get(value.casefold(), 5)

    @staticmethod
    def _source_rank(value: SourceHealthStatus) -> int:
        return {
            SourceHealthStatus.FAILED: 0,
            SourceHealthStatus.ATTENTION: 1,
            SourceHealthStatus.NEVER_SYNCED: 2,
            SourceHealthStatus.DISABLED: 3,
            SourceHealthStatus.HEALTHY: 4,
        }[value]
