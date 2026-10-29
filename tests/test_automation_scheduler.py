"""Tests for durable Automation & Scheduler V0."""

from datetime import datetime, timedelta, timezone
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from pmwizard.api import create_app
from pmwizard.automation import (
    AutomationExecutor,
    AutomationRepository,
    AutomationRunStatus,
    AutomationScheduleService,
    AutomationTaskType,
    AutomationTrigger,
    CreateAutomationScheduleRequest,
)
from pmwizard.automation.worker import AutomationWorker
from pmwizard.health import ProjectHealthHistoryService
from pmwizard.models import Project
from pmwizard.persistence import Base, ProjectMemoryService


NOW = datetime(2026, 10, 29, 22, 0, tzinfo=timezone.utc)


@pytest.fixture()
def automation_env():
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
    yield factory


def _seed_project(factory):
    tenant_id = uuid4()
    user_id = uuid4()
    with factory() as session:
        project = ProjectMemoryService(session).create_project(
            tenant_id,
            Project(name="Automation Demo"),
        )
    return tenant_id, user_id, project


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


def test_schedule_service_creates_durable_health_snapshot_schedule(
    automation_env,
) -> None:
    tenant_id, user_id, project = _seed_project(automation_env)

    with automation_env() as session:
        service = AutomationScheduleService(session)
        schedule = service.create(
            tenant_id=tenant_id,
            project_id=project.id,
            created_by=user_id,
            command=CreateAutomationScheduleRequest(
                name="Daily health snapshot",
                interval_minutes=1440,
            ),
            now=NOW,
        )
        snapshot = service.snapshot(
            tenant_id=tenant_id,
            project_id=project.id,
            now=NOW,
        )

    assert schedule.task_type == AutomationTaskType.HEALTH_SNAPSHOT
    assert schedule.next_run_at == NOW + timedelta(days=1)
    assert schedule.enabled is True
    assert snapshot.summary.total == 1
    assert snapshot.summary.enabled == 1
    assert snapshot.summary.running == 0
    assert snapshot.schedules[0].name == "Daily health snapshot"


def test_run_now_is_queued_and_worker_captures_health_snapshot(
    automation_env,
) -> None:
    tenant_id, user_id, project = _seed_project(automation_env)

    with automation_env() as session:
        service = AutomationScheduleService(session)
        schedule = service.create(
            tenant_id=tenant_id,
            project_id=project.id,
            created_by=user_id,
            command=CreateAutomationScheduleRequest(
                name="Daily health snapshot",
                interval_minutes=1440,
            ),
            now=NOW,
        )
        queued = service.run_now(
            tenant_id=tenant_id,
            project_id=project.id,
            schedule_id=schedule.id,
            now=NOW,
        )

    assert queued.queued is True
    assert queued.next_run_at == NOW

    worker = AutomationWorker(
        automation_env,
        worker_id="worker-a",
        lease_seconds=60,
    )
    results = worker.run_once(now=NOW)

    assert len(results) == 1
    assert results[0].status == AutomationRunStatus.SUCCESS
    assert results[0].trigger == AutomationTrigger.MANUAL
    assert results[0].summary["created"] is True
    assert results[0].summary["snapshot_id"]

    with automation_env() as session:
        history = ProjectHealthHistoryService(session).history(
            tenant_id=tenant_id,
            project_id=project.id,
            limit=2,
        )
        workspace = AutomationScheduleService(session).snapshot(
            tenant_id=tenant_id,
            project_id=project.id,
        )

    assert history.count == 1
    assert workspace.schedules[0].last_status == AutomationRunStatus.SUCCESS
    assert workspace.schedules[0].consecutive_failures == 0
    assert workspace.schedules[0].recent_runs[0].trigger == AutomationTrigger.MANUAL


def test_atomic_lease_prevents_two_workers_claiming_same_schedule(
    automation_env,
) -> None:
    tenant_id, user_id, project = _seed_project(automation_env)

    with automation_env() as session:
        schedule = AutomationScheduleService(session).create(
            tenant_id=tenant_id,
            project_id=project.id,
            created_by=user_id,
            command=CreateAutomationScheduleRequest(
                name="Due health snapshot",
                interval_minutes=60,
                start_at=NOW,
            ),
            now=NOW,
        )

    with automation_env() as first_session:
        first = AutomationRepository(first_session).claim_due(
            worker_id="worker-a",
            now=NOW,
            lease_seconds=60,
            limit=10,
        )

    with automation_env() as second_session:
        second = AutomationRepository(second_session).claim_due(
            worker_id="worker-b",
            now=NOW,
            lease_seconds=60,
            limit=10,
        )

    assert len(first) == 1
    assert first[0].schedule_id == schedule.id
    assert second == []


def test_expired_lease_abandons_stale_run_and_blocks_old_finalize(
    automation_env,
) -> None:
    tenant_id, user_id, project = _seed_project(automation_env)

    with automation_env() as session:
        schedule = AutomationScheduleService(session).create(
            tenant_id=tenant_id,
            project_id=project.id,
            created_by=user_id,
            command=CreateAutomationScheduleRequest(
                name="Recoverable snapshot",
                interval_minutes=60,
                start_at=NOW,
            ),
            now=NOW,
        )

    with automation_env() as session:
        repo = AutomationRepository(session)
        old_claim = repo.claim_due(
            worker_id="worker-old",
            now=NOW,
            lease_seconds=60,
            limit=1,
        )[0]
        stale_run = repo.start_run(
            claim=old_claim,
            worker_id="worker-old",
            now=NOW,
        )

    recovered_at = NOW + timedelta(seconds=61)
    with automation_env() as session:
        repo = AutomationRepository(session)
        new_claim = repo.claim_due(
            worker_id="worker-new",
            now=recovered_at,
            lease_seconds=60,
            limit=1,
        )[0]
        runs = repo.list_runs(
            tenant_id=tenant_id,
            project_id=project.id,
            schedule_id=schedule.id,
            limit=5,
        )

    stale = next(row for row in runs if row.id == stale_run.id)
    assert stale.status == AutomationRunStatus.ABANDONED.value
    assert stale.finished_at is not None
    assert "lease expired" in (stale.error_message or "")

    with automation_env() as session:
        repo = AutomationRepository(session)
        with pytest.raises(RuntimeError, match="lease was lost"):
            repo.finish_run(
                claim=old_claim,
                run_id=stale_run.id,
                status=AutomationRunStatus.SUCCESS,
                now=recovered_at,
                summary={"should": "not write"},
            )

    assert new_claim.lease_token != old_claim.lease_token


def test_missing_handler_records_failed_run_instead_of_crashing_schedule(
    automation_env,
) -> None:
    tenant_id, user_id, project = _seed_project(automation_env)

    with automation_env() as session:
        schedule = AutomationScheduleService(session).create(
            tenant_id=tenant_id,
            project_id=project.id,
            created_by=user_id,
            command=CreateAutomationScheduleRequest(
                name="Handler test",
                interval_minutes=60,
                start_at=NOW,
            ),
            now=NOW,
        )

    with automation_env() as session:
        claim = AutomationRepository(session).claim_due(
            worker_id="worker-a",
            now=NOW,
            lease_seconds=60,
            limit=1,
        )[0]

    with automation_env() as session:
        run = AutomationExecutor(session, handlers=[]).execute(
            claim=claim,
            worker_id="worker-a",
            now=NOW,
        )

    assert run.status == AutomationRunStatus.FAILED.value
    assert "No automation handler" in (run.error_message or "")

    with automation_env() as session:
        workspace = AutomationScheduleService(session).snapshot(
            tenant_id=tenant_id,
            project_id=project.id,
        )

    current = workspace.schedules[0]
    assert current.last_status == AutomationRunStatus.FAILED
    assert current.consecutive_failures == 1
    assert current.running is False


def test_disabled_schedule_is_not_claimed(
    automation_env,
) -> None:
    tenant_id, user_id, project = _seed_project(automation_env)

    with automation_env() as session:
        AutomationScheduleService(session).create(
            tenant_id=tenant_id,
            project_id=project.id,
            created_by=user_id,
            command=CreateAutomationScheduleRequest(
                name="Paused snapshot",
                interval_minutes=60,
                enabled=False,
                start_at=NOW,
            ),
            now=NOW,
        )

    worker = AutomationWorker(
        automation_env,
        worker_id="worker-a",
        lease_seconds=60,
    )
    assert worker.run_once(now=NOW) == []


def test_api_requires_review_permission_for_schedule_mutations(
    automation_env,
) -> None:
    tenant_id, user_id, project = _seed_project(automation_env)
    app = create_app(
        automation_env,
        allow_trusted_headers=True,
    )

    with TestClient(app) as client:
        denied = client.post(
            f"/v1/projects/{project.id}/automations",
            json={
                "name": "Daily health snapshot",
                "task_type": "health_snapshot",
                "interval_minutes": 1440,
            },
            headers=_headers(
                tenant_id,
                user_id,
                "project:read",
            ),
        )
        allowed = client.post(
            f"/v1/projects/{project.id}/automations",
            json={
                "name": "Daily health snapshot",
                "task_type": "health_snapshot",
                "interval_minutes": 1440,
            },
            headers=_headers(
                tenant_id,
                user_id,
                "project:read",
                "project:review",
            ),
        )
        visible = client.get(
            f"/v1/projects/{project.id}/automations",
            headers=_headers(
                tenant_id,
                user_id,
                "project:read",
            ),
        )

    assert denied.status_code == 403
    assert allowed.status_code == 201
    assert visible.status_code == 200
    assert visible.json()["summary"]["total"] == 1


def test_api_run_now_queues_manual_trigger(
    automation_env,
) -> None:
    tenant_id, user_id, project = _seed_project(automation_env)
    app = create_app(
        automation_env,
        allow_trusted_headers=True,
    )

    with TestClient(app) as client:
        created = client.post(
            f"/v1/projects/{project.id}/automations",
            json={
                "name": "Daily health snapshot",
                "task_type": "health_snapshot",
                "interval_minutes": 1440,
            },
            headers=_headers(
                tenant_id,
                user_id,
                "project:read",
                "project:review",
            ),
        )
        schedule_id = created.json()["id"]
        queued = client.post(
            f"/v1/projects/{project.id}/automations/{schedule_id}/run-now",
            headers=_headers(
                tenant_id,
                user_id,
                "project:read",
                "project:review",
            ),
        )

    assert queued.status_code == 200
    assert queued.json()["queued"] is True

    with automation_env() as session:
        row = AutomationRepository(session).get_schedule(
            tenant_id=tenant_id,
            project_id=project.id,
            schedule_id=UUID(schedule_id),
        )

    assert row is not None
    assert row.pending_trigger == AutomationTrigger.MANUAL.value
