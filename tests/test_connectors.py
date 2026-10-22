"""Tests for Connector Framework V0."""

from datetime import datetime, timezone
from uuid import uuid4

import pytest
from sqlalchemy import func, select

from pmwizard.connectors import (
    ConnectorPage,
    ConnectorRunStatus,
    ConnectorRunner,
    ConnectorTestResult,
    InMemoryCheckpointStore,
    SyntheticConnector,
)
from pmwizard.ingestion import EvidenceIngestionService, SourceRecord
from pmwizard.models import Project
from pmwizard.persistence import (
    Base,
    ProjectMemoryService,
    create_engine_from_url,
    create_session_factory,
)
from pmwizard.persistence.orm import EvidenceORM


NOW = datetime(2026, 10, 21, 21, 0, tzinfo=timezone.utc)


@pytest.fixture()
def session():
    engine = create_engine_from_url("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    factory = create_session_factory(engine)
    with factory() as session:
        yield session


def _record(project_id, external_id: str, content: str | None = None) -> SourceRecord:
    return SourceRecord(
        project_id=project_id,
        source_type="email",
        source_system="synthetic-mail",
        external_id=external_id,
        source_reference=f"synthetic://mail/{external_id}",
        author="pm@example.test",
        captured_at=NOW,
        content=content or f"Update {external_id}",
        permission_scope=["project:read"],
    )


def test_synthetic_connector_implements_connection_check() -> None:
    connector = SyntheticConnector([])

    result = connector.test_connection()

    assert isinstance(result, ConnectorTestResult)
    assert result.ok is True


def test_runner_ingests_paginated_source_records(session) -> None:
    tenant_id = uuid4()
    memory = ProjectMemoryService(session)
    project = memory.create_project(tenant_id, Project(name="Connector Demo"))
    records = [_record(project.id, f"msg-{index}") for index in range(5)]
    store = InMemoryCheckpointStore()

    result = ConnectorRunner(session, store).run(
        tenant_id=tenant_id,
        project_id=project.id,
        connector=SyntheticConnector(records),
        page_size=2,
    )

    assert result.status == ConnectorRunStatus.SUCCESS
    assert result.pages_processed == 3
    assert result.fetched == 5
    assert result.ingested == 5
    assert result.end_cursor == "5"
    assert result.errors == []
    count = session.scalar(select(func.count()).select_from(EvidenceORM))
    assert count == 5


def test_checkpoint_resumes_from_last_completed_page(session) -> None:
    tenant_id = uuid4()
    memory = ProjectMemoryService(session)
    project = memory.create_project(tenant_id, Project(name="Resume Demo"))
    records = [_record(project.id, f"msg-{index}") for index in range(3)]
    connector = SyntheticConnector(records, connector_key="resume:v0")
    store = InMemoryCheckpointStore()
    runner = ConnectorRunner(session, store)

    first = runner.run(
        tenant_id=tenant_id,
        project_id=project.id,
        connector=connector,
        page_size=2,
        max_pages=1,
    )
    second = runner.run(
        tenant_id=tenant_id,
        project_id=project.id,
        connector=connector,
        page_size=2,
    )

    assert first.status == ConnectorRunStatus.PARTIAL
    assert first.end_cursor == "2"
    assert second.status == ConnectorRunStatus.SUCCESS
    assert second.start_cursor == "2"
    assert second.fetched == 1
    assert second.ingested == 1
    assert second.end_cursor == "3"


class _FailOnceIngestion:
    def __init__(self, session, fail_external_id: str) -> None:
        self.delegate = EvidenceIngestionService(session)
        self.fail_external_id = fail_external_id
        self.failed = False

    def ingest(self, tenant_id, record):
        if record.external_id == self.fail_external_id and not self.failed:
            self.failed = True
            raise RuntimeError("synthetic ingestion failure")
        return self.delegate.ingest(tenant_id, record)


def test_checkpoint_does_not_advance_on_partial_page_failure_and_retry_is_safe(session) -> None:
    tenant_id = uuid4()
    memory = ProjectMemoryService(session)
    project = memory.create_project(tenant_id, Project(name="Retry Demo"))
    records = [
        _record(project.id, "msg-1"),
        _record(project.id, "msg-2"),
    ]
    connector = SyntheticConnector(records, connector_key="retry:v0")
    store = InMemoryCheckpointStore()
    ingestion = _FailOnceIngestion(session, "msg-2")
    runner = ConnectorRunner(session, store, ingestion=ingestion)

    first = runner.run(
        tenant_id=tenant_id,
        project_id=project.id,
        connector=connector,
        page_size=2,
    )
    second = runner.run(
        tenant_id=tenant_id,
        project_id=project.id,
        connector=connector,
        page_size=2,
    )

    assert first.status == ConnectorRunStatus.FAILED
    assert first.end_cursor is None
    assert first.ingested == 1
    assert len(first.errors) == 1
    assert first.errors[0].stage == "ingestion"

    assert second.status == ConnectorRunStatus.SUCCESS
    assert second.start_cursor is None
    assert second.fetched == 2
    assert second.duplicates == 1
    assert second.ingested == 1
    assert second.end_cursor == "2"

    count = session.scalar(select(func.count()).select_from(EvidenceORM))
    assert count == 2


class _WrongProjectConnector:
    connector_key = "wrong-project:v0"

    def __init__(self, record: SourceRecord) -> None:
        self.record = record

    def test_connection(self) -> ConnectorTestResult:
        return ConnectorTestResult(ok=True, message="ok")

    def fetch_page(self, *, project_id, cursor, limit) -> ConnectorPage:
        return ConnectorPage(
            records=[self.record],
            next_cursor="1",
            has_more=False,
        )


def test_runner_rejects_record_mapped_to_another_project(session) -> None:
    tenant_id = uuid4()
    memory = ProjectMemoryService(session)
    expected = memory.create_project(tenant_id, Project(name="Expected"))
    other = memory.create_project(tenant_id, Project(name="Other"))
    store = InMemoryCheckpointStore()

    result = ConnectorRunner(session, store).run(
        tenant_id=tenant_id,
        project_id=expected.id,
        connector=_WrongProjectConnector(_record(other.id, "wrong-1")),
    )

    assert result.status == ConnectorRunStatus.FAILED
    assert result.pages_processed == 0
    assert result.errors[0].stage == "mapping"
    assert result.end_cursor is None


class _BrokenPagingConnector:
    connector_key = "broken-paging:v0"

    def test_connection(self) -> ConnectorTestResult:
        return ConnectorTestResult(ok=True, message="ok")

    def fetch_page(self, *, project_id, cursor, limit) -> ConnectorPage:
        return ConnectorPage(records=[], next_cursor=None, has_more=True)


def test_runner_detects_invalid_paging_contract(session) -> None:
    tenant_id = uuid4()
    memory = ProjectMemoryService(session)
    project = memory.create_project(tenant_id, Project(name="Broken Paging"))

    result = ConnectorRunner(session, InMemoryCheckpointStore()).run(
        tenant_id=tenant_id,
        project_id=project.id,
        connector=_BrokenPagingConnector(),
    )

    assert result.status == ConnectorRunStatus.FAILED
    assert result.errors[0].stage == "contract"


class _FetchFailureConnector:
    connector_key = "fetch-failure:v0"

    def test_connection(self) -> ConnectorTestResult:
        return ConnectorTestResult(ok=False, message="unavailable")

    def fetch_page(self, *, project_id, cursor, limit) -> ConnectorPage:
        raise ConnectionError("source unavailable")


def test_runner_reports_fetch_failures_without_advancing_checkpoint(session) -> None:
    tenant_id = uuid4()
    memory = ProjectMemoryService(session)
    project = memory.create_project(tenant_id, Project(name="Fetch Failure"))
    store = InMemoryCheckpointStore()

    result = ConnectorRunner(session, store).run(
        tenant_id=tenant_id,
        project_id=project.id,
        connector=_FetchFailureConnector(),
    )

    assert result.status == ConnectorRunStatus.FAILED
    assert result.errors[0].stage == "fetch"
    assert result.end_cursor is None


def test_checkpoint_is_scoped_by_tenant_project_and_connector() -> None:
    store = InMemoryCheckpointStore()
    tenant_a = uuid4()
    tenant_b = uuid4()
    project_a = uuid4()
    project_b = uuid4()

    store.set_checkpoint(
        tenant_id=tenant_a,
        project_id=project_a,
        connector_key="mail:v0",
        cursor="10",
    )

    assert store.get_checkpoint(
        tenant_id=tenant_a,
        project_id=project_a,
        connector_key="mail:v0",
    ) == "10"
    assert store.get_checkpoint(
        tenant_id=tenant_b,
        project_id=project_a,
        connector_key="mail:v0",
    ) is None
    assert store.get_checkpoint(
        tenant_id=tenant_a,
        project_id=project_b,
        connector_key="mail:v0",
    ) is None
    assert store.get_checkpoint(
        tenant_id=tenant_a,
        project_id=project_a,
        connector_key="files:v0",
    ) is None


@pytest.mark.parametrize("value", [0, -1, 1.5, True, None])
def test_invalid_runner_limits_are_rejected(session, value) -> None:
    runner = ConnectorRunner(session, InMemoryCheckpointStore())
    connector = SyntheticConnector([])

    with pytest.raises(ValueError, match="positive integer"):
        runner.run(
            tenant_id=uuid4(),
            project_id=uuid4(),
            connector=connector,
            page_size=value,
        )
