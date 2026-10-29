"""Tests for Secure Source Runtime + Scheduled Source Sync V0."""

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
    AutomationRunStatus,
    AutomationScheduleService,
    AutomationTaskType,
    CreateAutomationScheduleRequest,
)
from pmwizard.automation.worker import AutomationWorker
from pmwizard.connectors import (
    ConnectorDescriptor,
    MicrosoftGraphSharePointConnector,
)
from pmwizard.models import Project
from pmwizard.persistence import Base, ProjectMemoryService
from pmwizard.persistence.orm import (
    ConnectorCheckpointORM,
    EvidenceORM,
    SourceConnectionORM,
)
from pmwizard.security import (
    EnvironmentSecretProvider,
    MicrosoftEntraClientCredentialsTokenProvider,
    SecretResolutionError,
)
from pmwizard.sources import (
    BindSourceCredentialRequest,
    SourceCredentialService,
    SourceRuntimeResolver,
    SourceTelemetryService,
    SourcesWorkspaceService,
)


NOW = datetime.now(timezone.utc).replace(microsecond=0)


@pytest.fixture()
def runtime_env():
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


def _seed_mail_source(factory):
    tenant_id = uuid4()
    user_id = uuid4()
    with factory() as session:
        project = ProjectMemoryService(session).create_project(
            tenant_id,
            Project(name="Secure Source Demo"),
        )
        SourceTelemetryService(session).register_connection(
            tenant_id=tenant_id,
            project_id=project.id,
            connector_key="microsoft-graph-mail:project-inbox:v0",
            descriptor=ConnectorDescriptor(
                source_type="email",
                source_system="microsoft_graph_mail",
                display_name="Project Inbox",
                permission_scope=["project:read", "source:mail"],
                safe_config={
                    "mailbox": "pm@example.com",
                    "folder_id": "inbox",
                    "received_after": None,
                },
            ),
        )
        source = session.scalar(
            select(SourceConnectionORM).where(
                SourceConnectionORM.tenant_id == tenant_id,
                SourceConnectionORM.project_id == project.id,
            )
        )
        assert source is not None
    return tenant_id, user_id, project, source.id


class FakeGraphTransport:
    def __init__(self, token_provider, state: dict) -> None:
        self.token_provider = token_provider
        self.state = state

    def get_json(self, url: str, *, headers: dict[str, str]) -> dict:
        token = self.token_provider()
        self.state.setdefault("tokens", []).append(token)
        self.state.setdefault("urls", []).append(url)

        if url == "https://graph.test/delta/1":
            return {
                "value": [
                    {
                        "id": "msg-2",
                        "subject": "Second update",
                        "body": {
                            "contentType": "text",
                            "content": "Second governed source update.",
                        },
                        "receivedDateTime": "2026-10-29T22:15:00Z",
                        "from": {
                            "emailAddress": {
                                "address": "owner@example.com",
                            }
                        },
                    }
                ],
                "@odata.deltaLink": "https://graph.test/delta/2",
            }

        return {
            "value": [
                {
                    "id": "msg-1",
                    "subject": "First update",
                    "body": {
                        "contentType": "text",
                        "content": "First governed source update.",
                    },
                    "receivedDateTime": "2026-10-29T22:10:00Z",
                    "from": {
                        "emailAddress": {
                            "address": "owner@example.com",
                        }
                    },
                }
            ],
            "@odata.deltaLink": "https://graph.test/delta/1",
        }

    def get_bytes(
        self,
        url: str,
        *,
        headers: dict[str, str],
        max_bytes: int | None = None,
    ) -> bytes:
        raise AssertionError("Mail sync must not request document bytes")


def test_environment_secret_provider_only_reads_pmwizard_secret_namespace(
    monkeypatch,
) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "must-not-be-readable")
    monkeypatch.setenv(
        "PMWIZARD_SECRET_GRAPH_MAIN",
        '{"kind":"bearer_token","access_token":"runtime-only"}',
    )
    provider = EnvironmentSecretProvider()

    assert "runtime-only" in provider.resolve("env:GRAPH_MAIN")

    with pytest.raises(SecretResolutionError):
        provider.resolve("OPENAI_API_KEY")

    with pytest.raises(SecretResolutionError):
        provider.resolve("env:../OPENAI_API_KEY")


def test_entra_client_credentials_provider_caches_runtime_token() -> None:
    from pmwizard.security import EntraClientCredentials

    calls: list[tuple[str, bytes]] = []

    def exchange(url: str, body: bytes) -> dict:
        calls.append((url, body))
        return {
            "access_token": "entra-runtime-token",
            "expires_in": 3600,
        }

    provider = MicrosoftEntraClientCredentialsTokenProvider(
        EntraClientCredentials(
            kind="entra_client_credentials",
            tenant_id="tenant-id",
            client_id="client-id",
            client_secret="client-secret",
        ),
        exchange=exchange,
    )

    assert provider() == "entra-runtime-token"
    assert provider() == "entra-runtime-token"
    assert len(calls) == 1
    assert b"client_secret=client-secret" in calls[0][1]


def test_credential_binding_api_never_exposes_reference_or_secret(
    runtime_env,
    monkeypatch,
) -> None:
    tenant_id, user_id, project, source_id = _seed_mail_source(runtime_env)
    monkeypatch.setenv(
        "PMWIZARD_SECRET_TEST_GRAPH",
        '{"kind":"bearer_token","access_token":"TOP-SECRET-TOKEN"}',
    )
    app = create_app(runtime_env, allow_trusted_headers=True)

    with TestClient(app) as client:
        denied = client.put(
            f"/v1/projects/{project.id}/sources/{source_id}/credential",
            json={"credential_ref": "env:TEST_GRAPH"},
            headers=_headers(tenant_id, user_id, "project:read"),
        )
        bound = client.put(
            f"/v1/projects/{project.id}/sources/{source_id}/credential",
            json={"credential_ref": "env:TEST_GRAPH"},
            headers=_headers(
                tenant_id,
                user_id,
                "project:read",
                "project:review",
            ),
        )
        visible = client.get(
            f"/v1/projects/{project.id}/sources",
            headers=_headers(tenant_id, user_id, "project:read"),
        )

    assert denied.status_code == 403
    assert bound.status_code == 200
    assert bound.json() == {
        "source_connection_id": str(source_id),
        "credential_configured": True,
    }
    assert visible.status_code == 200
    source = visible.json()["sources"][0]
    assert source["credential_configured"] is True

    serialized = visible.text + bound.text
    assert "env:TEST_GRAPH" not in serialized
    assert "TOP-SECRET-TOKEN" not in serialized

    with runtime_env() as session:
        row = session.get(SourceConnectionORM, source_id)
        assert row is not None
        assert row.credential_ref == "env:TEST_GRAPH"
        assert "TOP-SECRET-TOKEN" not in json.dumps(row.safe_config)


def test_source_runtime_reconstructs_mail_connector_from_safe_metadata(
    runtime_env,
    monkeypatch,
) -> None:
    tenant_id, _, project, source_id = _seed_mail_source(runtime_env)
    monkeypatch.setenv(
        "PMWIZARD_SECRET_TEST_GRAPH",
        '{"kind":"bearer_token","access_token":"runtime-token"}',
    )
    state: dict = {}

    with runtime_env() as session:
        SourceCredentialService(session).bind(
            tenant_id=tenant_id,
            project_id=project.id,
            source_connection_id=source_id,
            command=BindSourceCredentialRequest(
                credential_ref="env:TEST_GRAPH"
            ),
        )
        connector = SourceRuntimeResolver(
            session,
            EnvironmentSecretProvider(),
            graph_transport_factory=lambda token_provider: FakeGraphTransport(
                token_provider,
                state,
            ),
        ).resolve(
            tenant_id=tenant_id,
            project_id=project.id,
            source_connection_id=source_id,
        )

        page = connector.fetch_page(
            project_id=project.id,
            cursor=None,
            limit=100,
        )

    assert connector.connector_key == "microsoft-graph-mail:project-inbox:v0"
    assert len(page.records) == 1
    assert page.records[0].external_id == "msg-1"
    assert page.next_cursor == "https://graph.test/delta/1"
    assert state["tokens"] == ["runtime-token"]


def test_source_runtime_reconstructs_sharepoint_without_persisting_secret(
    runtime_env,
    monkeypatch,
) -> None:
    tenant_id = uuid4()
    with runtime_env() as session:
        project = ProjectMemoryService(session).create_project(
            tenant_id,
            Project(name="SharePoint Runtime"),
        )
        SourceTelemetryService(session).register_connection(
            tenant_id=tenant_id,
            project_id=project.id,
            connector_key="microsoft-graph-sharepoint:delivery-docs:v0",
            descriptor=ConnectorDescriptor(
                source_type="document",
                source_system="microsoft_graph_sharepoint",
                display_name="Delivery Docs",
                permission_scope=["project:read", "source:sharepoint"],
                safe_config={
                    "drive_id": "drive-123",
                    "initial_sync_mode": "latest",
                    "supported_extensions": [".docx", ".txt"],
                    "max_file_bytes": 1048576,
                },
            ),
        )
        source = session.scalar(
            select(SourceConnectionORM).where(
                SourceConnectionORM.tenant_id == tenant_id,
                SourceConnectionORM.project_id == project.id,
            )
        )
        assert source is not None
        source_id = source.id

        SourceCredentialService(session).bind(
            tenant_id=tenant_id,
            project_id=project.id,
            source_connection_id=source_id,
            command=BindSourceCredentialRequest(
                credential_ref="env:SHAREPOINT_GRAPH"
            ),
        )

    monkeypatch.setenv(
        "PMWIZARD_SECRET_SHAREPOINT_GRAPH",
        '{"kind":"bearer_token","access_token":"sharepoint-runtime-token"}',
    )
    state: dict = {}

    with runtime_env() as session:
        connector = SourceRuntimeResolver(
            session,
            EnvironmentSecretProvider(),
            graph_transport_factory=lambda token_provider: FakeGraphTransport(
                token_provider,
                state,
            ),
        ).resolve(
            tenant_id=tenant_id,
            project_id=project.id,
            source_connection_id=source_id,
        )

    assert isinstance(connector, MicrosoftGraphSharePointConnector)
    assert connector.connector_key == (
        "microsoft-graph-sharepoint:delivery-docs:v0"
    )
    assert connector.config.connection_name == "Delivery Docs"
    assert connector.config.drive_id == "drive-123"


def test_source_sync_schedule_requires_bound_enabled_source(runtime_env) -> None:
    tenant_id, user_id, project, source_id = _seed_mail_source(runtime_env)

    with runtime_env() as session:
        service = AutomationScheduleService(session)
        with pytest.raises(
            ValueError,
            match="runtime credential binding",
        ):
            service.create(
                tenant_id=tenant_id,
                project_id=project.id,
                created_by=user_id,
                command=CreateAutomationScheduleRequest(
                    name="Sync Project Inbox",
                    task_type=AutomationTaskType.SOURCE_SYNC,
                    interval_minutes=60,
                    config={
                        "source_connection_id": str(source_id),
                    },
                ),
                now=NOW,
            )


def test_scheduled_source_sync_ingests_and_resumes_durable_delta_checkpoint(
    runtime_env,
    monkeypatch,
) -> None:
    tenant_id, user_id, project, source_id = _seed_mail_source(runtime_env)
    monkeypatch.setenv(
        "PMWIZARD_SECRET_TEST_GRAPH",
        '{"kind":"bearer_token","access_token":"RUNTIME-ONLY-TOKEN"}',
    )
    state: dict = {}

    with runtime_env() as session:
        SourceCredentialService(session).bind(
            tenant_id=tenant_id,
            project_id=project.id,
            source_connection_id=source_id,
            command=BindSourceCredentialRequest(
                credential_ref="env:TEST_GRAPH"
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
                start_at=NOW,
                config={
                    "source_connection_id": str(source_id),
                },
            ),
            now=NOW,
        )

    worker = AutomationWorker(
        runtime_env,
        worker_id="source-worker",
        lease_seconds=60,
        secret_provider=EnvironmentSecretProvider(),
        graph_transport_factory=lambda token_provider: FakeGraphTransport(
            token_provider,
            state,
        ),
    )

    first = worker.run_once(now=NOW)
    assert len(first) == 1
    assert first[0].status == AutomationRunStatus.SUCCESS
    assert first[0].summary["ingested"] == 1

    with runtime_env() as session:
        checkpoint = session.scalar(
            select(ConnectorCheckpointORM).where(
                ConnectorCheckpointORM.tenant_id == tenant_id,
                ConnectorCheckpointORM.project_id == project.id,
            )
        )
        assert checkpoint is not None
        assert checkpoint.cursor == "https://graph.test/delta/1"

        evidence = list(
            session.scalars(
                select(EvidenceORM).where(
                    EvidenceORM.tenant_id == tenant_id,
                    EvidenceORM.project_id == project.id,
                )
            ).all()
        )
        assert len(evidence) == 1

        AutomationScheduleService(session).run_now(
            tenant_id=tenant_id,
            project_id=project.id,
            schedule_id=schedule.id,
            now=datetime.now(timezone.utc),
        )

    second_now = datetime.now(timezone.utc)
    second = worker.run_once(now=second_now)
    assert len(second) == 1
    assert second[0].status == AutomationRunStatus.SUCCESS
    assert second[0].summary["ingested"] == 1

    with runtime_env() as session:
        checkpoint = session.scalar(
            select(ConnectorCheckpointORM).where(
                ConnectorCheckpointORM.tenant_id == tenant_id,
                ConnectorCheckpointORM.project_id == project.id,
            )
        )
        assert checkpoint is not None
        assert checkpoint.cursor == "https://graph.test/delta/2"

        evidence = list(
            session.scalars(
                select(EvidenceORM).where(
                    EvidenceORM.tenant_id == tenant_id,
                    EvidenceORM.project_id == project.id,
                )
            ).all()
        )
        assert {row.external_id for row in evidence} == {"msg-1", "msg-2"}

        workspace = SourcesWorkspaceService(session).snapshot(
            tenant_id=tenant_id,
            project_id=project.id,
        )
        source = workspace.sources[0]
        assert source.credential_configured is True
        assert source.latest_run is not None
        assert source.latest_run.ingested == 1

        row = session.get(SourceConnectionORM, source_id)
        assert row is not None
        assert row.credential_ref == "env:TEST_GRAPH"
        persisted = json.dumps(
            {
                "safe_config": row.safe_config,
                "credential_ref": row.credential_ref,
            }
        )
        assert "RUNTIME-ONLY-TOKEN" not in persisted

    assert "https://graph.test/delta/1" in state["urls"]
    assert set(state["tokens"]) == {"RUNTIME-ONLY-TOKEN"}


def test_clearing_credential_makes_future_source_sync_fail_safely(
    runtime_env,
    monkeypatch,
) -> None:
    tenant_id, user_id, project, source_id = _seed_mail_source(runtime_env)
    monkeypatch.setenv(
        "PMWIZARD_SECRET_TEST_GRAPH",
        '{"kind":"bearer_token","access_token":"runtime-token"}',
    )

    with runtime_env() as session:
        credentials = SourceCredentialService(session)
        credentials.bind(
            tenant_id=tenant_id,
            project_id=project.id,
            source_connection_id=source_id,
            command=BindSourceCredentialRequest(
                credential_ref="env:TEST_GRAPH"
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
                start_at=NOW,
                config={"source_connection_id": str(source_id)},
            ),
            now=NOW,
        )
        credentials.clear(
            tenant_id=tenant_id,
            project_id=project.id,
            source_connection_id=source_id,
        )

    worker = AutomationWorker(
        runtime_env,
        worker_id="source-worker",
        lease_seconds=60,
        secret_provider=EnvironmentSecretProvider(),
        graph_transport_factory=lambda token_provider: FakeGraphTransport(
            token_provider,
            {},
        ),
    )
    result = worker.run_once(now=NOW)

    assert len(result) == 1
    assert result[0].status == AutomationRunStatus.FAILED
    assert "no runtime credential reference" in (
        result[0].error_message or ""
    ).casefold()
    assert "runtime-token" not in (result[0].error_message or "")

    with runtime_env() as session:
        current = AutomationScheduleService(session).snapshot(
            tenant_id=tenant_id,
            project_id=project.id,
        ).schedules[0]
    assert current.id == schedule.id
    assert current.consecutive_failures == 1
