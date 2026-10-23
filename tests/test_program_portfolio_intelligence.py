"""Tests for Program & Portfolio Intelligence V0."""

from datetime import date, datetime, timedelta, timezone
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from pmwizard.api import create_app
from pmwizard.auth import AccessTokenService, AuthService, AuthSettings
from pmwizard.health import ProjectHealthHistoryService
from pmwizard.models import ActionItem, Portfolio, Program, Project
from pmwizard.models.enums import ActionItemStatus
from pmwizard.persistence import Base, ProjectMemoryService
from pmwizard.persistence.orm import DependencyORM, RiskORM
from pmwizard.portfolio import (
    ProgramPortfolioIntelligenceService,
    StructureService,
)


AUTH_SETTINGS = AuthSettings(
    secret_key="pmwizard-program-portfolio-test-secret-key-32",
)
NOW = datetime(2026, 10, 23, 14, 0, tzinfo=timezone.utc)


@pytest.fixture()
def portfolio_env():
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    factory = sessionmaker(
        bind=engine,
        class_=Session,
        expire_on_commit=False,
    )
    app = create_app(
        factory,
        auth_settings=AUTH_SETTINGS,
        allow_trusted_headers=True,
    )
    with TestClient(app) as client:
        yield client, factory


def _seed(factory):
    tenant_id = uuid4()

    with factory() as session:
        structure = StructureService(session)
        portfolio = structure.create_portfolio(
            tenant_id=tenant_id,
            portfolio=Portfolio(
                name="Transformation Portfolio",
                status="active",
                strategic_objectives=[
                    "Modernize delivery",
                    "Reduce operational risk",
                ],
            ),
        )
        program = structure.create_program(
            tenant_id=tenant_id,
            program=Program(
                portfolio_id=portfolio.id,
                name="Digital Program",
                status="active",
            ),
        )

        memory = ProjectMemoryService(session)
        project_green = memory.create_project(
            tenant_id,
            Project(
                name="Alpha",
                status="active",
                priority="high",
                planned_end_date=date(2026, 12, 1),
                forecast_end_date=date(2026, 12, 1),
            ),
        )
        project_red = memory.create_project(
            tenant_id,
            Project(
                name="Beta",
                status="active",
                priority="critical",
                planned_end_date=date(2026, 12, 15),
                forecast_end_date=date(2026, 12, 15),
            ),
        )
        hidden_project = memory.create_project(
            tenant_id,
            Project(
                name="Hidden",
                status="active",
                planned_end_date=date(2026, 12, 20),
                forecast_end_date=date(2026, 12, 20),
            ),
        )

        for project in (project_green, project_red, hidden_project):
            structure.assign_project(
                tenant_id=tenant_id,
                project_id=project.id,
                program_id=program.id,
            )

        green_action = memory.add_action_item(
            tenant_id,
            ActionItem(
                project_id=project_green.id,
                title="Prepare release",
                status=ActionItemStatus.IN_PROGRESS,
                due_date=date(2026, 11, 15),
            ),
        )
        red_action = memory.add_action_item(
            tenant_id,
            ActionItem(
                project_id=project_red.id,
                title="Legal approval",
                status=ActionItemStatus.IN_PROGRESS,
                due_date=date(2026, 11, 10),
            ),
        )
        memory.add_action_item(
            tenant_id,
            ActionItem(
                project_id=hidden_project.id,
                title="Hidden action",
                status=ActionItemStatus.BLOCKED,
                due_date=date(2026, 10, 1),
            ),
        )

        common = {
            "tenant_id": tenant_id,
            "created_at": NOW,
            "updated_at": NOW,
            "provenance": {},
        }
        session.add_all(
            [
                RiskORM(
                    id=uuid4(),
                    project_id=project_green.id,
                    title="Vendor capacity",
                    impact="high",
                    status="mitigating",
                    **common,
                ),
                RiskORM(
                    id=uuid4(),
                    project_id=project_red.id,
                    title="Vendor-capacity",
                    impact="high",
                    status="open",
                    **common,
                ),
                RiskORM(
                    id=uuid4(),
                    project_id=hidden_project.id,
                    title="Vendor capacity",
                    impact="critical",
                    status="materialized",
                    **common,
                ),
                DependencyORM(
                    id=uuid4(),
                    project_id=project_green.id,
                    title="Security approval",
                    criticality="high",
                    status="open",
                    **common,
                ),
                DependencyORM(
                    id=uuid4(),
                    project_id=project_red.id,
                    title="Security Approval",
                    criticality="high",
                    status="blocked",
                    **common,
                ),
            ]
        )
        session.commit()

        history = ProjectHealthHistoryService(session)
        history.capture(
            tenant_id=tenant_id,
            project_id=project_green.id,
            captured_by=None,
            capture_source="test",
            captured_at=NOW,
        )
        history.capture(
            tenant_id=tenant_id,
            project_id=project_green.id,
            captured_by=None,
            capture_source="test",
            captured_at=NOW + timedelta(hours=4),
        )

        history.capture(
            tenant_id=tenant_id,
            project_id=project_red.id,
            captured_by=None,
            capture_source="test",
            captured_at=NOW,
        )

        from pmwizard.persistence.orm import ActionItemORM
        row = session.get(ActionItemORM, red_action.id)
        assert row is not None
        row.status = ActionItemStatus.BLOCKED.value
        row.due_date = date(2026, 10, 1)
        session.commit()

        history.capture(
            tenant_id=tenant_id,
            project_id=project_red.id,
            captured_by=None,
            capture_source="test",
            captured_at=NOW + timedelta(days=1),
        )

        auth = AuthService(session, AccessTokenService(AUTH_SETTINGS))
        user = auth.create_user(
            tenant_id=tenant_id,
            email="portfolio@example.com",
            display_name="Portfolio Lead",
            password="A secure portfolio password!",
        )
        for project in (project_green, project_red):
            auth.grant_project_access(
                tenant_id=tenant_id,
                user_id=user.id,
                project_id=project.id,
                role="program_manager",
                permissions=["project:read", "project:review"],
            )

        no_read_user = auth.create_user(
            tenant_id=tenant_id,
            email="noread@example.com",
            display_name="No Read",
            password="Another secure password!",
        )
        auth.grant_project_access(
            tenant_id=tenant_id,
            user_id=no_read_user.id,
            project_id=project_green.id,
            role="observer",
            permissions=["project:review"],
        )

    return {
        "tenant_id": tenant_id,
        "portfolio": portfolio,
        "program": program,
        "green": project_green,
        "red": project_red,
        "hidden": hidden_project,
        "user": user,
        "no_read_user": no_read_user,
    }


def _login(client, tenant_id, email, password):
    response = client.post(
        "/v1/auth/login",
        json={
            "tenant_id": str(tenant_id),
            "email": email,
            "password": password,
        },
    )
    assert response.status_code == 200
    return response.json()["access_token"]


def test_structure_service_assigns_program_and_inherits_portfolio(
    portfolio_env,
) -> None:
    _, factory = portfolio_env
    seeded = _seed(factory)

    with factory() as session:
        from pmwizard.persistence.orm import ProjectORM
        row = session.get(ProjectORM, seeded["green"].id)

    assert row is not None
    assert row.program_id == seeded["program"].id
    assert row.portfolio_id == seeded["portfolio"].id


def test_overview_rolls_up_only_authorized_projects(portfolio_env) -> None:
    _, factory = portfolio_env
    seeded = _seed(factory)

    with factory() as session:
        overview = ProgramPortfolioIntelligenceService(session).overview(
            tenant_id=seeded["tenant_id"],
            authorized_project_ids={
                seeded["green"].id,
                seeded["red"].id,
            },
        )

    assert overview.summary.projects_total == 2
    assert overview.summary.projects_scored == 2
    assert overview.summary.amber + overview.summary.red + overview.summary.green == 2
    assert overview.summary.deteriorating == 1
    assert overview.summary.stable == 1

    assert len(overview.portfolios) == 1
    portfolio = overview.portfolios[0]
    assert portfolio.name == "Transformation Portfolio"
    assert len(portfolio.programs) == 1

    program = portfolio.programs[0]
    assert program.name == "Digital Program"
    assert {project.name for project in program.projects} == {"Alpha", "Beta"}
    assert "Hidden" not in {project.name for project in program.projects}


def test_attention_projects_prioritize_deteriorating_red_project(
    portfolio_env,
) -> None:
    _, factory = portfolio_env
    seeded = _seed(factory)

    with factory() as session:
        overview = ProgramPortfolioIntelligenceService(session).overview(
            tenant_id=seeded["tenant_id"],
            authorized_project_ids={
                seeded["green"].id,
                seeded["red"].id,
            },
        )

    assert overview.attention_projects[0].name == "Beta"
    assert overview.attention_projects[0].trend_direction == "deteriorating"
    assert overview.attention_projects[0].health_band == "red"
    assert overview.attention_projects[1].name == "Alpha"


def test_cross_project_signals_require_same_active_normalized_title(
    portfolio_env,
) -> None:
    _, factory = portfolio_env
    seeded = _seed(factory)

    with factory() as session:
        overview = ProgramPortfolioIntelligenceService(session).overview(
            tenant_id=seeded["tenant_id"],
            authorized_project_ids={
                seeded["green"].id,
                seeded["red"].id,
            },
        )

    signals = {
        (signal.signal_type, signal.title): signal
        for signal in overview.cross_project_signals
    }

    risk = next(
        signal
        for signal in overview.cross_project_signals
        if signal.signal_type == "risk"
    )
    assert risk.project_count == 2
    assert set(risk.project_names) == {"Alpha", "Beta"}
    assert "Hidden" not in risk.project_names
    assert risk.severity_labels == ["high"]

    dependency = next(
        signal
        for signal in overview.cross_project_signals
        if signal.signal_type == "dependency"
    )
    assert dependency.project_count == 2
    assert set(dependency.project_names) == {"Alpha", "Beta"}
    assert set(dependency.statuses) == {"blocked", "open"}


def test_rollup_does_not_turn_sparse_portfolio_green(portfolio_env) -> None:
    _, factory = portfolio_env
    tenant_id = uuid4()

    with factory() as session:
        structure = StructureService(session)
        portfolio = structure.create_portfolio(
            tenant_id=tenant_id,
            portfolio=Portfolio(name="Sparse Portfolio"),
        )
        memory = ProjectMemoryService(session)
        projects = [
            memory.create_project(tenant_id, Project(name=f"Sparse {index}"))
            for index in range(3)
        ]
        for project in projects:
            structure.assign_project(
                tenant_id=tenant_id,
                project_id=project.id,
                portfolio_id=portfolio.id,
            )

        # Only one project has enough delivery data to calculate a score.
        memory.add_action_item(
            tenant_id,
            ActionItem(
                project_id=projects[0].id,
                title="Healthy action",
                status=ActionItemStatus.IN_PROGRESS,
                due_date=date(2026, 12, 1),
            ),
        )

        overview = ProgramPortfolioIntelligenceService(session).overview(
            tenant_id=tenant_id,
            authorized_project_ids={project.id for project in projects},
        )

    assert overview.summary.score == 100
    assert overview.summary.average_coverage_percent == 12
    assert overview.summary.band == "insufficient_data"
    assert overview.summary.projects_scored == 1


def test_bearer_api_returns_only_memberships_with_project_read(
    portfolio_env,
) -> None:
    client, factory = portfolio_env
    seeded = _seed(factory)
    token = _login(
        client,
        seeded["tenant_id"],
        "portfolio@example.com",
        "A secure portfolio password!",
    )

    response = client.get(
        "/v1/intelligence/overview",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["summary"]["projects_total"] == 2
    names = {
        project["name"]
        for portfolio in payload["portfolios"]
        for program in portfolio["programs"]
        for project in program["projects"]
    }
    assert names == {"Alpha", "Beta"}


def test_membership_without_project_read_is_excluded(portfolio_env) -> None:
    client, factory = portfolio_env
    seeded = _seed(factory)
    token = _login(
        client,
        seeded["tenant_id"],
        "noread@example.com",
        "Another secure password!",
    )

    response = client.get(
        "/v1/intelligence/overview",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["summary"]["projects_total"] == 0
    assert payload["portfolios"] == []
    assert payload["cross_project_signals"] == []


def test_trusted_headers_cannot_enumerate_cross_project_intelligence(
    portfolio_env,
) -> None:
    client, factory = portfolio_env
    seeded = _seed(factory)

    response = client.get(
        "/v1/intelligence/overview",
        headers={
            "X-PMWizard-Tenant-ID": str(seeded["tenant_id"]),
            "X-PMWizard-User-ID": str(uuid4()),
            "X-PMWizard-Permissions": "project:read",
        },
    )

    assert response.status_code == 400
    assert "Bearer authentication" in response.json()["detail"]
