"""Authorized Program and Portfolio Intelligence rollups."""

from __future__ import annotations

import re
from collections import defaultdict
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from pmwizard.health import (
    HealthBand,
    ProjectHealthHistoryService,
    ProjectHealthService,
    TrendDirection,
)
from pmwizard.models.enums import DependencyStatus, RiskStatus
from pmwizard.persistence.orm import DependencyORM, RiskORM

from .repository import StructureRepository
from .schemas import (
    CrossProjectSignal,
    PortfolioRollup,
    ProgramPortfolioOverview,
    ProgramRollup,
    ProjectRollupItem,
    RollupSummary,
)


class ProgramPortfolioIntelligenceService:
    """Build rollups only from projects already authorized to the caller."""

    def __init__(self, session: Session) -> None:
        self.session = session
        self.repository = StructureRepository(session)

    def overview(
        self,
        *,
        tenant_id: UUID,
        authorized_project_ids: set[UUID],
    ) -> ProgramPortfolioOverview:
        project_rows = self.repository.list_project_rows(
            tenant_id=tenant_id,
            project_ids=authorized_project_ids,
        )
        visible_project_ids = {row.id for row in project_rows}

        program_ids = {
            row.program_id
            for row in project_rows
            if row.program_id is not None
        }
        program_rows = self.repository.list_program_rows(
            tenant_id=tenant_id,
            program_ids=program_ids,
        )
        programs_by_id = {row.id: row for row in program_rows}

        portfolio_ids = {
            row.portfolio_id
            for row in project_rows
            if row.portfolio_id is not None
        }
        portfolio_ids.update(
            row.portfolio_id
            for row in program_rows
            if row.portfolio_id is not None
        )
        portfolio_rows = self.repository.list_portfolio_rows(
            tenant_id=tenant_id,
            portfolio_ids=portfolio_ids,
        )
        portfolios_by_id = {row.id: row for row in portfolio_rows}

        cards = [
            self._project_card(
                tenant_id=tenant_id,
                project_row=row,
                program_row=(
                    programs_by_id.get(row.program_id)
                    if row.program_id is not None
                    else None
                ),
                portfolios_by_id=portfolios_by_id,
            )
            for row in project_rows
        ]
        cards_by_id = {card.project_id: card for card in cards}

        program_projects: dict[UUID, list[ProjectRollupItem]] = defaultdict(list)
        direct_portfolio_projects: dict[UUID, list[ProjectRollupItem]] = defaultdict(list)
        standalone_projects: list[ProjectRollupItem] = []

        for card in cards:
            if card.program_id is not None and card.program_id in programs_by_id:
                program_projects[card.program_id].append(card)
            elif card.portfolio_id is not None and card.portfolio_id in portfolios_by_id:
                direct_portfolio_projects[card.portfolio_id].append(card)
            else:
                standalone_projects.append(card)

        program_rollups: dict[UUID, ProgramRollup] = {}
        for program_id, program_cards in program_projects.items():
            row = programs_by_id[program_id]
            portfolio = (
                portfolios_by_id.get(row.portfolio_id)
                if row.portfolio_id is not None
                else None
            )
            program_rollups[program_id] = ProgramRollup(
                id=row.id,
                name=row.name,
                description=row.description,
                status=row.status,
                portfolio_id=portfolio.id if portfolio is not None else None,
                portfolio_name=portfolio.name if portfolio is not None else None,
                summary=self._summary(program_cards),
                projects=self._sort_projects(program_cards),
            )

        portfolio_rollups: list[PortfolioRollup] = []
        for portfolio_id, row in portfolios_by_id.items():
            programs = [
                rollup
                for rollup in program_rollups.values()
                if rollup.portfolio_id == portfolio_id
            ]
            direct_projects = direct_portfolio_projects.get(portfolio_id, [])
            all_projects = list(direct_projects)
            for program in programs:
                all_projects.extend(program.projects)

            if not all_projects:
                continue

            portfolio_rollups.append(
                PortfolioRollup(
                    id=row.id,
                    name=row.name,
                    description=row.description,
                    status=row.status,
                    strategic_objectives=row.strategic_objectives,
                    summary=self._summary(all_projects),
                    programs=sorted(programs, key=lambda item: (item.name, str(item.id))),
                    direct_projects=self._sort_projects(direct_projects),
                )
            )

        standalone_programs = sorted(
            [
                rollup
                for rollup in program_rollups.values()
                if rollup.portfolio_id is None
            ],
            key=lambda item: (item.name, str(item.id)),
        )

        return ProgramPortfolioOverview(
            summary=self._summary(cards),
            portfolios=sorted(
                portfolio_rollups,
                key=lambda item: (item.name, str(item.id)),
            ),
            standalone_programs=standalone_programs,
            standalone_projects=self._sort_projects(standalone_projects),
            attention_projects=self._attention_projects(cards)[:10],
            cross_project_signals=self._cross_project_signals(
                tenant_id=tenant_id,
                project_ids=visible_project_ids,
                cards_by_id=cards_by_id,
            ),
        )

    def _project_card(
        self,
        *,
        tenant_id: UUID,
        project_row,
        program_row,
        portfolios_by_id,
    ) -> ProjectRollupItem:
        health = ProjectHealthService(self.session).snapshot(
            tenant_id=tenant_id,
            project_id=project_row.id,
        )
        history = ProjectHealthHistoryService(self.session).history(
            tenant_id=tenant_id,
            project_id=project_row.id,
            limit=2,
        )

        resolved_portfolio_id = (
            program_row.portfolio_id
            if program_row is not None and program_row.portfolio_id is not None
            else project_row.portfolio_id
        )
        portfolio = (
            portfolios_by_id.get(resolved_portfolio_id)
            if resolved_portfolio_id is not None
            else None
        )

        return ProjectRollupItem(
            project_id=project_row.id,
            name=project_row.name,
            status=project_row.status,
            priority=project_row.priority,
            program_id=program_row.id if program_row is not None else None,
            program_name=program_row.name if program_row is not None else None,
            portfolio_id=portfolio.id if portfolio is not None else None,
            portfolio_name=portfolio.name if portfolio is not None else None,
            health_score=health.score,
            health_band=health.band,
            health_coverage_percent=health.coverage_percent,
            trend_direction=history.trend.direction,
            trend_score_delta=history.trend.score_delta,
            top_drivers=[driver.title for driver in health.key_drivers[:3]],
        )

    @staticmethod
    def _summary(projects: list[ProjectRollupItem]) -> RollupSummary:
        total = len(projects)
        reliable = [
            project
            for project in projects
            if project.health_score is not None
            and project.health_band != HealthBand.INSUFFICIENT_DATA
        ]
        score = (
            round(
                sum(project.health_score or 0 for project in reliable)
                / len(reliable)
            )
            if reliable
            else None
        )
        average_coverage = (
            round(
                sum(project.health_coverage_percent for project in projects)
                / total
            )
            if total
            else 0
        )

        if score is None or average_coverage < 35:
            band = HealthBand.INSUFFICIENT_DATA
        elif score >= 80:
            band = HealthBand.GREEN
        elif score >= 60:
            band = HealthBand.AMBER
        else:
            band = HealthBand.RED

        return RollupSummary(
            projects_total=total,
            projects_scored=len(reliable),
            score=score,
            band=band,
            average_coverage_percent=average_coverage,
            green=sum(project.health_band == HealthBand.GREEN for project in projects),
            amber=sum(project.health_band == HealthBand.AMBER for project in projects),
            red=sum(project.health_band == HealthBand.RED for project in projects),
            insufficient_data=sum(
                project.health_band == HealthBand.INSUFFICIENT_DATA
                for project in projects
            ),
            improving=sum(
                project.trend_direction == TrendDirection.IMPROVING
                for project in projects
            ),
            stable=sum(
                project.trend_direction == TrendDirection.STABLE
                for project in projects
            ),
            deteriorating=sum(
                project.trend_direction == TrendDirection.DETERIORATING
                for project in projects
            ),
            insufficient_history=sum(
                project.trend_direction == TrendDirection.INSUFFICIENT_HISTORY
                for project in projects
            ),
        )

    @staticmethod
    def _sort_projects(
        projects: list[ProjectRollupItem],
    ) -> list[ProjectRollupItem]:
        return sorted(projects, key=lambda item: (item.name, str(item.project_id)))

    @staticmethod
    def _attention_projects(
        projects: list[ProjectRollupItem],
    ) -> list[ProjectRollupItem]:
        band_rank = {
            HealthBand.RED: 0,
            HealthBand.AMBER: 2,
            HealthBand.INSUFFICIENT_DATA: 3,
            HealthBand.GREEN: 4,
        }

        def rank(project: ProjectRollupItem):
            trend_priority = (
                0
                if project.trend_direction == TrendDirection.DETERIORATING
                else 1
            )
            return (
                min(band_rank[project.health_band], trend_priority),
                band_rank[project.health_band],
                project.health_score if project.health_score is not None else 101,
                project.name,
            )

        return sorted(projects, key=rank)

    def _cross_project_signals(
        self,
        *,
        tenant_id: UUID,
        project_ids: set[UUID],
        cards_by_id: dict[UUID, ProjectRollupItem],
    ) -> list[CrossProjectSignal]:
        if len(project_ids) < 2:
            return []

        groups: dict[
            tuple[str, str],
            list[tuple[UUID, str, str | None, str]],
        ] = defaultdict(list)

        risks = self.session.scalars(
            select(RiskORM).where(
                RiskORM.tenant_id == tenant_id,
                RiskORM.project_id.in_(project_ids),
                RiskORM.status != RiskStatus.CLOSED.value,
            )
        ).all()
        for row in risks:
            key = self._normalize_title(row.title)
            if key:
                groups[("risk", key)].append(
                    (row.project_id, row.status, row.impact, row.title)
                )

        dependencies = self.session.scalars(
            select(DependencyORM).where(
                DependencyORM.tenant_id == tenant_id,
                DependencyORM.project_id.in_(project_ids),
                DependencyORM.status.notin_(
                    [
                        DependencyStatus.SATISFIED.value,
                        DependencyStatus.WAIVED.value,
                        DependencyStatus.CLOSED.value,
                    ]
                ),
            )
        ).all()
        for row in dependencies:
            key = self._normalize_title(row.title)
            if key:
                groups[("dependency", key)].append(
                    (row.project_id, row.status, row.criticality, row.title)
                )

        signals: list[CrossProjectSignal] = []
        for (signal_type, _normalized_title), entries in groups.items():
            distinct_project_ids = sorted(
                {project_id for project_id, _, _, _ in entries},
                key=str,
            )
            if len(distinct_project_ids) < 2:
                continue

            title = entries[0][3]
            project_names = [
                cards_by_id[project_id].name
                for project_id in distinct_project_ids
                if project_id in cards_by_id
            ]
            statuses = sorted({status for _, status, _, _ in entries})
            severity_labels = sorted(
                {
                    severity
                    for _, _, severity, _ in entries
                    if severity is not None and severity.strip()
                }
            )

            signals.append(
                CrossProjectSignal(
                    signal_type=signal_type,
                    title=title,
                    project_count=len(distinct_project_ids),
                    project_ids=distinct_project_ids,
                    project_names=project_names,
                    statuses=statuses,
                    severity_labels=severity_labels,
                    explanation=(
                        f"The same active {signal_type} title appears in "
                        f"{len(distinct_project_ids)} authorized projects."
                    ),
                )
            )

        return sorted(
            signals,
            key=lambda item: (
                -item.project_count,
                item.signal_type,
                item.title.casefold(),
            ),
        )[:20]

    @staticmethod
    def _normalize_title(value: str) -> str:
        return re.sub(r"[^a-z0-9]+", " ", value.casefold()).strip()
