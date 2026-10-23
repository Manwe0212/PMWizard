"""Application service for Program and Portfolio structure."""

from __future__ import annotations

from uuid import UUID

from sqlalchemy.orm import Session

from pmwizard.models import Portfolio, Program, Project

from .repository import StructureRepository


class StructureService:
    def __init__(self, session: Session) -> None:
        self.session = session
        self.repository = StructureRepository(session)

    def create_portfolio(
        self,
        *,
        tenant_id: UUID,
        portfolio: Portfolio,
    ) -> Portfolio:
        created = self.repository.create_portfolio(
            tenant_id=tenant_id,
            portfolio=portfolio,
        )
        self.session.commit()
        return created

    def create_program(
        self,
        *,
        tenant_id: UUID,
        program: Program,
    ) -> Program:
        created = self.repository.create_program(
            tenant_id=tenant_id,
            program=program,
        )
        self.session.commit()
        return created

    def assign_project(
        self,
        *,
        tenant_id: UUID,
        project_id: UUID,
        program_id: UUID | None = None,
        portfolio_id: UUID | None = None,
    ) -> Project:
        project = self.repository.assign_project(
            tenant_id=tenant_id,
            project_id=project_id,
            program_id=program_id,
            portfolio_id=portfolio_id,
        )
        self.session.commit()
        return project
