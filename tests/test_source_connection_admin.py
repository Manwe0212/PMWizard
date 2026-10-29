"""Tests for Source Connection Administration V0."""

from __future__ import annotations

from datetime import datetime, timezone
import json
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from pmwizard.api import create_app
from pmwizard.automation import (
    AutomationScheduleService,
    AutomationTaskType,
    CreateAutomationScheduleRequest,
)
from pmwizard.automation.worker import AutomationWorker
from pmwizard.connectors import ConnectorDescriptor, ConnectorPage, ConnectorTestResult
from pmwizard.models import Project
from pmwizard.persistence import Base, ProjectMemoryService
from pmwizard.persistence.orm import (
    AutomationScheduleORM,
    ConnectorCheckpointORM,
    SourceConnectionORM,
)
from pmwizard.security import EnvironmentSecretProvider
from pmwizard.sources import (
    BindSourceCredentialRequest,
    SourceConnectionAdminService,
    SourceCredentialService,
    SourceRepository,
    SourceTelemetryService,
    SourcesWorkspaceService,
)
from pmwizard.connectors import SQLAlchemyCheckpointStore


NOW = datetime.now(timezone.utc).replace(microsecond=0)


@pytest.fixture()
def admin_env():
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
            Project(name="Source Admin Demo"),
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


class FakeGraphTransport:
    def __init__(self, token_provider, state: dict) -> None:
        self.token_provider = token_provider
        self.state = state

    def get_json(self, url: str, *, headers: dict[str, str]) -> dict:
        self.state["token"] = self.token_provider()
        self.state["url"] = url
        if "/mailFolders/" in url:
            return {"id": "inbox", "displayName": "Inbox"}
        return {
            "id": "drive-123",
            "name": "Delivery Documents",
            "webUrl": "https://example.test/docs",
        }

    def get_bytes(
        self,
        url: str,
        *,
        headers: dict[str, str],
        max_bytes: int | None = None,
    ) -> bytes:
        return b""


def test_create_mail_source_from_api_uses_immutable_uuid_connector_key(
    admin_env,
) -> None:
    tenant_id, user_id, project = _seed_project(admin_env)
    app = create_app(admin_env, allow_trusted_headers=True)

    payload = {
        "source_system": "microsoft_graph_mail",
        "display_name": "Project Inbox",
        "safe_config": {
            "mailbox": "pm@example.com",
            "folder_id": "inbox",
            "received_after": None,
        },
        "permission_scope": ["project:read", "source:mail"],
    }

    with TestClient(app) as client:
        denied = client.post(
            f"/v1/projects/{project.id}/sources",
            json=payload,
            headers=_headers(tenant_id, user_id, "project:read"),
        )
        created = client.post(
            f"/v1/projects/{project.id}/sources",
            json=payload,
            headers=_headers(
                tenant_id,
                user_id,
                "project:read",
                "project:review",
            ),
        )

    assert denied.status_code == 403
    assert created.status_code == 201
    source = created.json()
    assert source["display_name"] == "Project Inbox"
    assert source["source_system"] == "microsoft_graph_mail"
    assert source["source_type"] == "email"
    assert source["credential_configured"] is False
    assert source["connector_key"].startswith(
        "microsoft-graph-mail:admin:"
    )
    assert source["connector_key"].endswith(":v0")
    assert str(source["id"]) in source["connector_key"]
    assert source["permission_scope"] == ["project:read", "source:mail"]


def test_create_source_rejects_secret_material_in_safe_config(admin_env) -> None:
    tenant_id, user_id, project = _seed_project(admin_env)
    app = create_app(admin_env, allow_trusted_headers=True)

    with TestClient(app) as client:
        response = client.post(
            f"/v1/projects/{project.id}/sources",
            json={
                "source_system": "microsoft_graph_mail",
                "display_name": "Unsafe Inbox",
                "safe_config": {
                    "mailbox": "pm@example.com",
                    "folder_id": "inbox",
                    "access_token": "must-never-be-accepted",
                },
            },
            headers=_headers(
                tenant_id,
                user_id,
                "project:read",
                "project:review",
            ),
        )

    assert response.status_code == 422
    assert "access_token" in response.json()["detail"]

    with admin_env() as session:
        rows = session.scalars(select(SourceConnectionORM)).all()
    assert rows == []


def test_update_display_name_preserves_key_but_stream_change_clears_checkpoint(
    admin_env,
) -> None:
    tenant_id, _, project = _seed_project(admin_env)

    with admin_env() as session:
        service = SourceConnectionAdminService(session)
        source = service.create(
            tenant_id=tenant_id,
            project_id=project.id,
            command=__import__(
                "pmwizard.sources.schemas",
                fromlist=["CreateSourceConnectionRequest"],
            ).CreateSourceConnectionRequest(
                source_system="microsoft_graph_mail",
                display_name="Original",
                safe_config={
                    "mailbox": "pm@example.com",
                    "folder_id": "inbox",
                },
            ),
        )
        key = source.connector_key

        SQLAlchemyCheckpointStore(session).set(
            tenant_id=tenant_id,
            project_id=project.id,
            connector_key=key,
            cursor="https://graph.test/delta/original",
        )
        session.commit()

        renamed = service.update(
            tenant_id=tenant_id,
            project_id=project.id,
            source_connection_id=source.id,
            command=__import__(
                "pmwizard.sources.schemas",
                fromlist=["UpdateSourceConnectionRequest"],
            ).UpdateSourceConnectionRequest(
                display_name="Renamed Inbox",
            ),
        )

    assert renamed.connector_key == key

    with admin_env() as session:
        checkpoint = session.scalar(
            select(ConnectorCheckpointORM).where(
                ConnectorCheckpointORM.connector_key == key
            )
        )
        assert checkpoint is not None

        service = SourceConnectionAdminService(session)
        changed = service.update(
            tenant_id=tenant_id,
            project_id=project.id,
            source_connection_id=source.id,
            command=__import__(
                "pmwizard.sources.schemas",
                fromlist=["UpdateSourceConnectionRequest"],
            ).UpdateSourceConnectionRequest(
                safe_config={
                    "mailbox": "pm@example.com",
                    "folder_id": "archive",
                },
            ),
        )

    assert changed.connector_key == key
    assert changed.safe_config["folder_id"] == "archive"

    with admin_env() as session:
        checkpoint = session.scalar(
            select(ConnectorCheckpointORM).where(
                ConnectorCheckpointORM.connector_key == key
            )
        )
    assert checkpoint is None


def test_disabling_source_pauses_related_source_sync_schedule(admin_env) -> None:
    tenant_id, user_id, project = _seed_project(admin_env)

    with admin_env() as session:
        from pmwizard.sources.schemas import (
            CreateSourceConnectionRequest,
            UpdateSourceConnectionRequest,
        )

        source = SourceConnectionAdminService(session).create(
            tenant_id=tenant_id,
            project_id=project.id,
            command=CreateSourceConnectionRequest(
                source_system="microsoft_graph_mail",
                display_name="Project Inbox",
                safe_config={
                    "mailbox": "pm@example.com",
                    "folder_id": "inbox",
                },
            ),
        )
        SourceCredentialService(session).bind(
            tenant_id=tenant_id,
            project_id=project.id,
            source_connection_id=source.id,
            command=BindSourceCredentialRequest(
                credential_ref="env:GRAPH_ADMIN"
            ),
        )
        schedule = AutomationScheduleService(session).create(
            tenant_id=tenant_id,
            project_id=project.id,
            created_by=user_id,
            command=CreateAutomationScheduleRequest(
                name="Sync Project Inbox",
                task_type=AutomationTaskType.SOURCE_SYNC,
                interval_minutes=60,
                config={"source_connection_id": str(source.id)},
            ),
            now=NOW,
        )
        assert schedule.enabled is True

        SourceConnectionAdminService(session).update(
            tenant_id=tenant_id,
            project_id=project.id,
            source_connection_id=source.id,
            command=UpdateSourceConnectionRequest(enabled=False),
        )

    with admin_env() as session:
        row = session.get(AutomationScheduleORM, schedule.id)
        assert row is not None
        assert row.is_enabled is False


def test_test_connection_requires_enabled_source_and_credential(admin_env) -> None:
    tenant_id, user_id, project = _seed_project(admin_env)

    with admin_env() as session:
        from pmwizard.sources.schemas import CreateSourceConnectionRequest

        source = SourceConnectionAdminService(session).create(
            tenant_id=tenant_id,
            project_id=project.id,
            command=CreateSourceConnectionRequest(
                source_system="microsoft_graph_sharepoint",
                display_name="Delivery Docs",
                safe_config={
                    "drive_id": "drive-123",
                    "initial_sync_mode": "latest",
                },
            ),
        )

        with pytest.raises(ValueError, match="runtime credential"):
            SourceConnectionAdminService(session).queue_test(
                tenant_id=tenant_id,
                project_id=project.id,
                source_connection_id=source.id,
                requested_by=user_id,
                now=NOW,
            )


def test_connection_test_is_worker_executed_and_secret_never_exposed(
    admin_env,
    monkeypatch,
) -> None:
    tenant_id, user_id, project = _seed_project(admin_env)
    monkeypatch.setenv(
        "PMWIZARD_SECRET_GRAPH_ADMIN",
        '{"kind":"bearer_token","access_token":"WORKER-ONLY-TOKEN"}',
    )
    state: dict = {}

    with admin_env() as session:
        from pmwizard.sources.schemas import CreateSourceConnectionRequest

        source = SourceConnectionAdminService(session).create(
            tenant_id=tenant_id,
            project_id=project.id,
            command=CreateSourceConnectionRequest(
                source_system="microsoft_graph_mail",
                display_name="Project Inbox",
                safe_config={
                    "mailbox": "pm@example.com",
                    "folder_id": "inbox",
                },
            ),
        )
        SourceCredentialService(session).bind(
            tenant_id=tenant_id,
            project_id=project.id,
            source_connection_id=source.id,
            command=BindSourceCredentialRequest(
                credential_ref="env:GRAPH_ADMIN"
            ),
        )
        queued = SourceConnectionAdminService(session).queue_test(
            tenant_id=tenant_id,
            project_id=project.id,
            source_connection_id=source.id,
            requested_by=user_id,
            now=NOW,
        )

    assert queued.status.value == "queued"

    worker = AutomationWorker(
        admin_env,
        worker_id="admin-worker",
        lease_seconds=60,
        secret_provider=EnvironmentSecretProvider(),
        graph_transport_factory=lambda token_provider: FakeGraphTransport(
            token_provider,
            state,
        ),
    )
    worker.run_once(now=NOW)

    with admin_env() as session:
        snapshot = SourcesWorkspaceService(session).snapshot(
            tenant_id=tenant_id,
            project_id=project.id,
        )
        current = snapshot.sources[0]
        row = session.get(SourceConnectionORM, source.id)

    assert current.connection_test.status.value == "success"
    assert "reachable" in (current.connection_test.message or "")
    assert current.connection_test.last_test_at is not None
    assert state["token"] == "WORKER-ONLY-TOKEN"
    assert row is not None
    serialized = json.dumps(
        {
            "safe_config": row.safe_config,
            "last_test_message": row.last_test_message,
            "credential_ref": row.credential_ref,
        }
    )
    assert "WORKER-ONLY-TOKEN" not in serialized


def test_two_workers_cannot_claim_same_connection_test(admin_env) -> None:
    tenant_id, user_id, project = _seed_project(admin_env)

    with admin_env() as session:
        from pmwizard.sources.schemas import CreateSourceConnectionRequest

        source = SourceConnectionAdminService(session).create(
            tenant_id=tenant_id,
            project_id=project.id,
            command=CreateSourceConnectionRequest(
                source_system="microsoft_graph_mail",
                display_name="Project Inbox",
                safe_config={"mailbox": "pm@example.com", "folder_id": "inbox"},
            ),
        )
        SourceCredentialService(session).bind(
            tenant_id=tenant_id,
            project_id=project.id,
            source_connection_id=source.id,
            command=BindSourceCredentialRequest(
                credential_ref="env:GRAPH_ADMIN"
            ),
        )
        SourceConnectionAdminService(session).queue_test(
            tenant_id=tenant_id,
            project_id=project.id,
            source_connection_id=source.id,
            requested_by=user_id,
            now=NOW,
        )

    with admin_env() as session:
        first = SourceRepository(session).claim_pending_tests(
            worker_id="worker-a",
            now=NOW,
            lease_seconds=60,
            limit=10,
        )

    with admin_env() as session:
        second = SourceRepository(session).claim_pending_tests(
            worker_id="worker-b",
            now=NOW,
            lease_seconds=60,
            limit=10,
        )

    assert len(first) == 1
    assert second == []


def test_sharepoint_admin_normalizes_extensions(admin_env) -> None:
    tenant_id, _, project = _seed_project(admin_env)

    with admin_env() as session:
        from pmwizard.sources.schemas import CreateSourceConnectionRequest

        source = SourceConnectionAdminService(session).create(
            tenant_id=tenant_id,
            project_id=project.id,
            command=CreateSourceConnectionRequest(
                source_system="microsoft_graph_sharepoint",
                display_name="Delivery Docs",
                safe_config={
                    "drive_id": "drive-123",
                    "initial_sync_mode": "full",
                    "supported_extensions": ["DOCX", ".txt", "docx"],
                    "max_file_bytes": 5000000,
                },
            ),
        )

    assert source.source_type == "document"
    assert source.safe_config["supported_extensions"] == [".docx", ".txt"]
    assert source.safe_config["initial_sync_mode"] == "full"
