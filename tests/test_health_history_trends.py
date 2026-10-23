"""Tests for Project Health History + Trends V0."""

from datetime import datetime, timedelta, timezone
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from pmwizard.api import create_app
from pmwizard.health import (
    ProjectHealthHistoryService,
    TrendDirection,
)
from pmwizard.models import ActionItem, Project
from pmwizard.models.enums import ActionItemStatus
from pmwizard.persistence import Base, ProjectMemoryService
from pmwizard.persistence.orm import ActionItemORM, ProjectHealthSnapshotORM


START = datetime(2026, 10, 23, 12, 0, tzinfo=timezone.utc)


@pytest.fixture()
def history_env():
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


def _seed_delivery_project(factory):
    tenant_id = uuid4()
    user_id = uuid4()
    with factory() as session:
        memory = ProjectMemoryService(session)
        project = memory.create_project(
            tenant_id,
            Project(
                name="Health Trend Demo",
                planned_end_date=START.date() + timedelta(days=30),
                forecast_end_date=START.date() + timedelta(days=30),
            ),
        )
        action = memory.add_action_item(
            tenant_id,
            ActionItem(
                project_id=project.id,
                title="Prepare launch",
                status=ActionItemStatus.IN_PROGRESS,
                due_date=START.date() + timedelta(days=10),
            ),
        )
    return tenant_id, user_id, project, action


def test_capture_persists_full_health_snapshot(history_env) -> None:
    _, factory = history_env
    tenant_id, user_id, project, _ = _seed_delivery_project(factory)

    with factory() as session:
        result = ProjectHealthHistoryService(session).capture(
            tenant_id=tenant_id,
            project_id=project.id,
            captured_by=user_id,
            captured_at=START,
        )

        assert result.created is True
        assert result.snapshot.score == 100
        assert result.snapshot.band == "green"
        assert result.snapshot.coverage_percent == 35
        assert result.snapshot.factor_scores["delivery"] == 100

        row = session.scalar(
            select(ProjectHealthSnapshotORM).where(
                ProjectHealthSnapshotORM.id == result.snapshot.id
            )
        )
        assert row is not None
        assert row.captured_by == user_id
        assert row.capture_source == "manual"
        assert row.model_version == "project-health-v0"
        assert row.snapshot_payload["project_name"] == "Health Trend Demo"
        assert len(row.state_fingerprint) == 64


def test_identical_snapshot_within_five_minutes_is_deduplicated(
    history_env,
) -> None:
    _, factory = history_env
    tenant_id, user_id, project, _ = _seed_delivery_project(factory)

    with factory() as session:
        service = ProjectHealthHistoryService(session)
        first = service.capture(
            tenant_id=tenant_id,
            project_id=project.id,
            captured_by=user_id,
            captured_at=START,
        )
        second = service.capture(
            tenant_id=tenant_id,
            project_id=project.id,
            captured_by=user_id,
            captured_at=START + timedelta(minutes=2),
        )
        history = service.history(
            tenant_id=tenant_id,
            project_id=project.id,
        )

    assert first.created is True
    assert second.created is False
    assert second.snapshot.id == first.snapshot.id
    assert history.count == 1


def test_identical_state_can_be_recorded_later_to_show_stability(
    history_env,
) -> None:
    _, factory = history_env
    tenant_id, user_id, project, _ = _seed_delivery_project(factory)

    with factory() as session:
        service = ProjectHealthHistoryService(session)
        first = service.capture(
            tenant_id=tenant_id,
            project_id=project.id,
            captured_by=user_id,
            captured_at=START,
        )
        second = service.capture(
            tenant_id=tenant_id,
            project_id=project.id,
            captured_by=user_id,
            captured_at=START + timedelta(hours=4),
        )
        history = service.history(
            tenant_id=tenant_id,
            project_id=project.id,
        )

    assert first.created is True
    assert second.created is True
    assert history.count == 2
    assert history.trend.direction == TrendDirection.STABLE
    assert history.trend.score_delta == 0
    assert history.trend.elapsed_hours == 4.0


def test_deteriorating_trend_identifies_new_delivery_drivers(
    history_env,
) -> None:
    _, factory = history_env
    tenant_id, user_id, project, action = _seed_delivery_project(factory)

    with factory() as session:
        service = ProjectHealthHistoryService(session)
        service.capture(
            tenant_id=tenant_id,
            project_id=project.id,
            captured_by=user_id,
            captured_at=START,
        )

        row = session.scalar(
            select(ActionItemORM).where(
                ActionItemORM.tenant_id == tenant_id,
                ActionItemORM.id == action.id,
            )
        )
        assert row is not None
        row.status = ActionItemStatus.BLOCKED.value
        row.due_date = START.date() - timedelta(days=2)
        session.commit()

        service.capture(
            tenant_id=tenant_id,
            project_id=project.id,
            captured_by=user_id,
            captured_at=START + timedelta(days=1),
        )
        history = service.history(
            tenant_id=tenant_id,
            project_id=project.id,
        )

    assert history.trend.direction == TrendDirection.DETERIORATING
    assert history.trend.score_delta is not None
    assert history.trend.score_delta <= -3
    assert history.trend.factor_deltas["delivery"] < 0
    assert set(history.trend.new_drivers) == {
        "Blocked Action Items",
        "Overdue Action Items",
    }
    assert history.trend.resolved_drivers == []


def test_improving_trend_identifies_resolved_drivers(history_env) -> None:
    _, factory = history_env
    tenant_id, user_id, project, action = _seed_delivery_project(factory)

    with factory() as session:
        row = session.scalar(
            select(ActionItemORM).where(
                ActionItemORM.tenant_id == tenant_id,
                ActionItemORM.id == action.id,
            )
        )
        assert row is not None
        row.status = ActionItemStatus.BLOCKED.value
        row.due_date = START.date() - timedelta(days=1)
        session.commit()

        service = ProjectHealthHistoryService(session)
        service.capture(
            tenant_id=tenant_id,
            project_id=project.id,
            captured_by=user_id,
            captured_at=START,
        )

        row.status = ActionItemStatus.COMPLETED.value
        row.completed_at = START + timedelta(hours=2)
        session.commit()

        service.capture(
            tenant_id=tenant_id,
            project_id=project.id,
            captured_by=user_id,
            captured_at=START + timedelta(days=1),
        )
        history = service.history(
            tenant_id=tenant_id,
            project_id=project.id,
        )

    assert history.trend.direction == TrendDirection.IMPROVING
    assert history.trend.score_delta is not None
    assert history.trend.score_delta >= 3
    assert history.trend.new_drivers == []
    assert set(history.trend.resolved_drivers) == {
        "Blocked Action Items",
        "Overdue Action Items",
    }


def test_single_snapshot_has_insufficient_history(history_env) -> None:
    _, factory = history_env
    tenant_id, user_id, project, _ = _seed_delivery_project(factory)

    with factory() as session:
        service = ProjectHealthHistoryService(session)
        service.capture(
            tenant_id=tenant_id,
            project_id=project.id,
            captured_by=user_id,
            captured_at=START,
        )
        history = service.history(
            tenant_id=tenant_id,
            project_id=project.id,
        )

    assert history.count == 1
    assert history.trend.direction == TrendDirection.INSUFFICIENT_HISTORY
    assert history.trend.score_delta is None


def test_history_limit_is_validated(history_env) -> None:
    _, factory = history_env
    tenant_id, _, project, _ = _seed_delivery_project(factory)

    with factory() as session:
        service = ProjectHealthHistoryService(session)
        with pytest.raises(ValueError, match="between 2 and 365"):
            service.history(
                tenant_id=tenant_id,
                project_id=project.id,
                limit=1,
            )


def test_history_api_requires_project_read(history_env) -> None:
    client, factory = history_env
    tenant_id, user_id, project, _ = _seed_delivery_project(factory)

    response = client.get(
        f"/v1/projects/{project.id}/health/history",
        headers=_headers(tenant_id, user_id),
    )

    assert response.status_code == 403
    assert "project:read" in response.json()["detail"]


def test_capture_api_requires_project_review(history_env) -> None:
    client, factory = history_env
    tenant_id, user_id, project, _ = _seed_delivery_project(factory)

    response = client.post(
        f"/v1/projects/{project.id}/health/snapshots",
        headers=_headers(tenant_id, user_id, "project:read"),
    )

    assert response.status_code == 403
    assert "project:review" in response.json()["detail"]


def test_capture_and_history_api_round_trip(history_env) -> None:
    client, factory = history_env
    tenant_id, user_id, project, _ = _seed_delivery_project(factory)
    headers = _headers(
        tenant_id,
        user_id,
        "project:read",
        "project:review",
    )

    capture = client.post(
        f"/v1/projects/{project.id}/health/snapshots",
        headers=headers,
    )
    history = client.get(
        f"/v1/projects/{project.id}/health/history",
        headers=headers,
    )

    assert capture.status_code == 200
    assert capture.json()["created"] is True
    assert history.status_code == 200
    assert history.json()["count"] == 1
    assert history.json()["points"][0]["id"] == capture.json()["snapshot"]["id"]


def test_history_is_tenant_scoped(history_env) -> None:
    client, factory = history_env
    _, user_id, project, _ = _seed_delivery_project(factory)

    response = client.get(
        f"/v1/projects/{project.id}/health/history",
        headers=_headers(uuid4(), user_id, "project:read"),
    )

    assert response.status_code == 404
    assert response.json()["detail"] == "Project not found for tenant"
