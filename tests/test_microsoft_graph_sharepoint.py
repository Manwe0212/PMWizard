"""Tests for SharePoint Documents V0."""

import io
import zipfile
from datetime import datetime, timezone
from urllib.parse import parse_qs, urlparse
from uuid import uuid4

import pytest
from sqlalchemy import func, select

import pmwizard.connectors.microsoft_graph_mail as graph_mail_module
from pmwizard.connectors import (
    ConnectorRunStatus,
    ConnectorRunner,
    InMemoryCheckpointStore,
    MicrosoftGraphHttpTransport,
    MicrosoftGraphSharePointConfig,
    MicrosoftGraphSharePointConnector,
)
from pmwizard.intelligence import ProgressIntelligenceService, ProgressPipelineOutcome
from pmwizard.models import ActionItem, Project
from pmwizard.models.enums import ActionItemStatus
from pmwizard.persistence import (
    Base,
    ProjectMemoryService,
    create_engine_from_url,
    create_session_factory,
)
from pmwizard.persistence.orm import EvidenceORM


NOW = datetime(2026, 10, 21, 22, 0, tzinfo=timezone.utc)


class _FakeDocumentTransport:
    def __init__(self, json_responses, byte_responses=None):
        self.json_responses = list(json_responses)
        self.byte_responses = list(byte_responses or [])
        self.json_calls = []
        self.byte_calls = []

    def get_json(self, url, *, headers):
        self.json_calls.append((url, headers))
        if not self.json_responses:
            raise AssertionError("No fake Graph JSON response configured")
        response = self.json_responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return response

    def get_bytes(self, url, *, headers, max_bytes=None):
        self.byte_calls.append((url, headers, max_bytes))
        if not self.byte_responses:
            raise AssertionError("No fake Graph byte response configured")
        response = self.byte_responses.pop(0)
        if isinstance(response, Exception):
            raise response
        if max_bytes is not None and len(response) > max_bytes:
            raise RuntimeError("fake file too large")
        return response


@pytest.fixture()
def session():
    engine = create_engine_from_url("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    factory = create_session_factory(engine)
    with factory() as session:
        yield session


def _config(**overrides):
    values = {
        "connection_name": "project-documents",
        "drive_id": "drive-123",
        "permission_scope": ["microsoft-graph:sharepoint:read"],
    }
    values.update(overrides)
    return MicrosoftGraphSharePointConfig(**values)


def _item(
    *,
    item_id="item-1",
    name="Meeting Notes.txt",
    etag='"etag-1"',
    modified="2026-10-21T22:00:00Z",
    size=100,
):
    return {
        "id": item_id,
        "name": name,
        "file": {"mimeType": "text/plain"},
        "lastModifiedDateTime": modified,
        "createdDateTime": modified,
        "webUrl": f"https://contoso.sharepoint.com/{name}",
        "eTag": etag,
        "size": size,
        "lastModifiedBy": {
            "user": {
                "displayName": "Project Manager",
                "email": "pm@example.test",
            }
        },
    }


def _docx_bytes(*paragraphs: str) -> bytes:
    namespace = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
    body = "".join(
        f"<w:p><w:r><w:t>{paragraph}</w:t></w:r></w:p>"
        for paragraph in paragraphs
    )
    document = (
        f'<?xml version="1.0" encoding="UTF-8"?>'
        f'<w:document xmlns:w="{namespace}"><w:body>{body}</w:body></w:document>'
    ).encode("utf-8")

    output = io.BytesIO()
    with zipfile.ZipFile(output, "w") as archive:
        archive.writestr("word/document.xml", document)
    return output.getvalue()


def test_default_initial_sync_is_latest_and_uses_delta() -> None:
    transport = _FakeDocumentTransport(
        [
            {
                "value": [],
                "@odata.deltaLink": "https://graph.microsoft.com/delta/final",
            }
        ]
    )
    connector = MicrosoftGraphSharePointConnector(_config(), transport)

    page = connector.fetch_page(project_id=uuid4(), cursor=None, limit=50)

    url, headers = transport.json_calls[0]
    parsed = urlparse(url)
    query = parse_qs(parsed.query)
    assert parsed.path.endswith("/drives/drive-123/root/delta")
    assert query["token"] == ["latest"]
    assert query["$top"] == ["50"]
    assert "lastModifiedDateTime" in query["$select"][0]
    assert headers["deltaExcludeParent"] == "true"
    assert page.next_cursor == "https://graph.microsoft.com/delta/final"


def test_full_initial_sync_omits_latest_token() -> None:
    transport = _FakeDocumentTransport(
        [{"value": [], "@odata.deltaLink": "https://graph.microsoft.com/delta/final"}]
    )
    connector = MicrosoftGraphSharePointConnector(
        _config(initial_sync_mode="full"),
        transport,
    )

    connector.fetch_page(project_id=uuid4(), cursor=None, limit=10)

    query = parse_qs(urlparse(transport.json_calls[0][0]).query)
    assert "token" not in query


def test_plain_text_file_maps_to_versioned_source_record() -> None:
    project_id = uuid4()
    transport = _FakeDocumentTransport(
        [{"value": [_item()], "@odata.deltaLink": "https://graph/delta/1"}],
        [b"Action Item A was completed."],
    )
    connector = MicrosoftGraphSharePointConnector(_config(), transport)

    page = connector.fetch_page(project_id=project_id, cursor=None, limit=10)

    assert len(page.records) == 1
    record = page.records[0]
    assert record.project_id == project_id
    assert record.source_type == "document"
    assert record.source_system == "microsoft_graph_sharepoint"
    assert record.external_id == 'item-1:"etag-1"'
    assert record.author == "pm@example.test"
    assert record.content == "Meeting Notes\n\nAction Item A was completed."
    assert record.captured_at == NOW
    assert transport.byte_calls[0][0].endswith(
        "/drives/drive-123/items/item-1/content"
    )


def test_docx_text_is_extracted_deterministically() -> None:
    item = _item(name="Weekly Minutes.docx")
    item["file"] = {
        "mimeType": "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    }
    transport = _FakeDocumentTransport(
        [{"value": [item], "@odata.deltaLink": "https://graph/delta/1"}],
        [_docx_bytes("Verify API access", "Completed today")],
    )

    page = MicrosoftGraphSharePointConnector(_config(), transport).fetch_page(
        project_id=uuid4(),
        cursor=None,
        limit=10,
    )

    assert page.records[0].content == (
        "Weekly Minutes\n\n"
        "Verify API access\nCompleted today"
    )


def test_unsupported_deleted_and_folder_items_are_reported_as_skips() -> None:
    unsupported = _item(item_id="pdf-1", name="Report.pdf")
    deleted = {"id": "deleted-1", "deleted": {"state": "deleted"}}
    folder = {"id": "folder-1", "name": "Archive", "folder": {"childCount": 3}}

    transport = _FakeDocumentTransport(
        [
            {
                "value": [unsupported, deleted, folder],
                "@odata.deltaLink": "https://graph/delta/1",
            }
        ]
    )

    page = MicrosoftGraphSharePointConnector(_config(), transport).fetch_page(
        project_id=uuid4(),
        cursor=None,
        limit=10,
    )

    assert page.records == []
    assert len(page.skips) == 3
    reasons = " ".join(skip.reason for skip in page.skips)
    assert "Unsupported document extension" in reasons
    assert "historical Evidence is preserved" in reasons
    assert "not a downloadable file" in reasons
    assert transport.byte_calls == []


def test_oversized_file_is_skipped_before_download() -> None:
    transport = _FakeDocumentTransport(
        [
            {
                "value": [_item(size=5000)],
                "@odata.deltaLink": "https://graph/delta/1",
            }
        ]
    )
    connector = MicrosoftGraphSharePointConnector(
        _config(max_file_bytes=1000),
        transport,
    )

    page = connector.fetch_page(project_id=uuid4(), cursor=None, limit=10)

    assert page.records == []
    assert page.skips[0].external_id == "item-1"
    assert "size limit" in page.skips[0].reason
    assert transport.byte_calls == []


def test_last_duplicate_occurrence_in_delta_page_wins() -> None:
    first = _item(etag='"etag-old"', modified="2026-10-21T21:00:00Z")
    latest = _item(etag='"etag-new"', modified="2026-10-21T22:00:00Z")
    transport = _FakeDocumentTransport(
        [
            {
                "value": [first, latest],
                "@odata.deltaLink": "https://graph/delta/1",
            }
        ],
        [b"Latest content"],
    )

    page = MicrosoftGraphSharePointConnector(_config(), transport).fetch_page(
        project_id=uuid4(),
        cursor=None,
        limit=10,
    )

    assert len(page.records) == 1
    assert page.records[0].external_id == 'item-1:"etag-new"'
    assert page.records[0].content.endswith("Latest content")
    assert len(transport.byte_calls) == 1


def test_next_link_is_an_opaque_checkpoint() -> None:
    next_link = "https://graph.microsoft.com/v1.0/opaque?$skiptoken=ABC"
    delta_link = "https://graph.microsoft.com/v1.0/opaque?$deltatoken=XYZ"
    transport = _FakeDocumentTransport(
        [
            {"value": [], "@odata.nextLink": next_link},
            {"value": [], "@odata.deltaLink": delta_link},
        ]
    )
    connector = MicrosoftGraphSharePointConnector(_config(), transport)
    project_id = uuid4()

    first = connector.fetch_page(project_id=project_id, cursor=None, limit=10)
    second = connector.fetch_page(
        project_id=project_id,
        cursor=first.next_cursor,
        limit=10,
    )

    assert first.has_more is True
    assert first.next_cursor == next_link
    assert transport.json_calls[1][0] == next_link
    assert second.has_more is False
    assert second.next_cursor == delta_link


def test_connection_check_reports_drive_name_and_failure() -> None:
    good = _FakeDocumentTransport(
        [{"id": "drive-123", "name": "Project Documents"}]
    )
    bad = _FakeDocumentTransport([RuntimeError("Graph unavailable")])

    ok = MicrosoftGraphSharePointConnector(_config(), good).test_connection()
    failed = MicrosoftGraphSharePointConnector(_config(), bad).test_connection()

    assert ok.ok is True
    assert "Project Documents" in ok.message
    assert failed.ok is False
    assert "Graph unavailable" in failed.message


def test_graph_http_binary_download_is_bounded(monkeypatch) -> None:
    captured = {}

    class _Response:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def read(self, size=-1):
            captured["size"] = size
            return b"hello"

    def fake_urlopen(request, timeout):
        captured["authorization"] = request.get_header("Authorization")
        return _Response()

    monkeypatch.setattr(graph_mail_module, "urlopen", fake_urlopen)
    transport = MicrosoftGraphHttpTransport(lambda: "secret-token")

    payload = transport.get_bytes(
        "https://graph.microsoft.com/v1.0/drives/x/items/y/content",
        headers={"Accept": "*/*"},
        max_bytes=10,
    )

    assert payload == b"hello"
    assert captured["authorization"] == "Bearer secret-token"
    assert captured["size"] == 11


def test_document_versions_create_immutable_evidence_records(session) -> None:
    tenant_id = uuid4()
    memory = ProjectMemoryService(session)
    project = memory.create_project(tenant_id, Project(name="Versioned Documents"))
    delta_1 = "https://graph/delta/token-1"
    delta_2 = "https://graph/delta/token-2"
    transport = _FakeDocumentTransport(
        [
            {"value": [_item(etag='"v1"')], "@odata.deltaLink": delta_1},
            {
                "value": [
                    _item(
                        etag='"v2"',
                        modified="2026-10-21T22:30:00Z",
                    )
                ],
                "@odata.deltaLink": delta_2,
            },
        ],
        [b"Original project update", b"Changed project update"],
    )
    connector = MicrosoftGraphSharePointConnector(
        _config(initial_sync_mode="full"),
        transport,
    )
    runner = ConnectorRunner(session, InMemoryCheckpointStore())

    first = runner.run(
        tenant_id=tenant_id,
        project_id=project.id,
        connector=connector,
    )
    second = runner.run(
        tenant_id=tenant_id,
        project_id=project.id,
        connector=connector,
    )

    assert first.ingested == 1
    assert second.ingested == 1
    assert second.start_cursor == delta_1
    assert second.end_cursor == delta_2
    count = session.scalar(select(func.count()).select_from(EvidenceORM))
    assert count == 2


def test_metadata_only_version_with_same_content_is_deduplicated(session) -> None:
    tenant_id = uuid4()
    memory = ProjectMemoryService(session)
    project = memory.create_project(tenant_id, Project(name="Metadata Change"))
    delta_1 = "https://graph/delta/token-1"
    transport = _FakeDocumentTransport(
        [
            {"value": [_item(etag='"v1"')], "@odata.deltaLink": delta_1},
            {"value": [_item(etag='"v2"')], "@odata.deltaLink": "https://graph/delta/token-2"},
        ],
        [b"Same text", b"Same text"],
    )
    connector = MicrosoftGraphSharePointConnector(
        _config(initial_sync_mode="full"),
        transport,
    )
    runner = ConnectorRunner(session, InMemoryCheckpointStore())

    first = runner.run(
        tenant_id=tenant_id,
        project_id=project.id,
        connector=connector,
    )
    second = runner.run(
        tenant_id=tenant_id,
        project_id=project.id,
        connector=connector,
    )

    assert first.ingested == 1
    assert second.duplicates == 1
    count = session.scalar(select(func.count()).select_from(EvidenceORM))
    assert count == 1


def test_skips_are_aggregated_in_connector_run(session) -> None:
    tenant_id = uuid4()
    memory = ProjectMemoryService(session)
    project = memory.create_project(tenant_id, Project(name="Skip Reporting"))
    transport = _FakeDocumentTransport(
        [
            {
                "value": [_item(item_id="pdf-1", name="Report.pdf")],
                "@odata.deltaLink": "https://graph/delta/final",
            }
        ]
    )

    run = ConnectorRunner(session, InMemoryCheckpointStore()).run(
        tenant_id=tenant_id,
        project_id=project.id,
        connector=MicrosoftGraphSharePointConnector(_config(), transport),
    )

    assert run.status == ConnectorRunStatus.SUCCESS
    assert run.skipped == 1
    assert run.skips[0].external_id == "pdf-1"


def test_sharepoint_document_can_feed_progress_intelligence(session) -> None:
    tenant_id = uuid4()
    memory = ProjectMemoryService(session)
    project = memory.create_project(
        tenant_id,
        Project(name="SharePoint Intelligence"),
    )
    action = memory.add_action_item(
        tenant_id,
        ActionItem(
            project_id=project.id,
            title="Verify API access",
            status=ActionItemStatus.IN_PROGRESS,
            created_at=NOW,
        ),
    )

    item = _item(name="Verify API access.txt")
    transport = _FakeDocumentTransport(
        [{"value": [item], "@odata.deltaLink": "https://graph/delta/final"}],
        [b"Verify API access was completed today."],
    )
    connector = MicrosoftGraphSharePointConnector(
        _config(initial_sync_mode="full"),
        transport,
    )

    run = ConnectorRunner(session, InMemoryCheckpointStore()).run(
        tenant_id=tenant_id,
        project_id=project.id,
        connector=connector,
    )

    assert run.status == ConnectorRunStatus.SUCCESS
    assert run.ingested == 1

    evidence_rows = session.scalars(select(EvidenceORM)).all()
    assert len(evidence_rows) == 1
    evidence = memory.repository.get_evidence_by_source_identity(
        tenant_id,
        project.id,
        "microsoft_graph_sharepoint",
        evidence_rows[0].external_id,
    )
    assert evidence is not None

    intelligence = ProgressIntelligenceService(session).analyze_evidence(
        tenant_id,
        evidence,
    )

    assert intelligence.outcome == ProgressPipelineOutcome.SUGGESTION_CREATED
    assert intelligence.suggestion is not None
    assert intelligence.suggestion.target_entity_id == action.id
    assert intelligence.suggestion.proposed_changes["status"] == "completed"
