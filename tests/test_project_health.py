"""Tests for explainable deterministic Project Health V0."""

from datetime import date, datetime, timezone
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from pmwizard.api import create_app
from pmwizard.health import HealthBand, evaluate_project_health
from pmwizard.memory import ProjectMemorySnapshot, ProjectMemorySummary
from pmwizard.models import (
    ActionItem,
    Assumption,
    Decision,
    Dependency,
    Issue,
    Project,
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
from pmwizard.persistence import Base, ProjectMemoryService
from pmwizard.sources import (
    SourceConnectionView,
    SourceHealthStatus,
    SourcesSummary,
    SourcesWorkspaceSnapshot,
)


AS_OF = date(2026, 10, 23)
NOW = datetime(2026, 10, 23, 12, 0, tzinfo=timezone.utc)


def _memory(
    *,
    project: Project | None = None,
    actions: list[ActionItem] | None = None,
    risks: list[Risk] | None = None,
    assumptions: list[Assumption] | None = None,
    issues: list[Issue] | None = None,
    dependencies: list[Dependency] | None = None,
    decisions: list[Decision] | None = None,
) -> ProjectMemorySnapshot:
    project = project or Project(name="Health Demo")
    return ProjectMemorySnapshot(
        project=project,
        summary=ProjectMemorySummary(
            action_items_total=len(actions or []),
            action_items_open=0,
            action_items_blocked=0,
            risks_open=0,
            assumptions_open=0,
            issues_open=0,
            dependencies_open=0,
            decisions_total=len(decisions or []),
            decisions_approved=0,
        ),
        action_items=actions or [],
        risks=risks or [],
        assumptions=assumptions or [],
        issues=issues or [],
        dependencies=dependencies or [],
        decisions=decisions or [],
    )


def _sources(
    project_id: UUID,
    *healths: SourceHealthStatus,
) -> SourcesWorkspaceSnapshot:
    connections = [
        SourceConnectionView(
            id=uuid4(),
            connector_key=f"source:{index}:v0",
            source_type="email",
            source_system="synthetic",
            display_name=f"Source {index}",
            permission_scope=["project:read"],
            safe_config={},
            is_enabled=True,
            health=health,
            checkpoint_present=health != SourceHealthStatus.NEVER_SYNCED,
            checkpoint_fingerprint=None,
            checkpoint_updated_at=None,
            latest_run=None,
            recent_runs=[],
        )
        for index, health in enumerate(healths)
    ]
    return SourcesWorkspaceSnapshot(
        project_id=project_id,
        summary=SourcesSummary(
            total=len(connections),
            healthy=sum(item.health == SourceHealthStatus.HEALTHY for item in connections),
            attention=sum(item.health == SourceHealthStatus.ATTENTION for item in connections),
            failed=sum(item.health == SourceHealthStatus.FAILED for item in connections),
            never_synced=sum(
                item.health == SourceHealthStatus.NEVER_SYNCED for item in connections
            ),
            disabled=0,
            total_ingested=0,
            total_skipped=0,
            total_errors=0,
        ),
        sources=connections,
    )


def test_full_stable_project_is_green_with_full_coverage() -> None:
    project = Project(
        name="Stable Project",
        planned_end_date=date(2026, 12, 1),
        forecast_end_date=date(2026, 12, 1),
    )
    memory = _memory(
        project=project,
        actions=[
            ActionItem(
                project_id=project.id,
                title="Complete architecture",
                status=ActionItemStatus.COMPLETED,
                due_date=date(2026, 10, 20),
            ),
            ActionItem(
                project_id=project.id,
                title="Prepare rollout",
                status=ActionItemStatus.IN_PROGRESS,
                due_date=date(2026, 11, 10),
            ),
        ],
        risks=[
            Risk(
                project_id=project.id,
                title="Minor adoption risk",
                status=RiskStatus.MITIGATING,
                impact="low",
            )
        ],
        assumptions=[
            Assumption(
                project_id=project.id,
                title="Team capacity remains available",
                status=AssumptionStatus.VALIDATED,
            )
        ],
        issues=[
            Issue(
                project_id=project.id,
                title="Resolved setup issue",
                status=IssueStatus.RESOLVED,
                severity="low",
            )
        ],
        dependencies=[
            Dependency(
                project_id=project.id,
                title="Platform access",
                status=DependencyStatus.SATISFIED,
            )
        ],
        decisions=[
            Decision(
                project_id=project.id,
                title="Use modular monolith",
                status=DecisionStatus.APPROVED,
            )
        ],
    )
    sources = _sources(project.id, SourceHealthStatus.HEALTHY)

    result = evaluate_project_health(memory, sources, as_of=AS_OF)

    assert result.score == 100
    assert result.band == HealthBand.GREEN
    assert result.coverage_percent == 100
    assert result.coverage_band == "high"
    assert all(factor.available for factor in result.factors)
    assert result.key_drivers == []


def test_red_project_explains_each_negative_factor() -> None:
    project = Project(
        name="At Risk",
        planned_end_date=date(2026, 9, 1),
        forecast_end_date=date(2026, 11, 15),
    )
    memory = _memory(
        project=project,
        actions=[
            ActionItem(
                project_id=project.id,
                title="Blocked legal approval",
                status=ActionItemStatus.BLOCKED,
                due_date=date(2026, 10, 1),
            ),
            ActionItem(
                project_id=project.id,
                title="Vendor delivery",
                status=ActionItemStatus.PENDING_EXTERNAL,
                due_date=date(2026, 10, 10),
            ),
        ],
        risks=[
            Risk(
                project_id=project.id,
                title="Provider outage",
                status=RiskStatus.MATERIALIZED,
                impact="critical",
            )
        ],
        assumptions=[
            Assumption(
                project_id=project.id,
                title="API capacity",
                status=AssumptionStatus.INVALIDATED,
            )
        ],
        issues=[
            Issue(
                project_id=project.id,
                title="Legal blocker",
                status=IssueStatus.BLOCKED,
                severity="high",
            )
        ],
        dependencies=[
            Dependency(
                project_id=project.id,
                title="External approval",
                status=DependencyStatus.BLOCKED,
                criticality="high",
            )
        ],
        decisions=[
            Decision(
                project_id=project.id,
                title="Select vendor",
                status=DecisionStatus.PENDING,
                review_date=date(2026, 10, 1),
            ),
            Decision(
                project_id=project.id,
                title="Approve rollout model",
                status=DecisionStatus.PROPOSED,
            ),
        ],
    )
    sources = _sources(project.id, SourceHealthStatus.FAILED)

    result = evaluate_project_health(memory, sources, as_of=AS_OF)

    assert result.band == HealthBand.RED
    assert result.score is not None
    assert result.score < 60
    assert result.coverage_percent == 100

    factor_scores = {factor.key: factor.score for factor in result.factors}
    assert factor_scores["delivery"] < 60
    assert factor_scores["raid"] < 60
    assert factor_scores["decisions"] < 80
    assert factor_scores["sources"] == 20

    titles = {driver.title for driver in result.key_drivers}
    assert "Blocked Action Items" in titles
    assert "Materialized Risks" in titles
    assert "Failed Source Connections" in titles


def test_missing_dimensions_reduce_coverage_instead_of_inflating_score() -> None:
    project = Project(name="Sparse Project")
    memory = _memory(
        project=project,
        decisions=[
            Decision(
                project_id=project.id,
                title="Pending architecture choice",
                status=DecisionStatus.PENDING,
            )
        ],
    )

    result = evaluate_project_health(
        memory,
        _sources(project.id),
        as_of=AS_OF,
    )

    assert result.score == 90
    assert result.coverage_percent == 15
    assert result.coverage_band == "low"
    assert result.band == HealthBand.INSUFFICIENT_DATA
    assert "Provisional score 90/100" in result.explanation

    unavailable = {
        factor.key
        for factor in result.factors
        if not factor.available
    }
    assert unavailable == {"delivery", "raid", "sources"}


def test_no_operational_data_returns_no_score() -> None:
    project = Project(name="New Project")
    result = evaluate_project_health(
        _memory(project=project),
        _sources(project.id),
        as_of=AS_OF,
    )

    assert result.score is None
    assert result.band == HealthBand.INSUFFICIENT_DATA
    assert result.coverage_percent == 0
    assert result.available_weight == 0


def test_sources_factor_averages_enabled_connection_health() -> None:
    project = Project(name="Source Mix")
    memory = _memory(
        project=project,
        actions=[
            ActionItem(
                project_id=project.id,
                title="Active work",
                status=ActionItemStatus.IN_PROGRESS,
            )
        ],
    )
    sources = _sources(
        project.id,
        SourceHealthStatus.HEALTHY,
        SourceHealthStatus.ATTENTION,
        SourceHealthStatus.FAILED,
    )

    result = evaluate_project_health(memory, sources, as_of=AS_OF)
    source_factor = next(factor for factor in result.factors if factor.key == "sources")

    assert source_factor.score == 62
    assert source_factor.band == HealthBand.AMBER
    assert {signal.title for signal in source_factor.signals} == {
        "Failed Source Connections",
        "Sources Need Attention",
    }


@pytest.fixture()
def api_env():
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
    app = create_app(factory, allow_trusted_headers=True)
    with TestClient(app) as client:
        yield client, factory


def _headers(
    tenant_id: UUID,
    user_id: UUID,
    *permissions: str,
) -> dict[str, str]:
    return {
        "X-PMWizard-Tenant-ID": str(tenant_id),
        "X-PMWizard-User-ID": str(user_id),
        "X-PMWizard-Permissions": ",".join(permissions),
    }


def test_health_api_requires_project_read(api_env) -> None:
    client, factory = api_env
    tenant_id = uuid4()
    user_id = uuid4()

    with factory() as session:
        project = ProjectMemoryService(session).create_project(
            tenant_id,
            Project(name="API Health"),
        )

    response = client.get(
        f"/v1/projects/{project.id}/health",
        headers=_headers(tenant_id, user_id),
    )

    assert response.status_code == 403
    assert "project:read" in response.json()["detail"]


def test_health_api_returns_insufficient_data_for_new_project(api_env) -> None:
    client, factory = api_env
    tenant_id = uuid4()
    user_id = uuid4()

    with factory() as session:
        project = ProjectMemoryService(session).create_project(
            tenant_id,
            Project(name="New API Project"),
        )

    response = client.get(
        f"/v1/projects/{project.id}/health",
        headers=_headers(tenant_id, user_id, "project:read"),
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["project_name"] == "New API Project"
    assert payload["score"] is None
    assert payload["band"] == "insufficient_data"
    assert payload["coverage_percent"] == 0


def test_health_api_is_tenant_scoped(api_env) -> None:
    client, factory = api_env
    tenant_id = uuid4()
    user_id = uuid4()

    with factory() as session:
        project = ProjectMemoryService(session).create_project(
            tenant_id,
            Project(name="Tenant Project"),
        )

    response = client.get(
        f"/v1/projects/{project.id}/health",
        headers=_headers(uuid4(), user_id, "project:read"),
    )

    assert response.status_code == 404
    assert response.json()["detail"] == "Project not found for tenant"
