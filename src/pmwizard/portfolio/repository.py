"""Program/Portfolio structure persistence."""

from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from pmwizard.models import Portfolio, Program, Project, Provenance
from pmwizard.persistence.orm import PortfolioORM, ProgramORM, ProjectORM


class StructureRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def create_portfolio(
        self,
        *,
        tenant_id: UUID,
        portfolio: Portfolio,
    ) -> Portfolio:
        row = PortfolioORM(
            id=portfolio.id or uuid4(),
            tenant_id=tenant_id,
            name=portfolio.name,
            description=portfolio.description,
            owner_id=portfolio.owner_id,
            status=portfolio.status,
            start_date=portfolio.start_date,
            end_date=portfolio.end_date,
            strategic_objectives=portfolio.strategic_objectives,
            source_system=portfolio.source_system,
            external_id=portfolio.external_id,
            provenance=portfolio.provenance.model_dump(mode="json"),
            created_at=portfolio.created_at,
            updated_at=portfolio.updated_at,
        )
        self.session.add(row)
        self.session.flush()
        return self._portfolio(row)

    def create_program(
        self,
        *,
        tenant_id: UUID,
        program: Program,
    ) -> Program:
        if program.portfolio_id is not None:
            portfolio = self.get_portfolio(tenant_id, program.portfolio_id)
            if portfolio is None:
                raise LookupError("Portfolio not found for tenant")

        row = ProgramORM(
            id=program.id or uuid4(),
            tenant_id=tenant_id,
            portfolio_id=program.portfolio_id,
            name=program.name,
            description=program.description,
            program_manager_id=program.program_manager_id,
            status=program.status,
            start_date=program.start_date,
            end_date=program.end_date,
            objectives=program.objectives,
            source_system=program.source_system,
            external_id=program.external_id,
            provenance=program.provenance.model_dump(mode="json"),
            created_at=program.created_at,
            updated_at=program.updated_at,
        )
        self.session.add(row)
        self.session.flush()
        return self._program(row)

    def get_portfolio(
        self,
        tenant_id: UUID,
        portfolio_id: UUID,
    ) -> Portfolio | None:
        row = self.session.scalar(
            select(PortfolioORM).where(
                PortfolioORM.tenant_id == tenant_id,
                PortfolioORM.id == portfolio_id,
            )
        )
        return self._portfolio(row) if row is not None else None

    def get_program(
        self,
        tenant_id: UUID,
        program_id: UUID,
    ) -> Program | None:
        row = self.session.scalar(
            select(ProgramORM).where(
                ProgramORM.tenant_id == tenant_id,
                ProgramORM.id == program_id,
            )
        )
        return self._program(row) if row is not None else None

    def assign_project(
        self,
        *,
        tenant_id: UUID,
        project_id: UUID,
        program_id: UUID | None = None,
        portfolio_id: UUID | None = None,
    ) -> Project:
        row = self.session.scalar(
            select(ProjectORM).where(
                ProjectORM.tenant_id == tenant_id,
                ProjectORM.id == project_id,
            )
        )
        if row is None:
            raise LookupError("Project not found for tenant")

        program = None
        if program_id is not None:
            program = self.get_program(tenant_id, program_id)
            if program is None:
                raise LookupError("Program not found for tenant")

        resolved_portfolio_id = portfolio_id
        if resolved_portfolio_id is None and program is not None:
            resolved_portfolio_id = program.portfolio_id

        if resolved_portfolio_id is not None:
            if self.get_portfolio(tenant_id, resolved_portfolio_id) is None:
                raise LookupError("Portfolio not found for tenant")

        if (
            program is not None
            and program.portfolio_id is not None
            and resolved_portfolio_id is not None
            and program.portfolio_id != resolved_portfolio_id
        ):
            raise ValueError(
                "Project portfolio must match the selected Program portfolio"
            )

        row.program_id = program_id
        row.portfolio_id = resolved_portfolio_id
        row.updated_at = datetime.now(timezone.utc)
        self.session.flush()
        return self._project(row)

    def list_program_rows(
        self,
        *,
        tenant_id: UUID,
        program_ids: set[UUID],
    ) -> list[ProgramORM]:
        if not program_ids:
            return []
        return list(
            self.session.scalars(
                select(ProgramORM).where(
                    ProgramORM.tenant_id == tenant_id,
                    ProgramORM.id.in_(program_ids),
                )
            ).all()
        )

    def list_portfolio_rows(
        self,
        *,
        tenant_id: UUID,
        portfolio_ids: set[UUID],
    ) -> list[PortfolioORM]:
        if not portfolio_ids:
            return []
        return list(
            self.session.scalars(
                select(PortfolioORM).where(
                    PortfolioORM.tenant_id == tenant_id,
                    PortfolioORM.id.in_(portfolio_ids),
                )
            ).all()
        )

    def list_project_rows(
        self,
        *,
        tenant_id: UUID,
        project_ids: set[UUID],
    ) -> list[ProjectORM]:
        if not project_ids:
            return []
        return list(
            self.session.scalars(
                select(ProjectORM)
                .where(
                    ProjectORM.tenant_id == tenant_id,
                    ProjectORM.id.in_(project_ids),
                )
                .order_by(ProjectORM.name, ProjectORM.id)
            ).all()
        )

    @staticmethod
    def _portfolio(row: PortfolioORM) -> Portfolio:
        return Portfolio(
            id=row.id,
            name=row.name,
            description=row.description,
            owner_id=row.owner_id,
            status=row.status,
            start_date=row.start_date,
            end_date=row.end_date,
            strategic_objectives=row.strategic_objectives,
            source_system=row.source_system,
            external_id=row.external_id,
            created_at=row.created_at,
            updated_at=row.updated_at,
            provenance=Provenance.model_validate(row.provenance),
        )

    @staticmethod
    def _program(row: ProgramORM) -> Program:
        return Program(
            id=row.id,
            portfolio_id=row.portfolio_id,
            name=row.name,
            description=row.description,
            program_manager_id=row.program_manager_id,
            status=row.status,
            start_date=row.start_date,
            end_date=row.end_date,
            objectives=row.objectives,
            source_system=row.source_system,
            external_id=row.external_id,
            created_at=row.created_at,
            updated_at=row.updated_at,
            provenance=Provenance.model_validate(row.provenance),
        )

    @staticmethod
    def _project(row: ProjectORM) -> Project:
        return Project(
            id=row.id,
            name=row.name,
            description=row.description,
            objective=row.objective,
            portfolio_id=row.portfolio_id,
            program_id=row.program_id,
            project_manager_id=row.project_manager_id,
            sponsor_id=row.sponsor_id,
            methodology=row.methodology,
            industry=row.industry,
            lifecycle_phase=row.lifecycle_phase,
            status=row.status,
            priority=row.priority,
            start_date=row.start_date,
            planned_end_date=row.planned_end_date,
            forecast_end_date=row.forecast_end_date,
            actual_end_date=row.actual_end_date,
            business_value=row.business_value,
            source_system=row.source_system,
            external_id=row.external_id,
            created_at=row.created_at,
            updated_at=row.updated_at,
            provenance=Provenance.model_validate(row.provenance),
        )
