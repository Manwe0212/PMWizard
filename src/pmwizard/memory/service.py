"""Read-only query service for governed Project Memory."""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from pmwizard.models import (
    ActionItem,
    Assumption,
    Decision,
    Dependency,
    Issue,
    Provenance,
    Risk,
)
from pmwizard.models.enums import (
    ActionItemStatus,
    AssumptionStatus,
    DecisionStatus,
    DependencyStatus,
    IssueStatus,
    RiskStatus,
)
from pmwizard.persistence import ProjectMemoryRepository
from pmwizard.persistence.orm import (
    ActionItemORM,
    AssumptionORM,
    DecisionORM,
    DependencyORM,
    IssueORM,
    RiskORM,
)

from .schemas import ProjectMemorySnapshot, ProjectMemorySummary


class ProjectMemoryQueryService:
    """Return the governed state for one tenant/project boundary."""

    def __init__(self, session: Session) -> None:
        self.session = session
        self.repository = ProjectMemoryRepository(session)

    def snapshot(
        self,
        *,
        tenant_id: UUID,
        project_id: UUID,
    ) -> ProjectMemorySnapshot:
        project = self.repository.get_project(tenant_id, project_id)
        if project is None:
            raise LookupError("Project not found for tenant")

        actions = self._actions(tenant_id, project_id)
        risks = self._risks(tenant_id, project_id)
        assumptions = self._assumptions(tenant_id, project_id)
        issues = self._issues(tenant_id, project_id)
        dependencies = self._dependencies(tenant_id, project_id)
        decisions = self._decisions(tenant_id, project_id)

        return ProjectMemorySnapshot(
            project=project,
            summary=ProjectMemorySummary(
                action_items_total=len(actions),
                action_items_open=sum(
                    item.status
                    not in {
                        ActionItemStatus.COMPLETED,
                        ActionItemStatus.CANCELLED,
                    }
                    for item in actions
                ),
                action_items_blocked=sum(
                    item.status == ActionItemStatus.BLOCKED
                    for item in actions
                ),
                risks_open=sum(
                    item.status != RiskStatus.CLOSED
                    for item in risks
                ),
                assumptions_open=sum(
                    item.status
                    not in {
                        AssumptionStatus.VALIDATED,
                        AssumptionStatus.INVALIDATED,
                        AssumptionStatus.CLOSED,
                    }
                    for item in assumptions
                ),
                issues_open=sum(
                    item.status
                    not in {
                        IssueStatus.RESOLVED,
                        IssueStatus.CLOSED,
                    }
                    for item in issues
                ),
                dependencies_open=sum(
                    item.status
                    not in {
                        DependencyStatus.SATISFIED,
                        DependencyStatus.WAIVED,
                        DependencyStatus.CLOSED,
                    }
                    for item in dependencies
                ),
                decisions_total=len(decisions),
                decisions_approved=sum(
                    item.status == DecisionStatus.APPROVED
                    for item in decisions
                ),
            ),
            action_items=actions,
            risks=risks,
            assumptions=assumptions,
            issues=issues,
            dependencies=dependencies,
            decisions=decisions,
        )

    def _actions(self, tenant_id: UUID, project_id: UUID) -> list[ActionItem]:
        rows = self.session.scalars(
            select(ActionItemORM)
            .where(
                ActionItemORM.tenant_id == tenant_id,
                ActionItemORM.project_id == project_id,
            )
            .order_by(ActionItemORM.created_at.desc(), ActionItemORM.id)
        ).all()
        return [
            ActionItem(
                id=row.id,
                project_id=row.project_id,
                title=row.title,
                description=row.description,
                owner_id=row.owner_id,
                due_date=row.due_date,
                completed_at=row.completed_at,
                status=row.status,
                priority=row.priority,
                progress_summary=row.progress_summary,
                last_progress_date=row.last_progress_date,
                latest_evidence_id=row.latest_evidence_id,
                created_at=row.created_at,
                updated_at=row.updated_at,
                provenance=Provenance.model_validate(row.provenance),
            )
            for row in rows
        ]

    def _risks(self, tenant_id: UUID, project_id: UUID) -> list[Risk]:
        rows = self.session.scalars(
            select(RiskORM)
            .where(
                RiskORM.tenant_id == tenant_id,
                RiskORM.project_id == project_id,
            )
            .order_by(RiskORM.created_at.desc(), RiskORM.id)
        ).all()
        return [
            Risk(
                id=row.id,
                project_id=row.project_id,
                title=row.title,
                description=row.description,
                category=row.category,
                probability=row.probability,
                impact=row.impact,
                exposure=row.exposure,
                impact_type=row.impact_type,
                trigger=row.trigger,
                mitigation=row.mitigation,
                contingency=row.contingency,
                owner_id=row.owner_id,
                status=row.status,
                due_date=row.due_date,
                identified_at=row.identified_at,
                closed_at=row.closed_at,
                created_at=row.created_at,
                updated_at=row.updated_at,
                provenance=Provenance.model_validate(row.provenance),
            )
            for row in rows
        ]

    def _assumptions(
        self,
        tenant_id: UUID,
        project_id: UUID,
    ) -> list[Assumption]:
        rows = self.session.scalars(
            select(AssumptionORM)
            .where(
                AssumptionORM.tenant_id == tenant_id,
                AssumptionORM.project_id == project_id,
            )
            .order_by(AssumptionORM.created_at.desc(), AssumptionORM.id)
        ).all()
        return [
            Assumption(
                id=row.id,
                project_id=row.project_id,
                title=row.title,
                description=row.description,
                category=row.category,
                owner_id=row.owner_id,
                status=row.status,
                validation_date=row.validation_date,
                identified_at=row.identified_at,
                validated_at=row.validated_at,
                outcome=row.outcome,
                created_at=row.created_at,
                updated_at=row.updated_at,
                provenance=Provenance.model_validate(row.provenance),
            )
            for row in rows
        ]

    def _issues(self, tenant_id: UUID, project_id: UUID) -> list[Issue]:
        rows = self.session.scalars(
            select(IssueORM)
            .where(
                IssueORM.tenant_id == tenant_id,
                IssueORM.project_id == project_id,
            )
            .order_by(IssueORM.created_at.desc(), IssueORM.id)
        ).all()
        return [
            Issue(
                id=row.id,
                project_id=row.project_id,
                title=row.title,
                description=row.description,
                category=row.category,
                severity=row.severity,
                impact_type=row.impact_type,
                owner_id=row.owner_id,
                status=row.status,
                due_date=row.due_date,
                identified_at=row.identified_at,
                resolved_at=row.resolved_at,
                resolution=row.resolution,
                created_at=row.created_at,
                updated_at=row.updated_at,
                provenance=Provenance.model_validate(row.provenance),
            )
            for row in rows
        ]

    def _dependencies(
        self,
        tenant_id: UUID,
        project_id: UUID,
    ) -> list[Dependency]:
        rows = self.session.scalars(
            select(DependencyORM)
            .where(
                DependencyORM.tenant_id == tenant_id,
                DependencyORM.project_id == project_id,
            )
            .order_by(DependencyORM.created_at.desc(), DependencyORM.id)
        ).all()
        return [
            Dependency(
                id=row.id,
                project_id=row.project_id,
                title=row.title,
                description=row.description,
                dependency_type=row.dependency_type,
                owner_id=row.owner_id,
                provider=row.provider,
                required_by=row.required_by,
                status=row.status,
                criticality=row.criticality,
                created_at=row.created_at,
                updated_at=row.updated_at,
                provenance=Provenance.model_validate(row.provenance),
            )
            for row in rows
        ]

    def _decisions(
        self,
        tenant_id: UUID,
        project_id: UUID,
    ) -> list[Decision]:
        rows = self.session.scalars(
            select(DecisionORM)
            .where(
                DecisionORM.tenant_id == tenant_id,
                DecisionORM.project_id == project_id,
            )
            .order_by(
                DecisionORM.decision_date.desc().nullslast(),
                DecisionORM.created_at.desc(),
                DecisionORM.id,
            )
        ).all()
        return [
            Decision(
                id=row.id,
                project_id=row.project_id,
                title=row.title,
                description=row.description,
                status=row.status,
                decision_date=row.decision_date,
                decision_maker_id=row.decision_maker_id,
                context=row.context,
                alternatives_considered=row.alternatives_considered,
                rationale=row.rationale,
                expected_impact=row.expected_impact,
                review_date=row.review_date,
                created_at=row.created_at,
                updated_at=row.updated_at,
                provenance=Provenance.model_validate(row.provenance),
            )
            for row in rows
        ]
