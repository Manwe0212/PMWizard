"""Tests for durable source observability and Sources Workspace V0."""

from datetime import datetime, timezone
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from pmwizard.api import create_app
from pmwizard.connectors import (
    ConnectorDescriptor,
    ConnectorPage,
    ConnectorRunStatus,
    ConnectorSkip,
    ConnectorTestResult,
    SourceConnector,
    SyntheticConnector,
)
from pmwizard.ingestion import SourceRecord
from pmwizard.models import Project
from pmwizard.persistence import Base, ProjectMemoryService
from pmwizard.persistence.orm import ConnectorCheckpointORM
from pmwizard.sources import (
    SourceHealthStatus,
    SourceTelemetryService,
    SourcesWorkspaceService,
    create_durable_connector_runner,
)


NOW = datetime(2026, 10, 22, 17, 0, tzinfo=timezone.utc)


@pytest.fixture()
def source_env():
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


def _record(project_id: UUID, external_id: str) -> SourceRecord:
    return SourceRecord(
        project_id=project_id,
        source_type="email",
        source_system="synthetic",
        external_id=external_id,
        source_reference=f"synthetic://{external_id}",
        author="pm@example.com",
        captured_at=NOW,
        content=f"Update {external_id}",
        permission_scope=["project:read"],
    )


def _project(factory, name="Sources Demo"):
    tenant_id = uuid4()
    reviewer_id = uuid4()
    with factory() as session:
        project = ProjectMemoryService(session).create_project(
            tenant_id,
            Project(name=name),
        )
    return tenant_id, reviewer_id, project


def test_durable_checkpoint_resumes_across_runner_instances(source_env) -> None:
    _, factory = source_env
    tenant_id, _, project = _project(factory)
    records = [_record(project.id, f"msg-{index}") for index in range(3)]
    connector = SyntheticConnector(records, connector_key="synthetic:durable:v0")

    with factory() as session:
        first = create_durable_connector_runner(session).run(
            tenant_id=tenant_id,
            project_id=project.id,
            connector=connector,
            page_size=2,
            max_pages=1,
        )

    with factory() as session:
        second = create_durable_connector_runner(session).run(
            tenant_id=tenant_id,
            project_id=project.id,
            connector=connector,
            page_size=2,
        )

    assert first.status == ConnectorRunStatus.PARTIAL
    assert first.end_cursor == "2"
    assert second.status == ConnectorRunStatus.SUCCESS
    assert second.start_cursor == "2"
    assert second.ingested == 1
    assert second.end_cursor == "3"


def test_sources_workspace_reports_healthy_source_without_exposing_cursor(
    source_env,
) -> None:
    client, factory = source_env
    tenant_id, reviewer_id, project = _project(factory)
    connector = SyntheticConnector(
        [_record(project.id, "msg-1")],
        connector_key="synthetic:healthy:v0",
    )

    with factory() as session:
        result = create_durable_connector_runner(session).run(
            tenant_id=tenant_id,
            project_id=project.id,
            connector=connector,
        )
        assert result.status == ConnectorRunStatus.SUCCESS

        checkpoint = session.scalar(
            select(ConnectorCheckpointORM).where(
                ConnectorCheckpointORM.tenant_id == tenant_id,
                ConnectorCheckpointORM.project_id == project.id,
                ConnectorCheckpointORM.connector_key == connector.connector_key,
            )
        )
        assert checkpoint is not None
        assert checkpoint.cursor == "1"

    response = client.get(
        f"/v1/projects/{project.id}/sources",
        headers=_headers(tenant_id, reviewer_id, "project:read"),
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["summary"]["total"] == 1
    assert payload["summary"]["healthy"] == 1
    assert payload["summary"]["total_ingested"] == 1

    source = payload["sources"][0]
    assert source["health"] == "healthy"
    assert source["checkpoint_present"] is True
    assert len(source["checkpoint_fingerprint"]) == 16
    assert source["latest_run"]["ingested"] == 1

    serialized = response.text
    assert '"cursor"' not in serialized
    assert '"start_cursor"' not in serialized
    assert '"end_cursor"' not in serialized
    assert '"1"' not in source["checkpoint_fingerprint"]


class _SkipConnector:
    connector_key = "synthetic:skip:v0"
    descriptor = ConnectorDescriptor(
        source_type="document",
        source_system="synthetic_documents",
        display_name="Synthetic Documents",
        permission_scope=["project:read"],
        safe_config={"mode": "test"},
    )

    def test_connection(self) -> ConnectorTestResult:
        return ConnectorTestResult(ok=True, message="ok")

    def fetch_page(self, *, project_id, cursor, limit) -> ConnectorPage:
        return ConnectorPage(
            records=[],
            skips=[
                ConnectorSkip(
                    external_id="file-1",
                    reason="Unsupported document extension: .pdf.",
                )
            ],
            next_cursor="opaque-checkpoint-token",
            has_more=False,
        )


def test_success_with_skips_is_attention_and_checkpoint_is_redacted(source_env) -> None:
    _, factory = source_env
    tenant_id, _, project = _project(factory)

    with factory() as session:
        result = create_durable_connector_runner(session).run(
            tenant_id=tenant_id,
            project_id=project.id,
            connector=_SkipConnector(),
        )
        assert result.status == ConnectorRunStatus.SUCCESS

    with factory() as session:
        snapshot = SourcesWorkspaceService(session).snapshot(
            tenant_id=tenant_id,
            project_id=project.id,
        )

    source = snapshot.sources[0]
    assert source.health == SourceHealthStatus.ATTENTION
    assert source.latest_run is not None
    assert source.latest_run.skipped == 1
    assert source.latest_run.skips[0]["external_id"] == "file-1"
    assert source.latest_run.checkpoint_fingerprint != "opaque-checkpoint-token"


class _FailureConnector:
    connector_key = "synthetic:failure:v0"
    descriptor = ConnectorDescriptor(
        source_type="email",
        source_system="synthetic_failure",
        display_name="Broken Mail",
        permission_scope=["project:read"],
        safe_config={},
    )

    def test_connection(self) -> ConnectorTestResult:
        return ConnectorTestResult(ok=False, message="unavailable")

    def fetch_page(self, *, project_id, cursor, limit) -> ConnectorPage:
        raise ConnectionError("source unavailable")


def test_failed_run_is_persisted_with_sanitized_error(source_env) -> None:
    _, factory = source_env
    tenant_id, _, project = _project(factory)

    with factory() as session:
        result = create_durable_connector_runner(session).run(
            tenant_id=tenant_id,
            project_id=project.id,
            connector=_FailureConnector(),
        )
        assert result.status == ConnectorRunStatus.FAILED

    with factory() as session:
        snapshot = SourcesWorkspaceService(session).snapshot(
            tenant_id=tenant_id,
            project_id=project.id,
        )

    source = snapshot.sources[0]
    assert source.health == SourceHealthStatus.FAILED
    assert source.latest_run is not None
    assert source.latest_run.errors == [
        {
            "stage": "fetch",
            "message": "ConnectionError: source unavailable",
            "external_id": None,
        }
    ]
    assert source.latest_run.start_checkpoint_present is False
    assert source.latest_run.end_checkpoint_present is False


def test_registered_source_without_run_is_never_synced(source_env) -> None:
    _, factory = source_env
    tenant_id, _, project = _project(factory)
    descriptor = ConnectorDescriptor(
        source_type="email",
        source_system="microsoft_graph_mail",
        display_name="Project Inbox",
        permission_scope=["project:read", "source:mail"],
        safe_config={"folder_id": "inbox"},
    )

    with factory() as session:
        SourceTelemetryService(session).register_connection(
            tenant_id=tenant_id,
            project_id=project.id,
            connector_key="microsoft-graph-mail:project-inbox:v0",
            descriptor=descriptor,
        )

    with factory() as session:
        snapshot = SourcesWorkspaceService(session).snapshot(
            tenant_id=tenant_id,
            project_id=project.id,
        )

    assert snapshot.summary.never_synced == 1
    assert snapshot.sources[0].health == SourceHealthStatus.NEVER_SYNCED
    assert snapshot.sources[0].latest_run is None
    assert snapshot.sources[0].checkpoint_present is False


def test_sources_workspace_requires_project_read(source_env) -> None:
    client, factory = source_env
    tenant_id, reviewer_id, project = _project(factory)

    response = client.get(
        f"/v1/projects/{project.id}/sources",
        headers=_headers(tenant_id, reviewer_id),
    )

    assert response.status_code == 403
    assert "project:read" in response.json()["detail"]


def test_sources_workspace_is_tenant_scoped(source_env) -> None:
    client, factory = source_env
    _, reviewer_id, project = _project(factory)

    response = client.get(
        f"/v1/projects/{project.id}/sources",
        headers=_headers(uuid4(), reviewer_id, "project:read"),
    )

    assert response.status_code == 404
    assert response.json()["detail"] == "Project not found for tenant"


def test_source_runs_are_isolated_by_project(source_env) -> None:
    _, factory = source_env
    tenant_id = uuid4()

    with factory() as session:
        memory = ProjectMemoryService(session)
        project_a = memory.create_project(tenant_id, Project(name="A"))
        project_b = memory.create_project(tenant_id, Project(name="B"))

    with factory() as session:
        create_durable_connector_runner(session).run(
            tenant_id=tenant_id,
            project_id=project_a.id,
            connector=SyntheticConnector(
                [_record(project_a.id, "a-1")],
                connector_key="synthetic:shared:v0",
            ),
        )

    with factory() as session:
        snapshot_a = SourcesWorkspaceService(session).snapshot(
            tenant_id=tenant_id,
            project_id=project_a.id,
        )
        snapshot_b = SourcesWorkspaceService(session).snapshot(
            tenant_id=tenant_id,
            project_id=project_b.id,
        )

    assert snapshot_a.summary.total == 1
    assert snapshot_b.summary.total == 0
