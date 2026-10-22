"""Tests for Microsoft Graph Mail V0."""

from datetime import datetime, timezone
from types import SimpleNamespace
from urllib.parse import parse_qs, urlparse
from uuid import uuid4

import pytest
from pydantic import ValidationError

import pmwizard.connectors.microsoft_graph_mail as graph_mail_module
from pmwizard.connectors import (
    ConnectorRunStatus,
    ConnectorRunner,
    InMemoryCheckpointStore,
    MicrosoftGraphHttpTransport,
    MicrosoftGraphMailConfig,
    MicrosoftGraphMailConnector,
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


NOW = datetime(2026, 10, 21, 21, 30, tzinfo=timezone.utc)


class _FakeGraphTransport:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    def get_json(self, url, *, headers):
        self.calls.append((url, headers))
        if not self.responses:
            raise AssertionError("No fake Graph response configured")
        response = self.responses.pop(0)
        if isinstance(response, Exception):
            raise response
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
        "connection_name": "primary-inbox",
        "mailbox": "me",
        "folder_id": "inbox",
        "permission_scope": ["microsoft-graph:mail:read"],
    }
    values.update(overrides)
    return MicrosoftGraphMailConfig(**values)


def _message(
    *,
    message_id="msg-1",
    subject="Verify API access",
    body_content="Verify API access was completed today.",
    body_type="text",
    preview="Verify API access was completed today.",
):
    return {
        "id": message_id,
        "subject": subject,
        "body": {
            "contentType": body_type,
            "content": body_content,
        },
        "bodyPreview": preview,
        "from": {
            "emailAddress": {
                "name": "Project Manager",
                "address": "pm@example.test",
            }
        },
        "receivedDateTime": "2026-10-21T21:30:00Z",
        "webLink": f"https://outlook.office.com/mail/{message_id}",
    }


def test_config_requires_timezone_aware_received_after() -> None:
    with pytest.raises(ValidationError):
        _config(received_after=datetime(2026, 10, 21, 12, 0))


def test_initial_delta_request_uses_created_filter_select_and_received_after() -> None:
    transport = _FakeGraphTransport(
        [
            {
                "value": [],
                "@odata.deltaLink": "https://graph.microsoft.com/delta/final",
            }
        ]
    )
    connector = MicrosoftGraphMailConnector(
        _config(received_after=NOW),
        transport,
    )

    page = connector.fetch_page(project_id=uuid4(), cursor=None, limit=25)

    url, headers = transport.calls[0]
    parsed = urlparse(url)
    query = parse_qs(parsed.query)

    assert parsed.path.endswith("/me/mailFolders/inbox/messages/delta")
    assert query["changeType"] == ["created"]
    assert "body" in query["$select"][0]
    assert query["$filter"] == ["receivedDateTime ge 2026-10-21T21:30:00Z"]
    assert 'outlook.body-content-type="text"' in headers["Prefer"]
    assert "odata.maxpagesize=25" in headers["Prefer"]
    assert page.has_more is False
    assert page.next_cursor == "https://graph.microsoft.com/delta/final"


def test_mailbox_and_folder_are_url_encoded() -> None:
    transport = _FakeGraphTransport(
        [
            {
                "value": [],
                "@odata.deltaLink": "https://graph.microsoft.com/delta/final",
            }
        ]
    )
    connector = MicrosoftGraphMailConnector(
        _config(mailbox="user+pm@example.test", folder_id="Project Mail"),
        transport,
    )

    connector.fetch_page(project_id=uuid4(), cursor=None, limit=10)

    url, _ = transport.calls[0]
    assert "/users/user%2Bpm%40example.test/" in url
    assert "/mailFolders/Project%20Mail/messages/delta" in url


def test_text_body_maps_to_source_record() -> None:
    project_id = uuid4()
    transport = _FakeGraphTransport(
        [
            {
                "value": [_message()],
                "@odata.deltaLink": "https://graph.microsoft.com/delta/final",
            }
        ]
    )
    connector = MicrosoftGraphMailConnector(_config(), transport)

    page = connector.fetch_page(project_id=project_id, cursor=None, limit=10)

    assert len(page.records) == 1
    record = page.records[0]
    assert record.project_id == project_id
    assert record.source_system == "microsoft_graph_mail"
    assert record.source_type == "email"
    assert record.external_id == "msg-1"
    assert record.author == "pm@example.test"
    assert record.source_reference == "https://outlook.office.com/mail/msg-1"
    assert record.content == (
        "Subject: Verify API access\n\n"
        "Verify API access was completed today."
    )
    assert record.captured_at == NOW
    assert record.permission_scope == ["microsoft-graph:mail:read"]


def test_html_body_falls_back_to_text_preview() -> None:
    transport = _FakeGraphTransport(
        [
            {
                "value": [
                    _message(
                        body_content="<p>Unsafe for V0 parser</p>",
                        body_type="html",
                        preview="Safe plain-text preview",
                    )
                ],
                "@odata.deltaLink": "https://graph.microsoft.com/delta/final",
            }
        ]
    )

    record = MicrosoftGraphMailConnector(_config(), transport).fetch_page(
        project_id=uuid4(),
        cursor=None,
        limit=10,
    ).records[0]

    assert record.content.endswith("Safe plain-text preview")
    assert "<p>" not in record.content


def test_removed_delta_entries_are_ignored() -> None:
    transport = _FakeGraphTransport(
        [
            {
                "value": [
                    {"id": "deleted-1", "@removed": {"reason": "deleted"}},
                    _message(message_id="msg-2"),
                ],
                "@odata.deltaLink": "https://graph.microsoft.com/delta/final",
            }
        ]
    )

    page = MicrosoftGraphMailConnector(_config(), transport).fetch_page(
        project_id=uuid4(),
        cursor=None,
        limit=10,
    )

    assert [record.external_id for record in page.records] == ["msg-2"]


def test_next_link_is_used_as_opaque_cursor() -> None:
    next_link = "https://graph.microsoft.com/v1.0/opaque?$skiptoken=ABC123"
    delta_link = "https://graph.microsoft.com/v1.0/opaque?$deltatoken=XYZ456"
    transport = _FakeGraphTransport(
        [
            {
                "value": [_message(message_id="msg-1")],
                "@odata.nextLink": next_link,
            },
            {
                "value": [_message(message_id="msg-2")],
                "@odata.deltaLink": delta_link,
            },
        ]
    )
    connector = MicrosoftGraphMailConnector(_config(), transport)
    project_id = uuid4()

    first = connector.fetch_page(project_id=project_id, cursor=None, limit=5)
    second = connector.fetch_page(
        project_id=project_id,
        cursor=first.next_cursor,
        limit=5,
    )

    assert first.has_more is True
    assert first.next_cursor == next_link
    assert transport.calls[1][0] == next_link
    assert second.has_more is False
    assert second.next_cursor == delta_link


def test_missing_graph_cursor_is_rejected() -> None:
    transport = _FakeGraphTransport([{"value": []}])
    connector = MicrosoftGraphMailConnector(_config(), transport)

    with pytest.raises(RuntimeError, match="neither nextLink nor deltaLink"):
        connector.fetch_page(project_id=uuid4(), cursor=None, limit=10)


def test_connection_check_reports_success_and_failure() -> None:
    ok_transport = _FakeGraphTransport([{"id": "inbox", "displayName": "Inbox"}])
    bad_transport = _FakeGraphTransport([RuntimeError("Graph unavailable")])

    ok = MicrosoftGraphMailConnector(_config(), ok_transport).test_connection()
    bad = MicrosoftGraphMailConnector(_config(), bad_transport).test_connection()

    assert ok.ok is True
    assert "Inbox" in ok.message
    assert bad.ok is False
    assert "Graph unavailable" in bad.message


def test_http_transport_adds_bearer_token_and_decodes_json(monkeypatch) -> None:
    captured = {}

    class _Response:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def read(self):
            return b'{"value": []}'

    def fake_urlopen(request, timeout):
        captured["request"] = request
        captured["timeout"] = timeout
        return _Response()

    monkeypatch.setattr(graph_mail_module, "urlopen", fake_urlopen)

    transport = MicrosoftGraphHttpTransport(
        lambda: "secret-token",
        timeout_seconds=12,
    )
    payload = transport.get_json(
        "https://graph.microsoft.com/v1.0/me/messages",
        headers={"Prefer": 'outlook.body-content-type="text"'},
    )

    assert payload == {"value": []}
    assert captured["request"].get_header("Authorization") == "Bearer secret-token"
    assert captured["request"].get_header("Prefer") == (
        'outlook.body-content-type="text"'
    )
    assert captured["timeout"] == 12


def test_http_transport_rejects_empty_token() -> None:
    transport = MicrosoftGraphHttpTransport(lambda: "  ")

    with pytest.raises(RuntimeError, match="empty token"):
        transport.get_json(
            "https://graph.microsoft.com/v1.0/me/messages",
            headers={},
        )


def test_graph_mail_runs_through_connector_runner_and_progress_intelligence(session) -> None:
    tenant_id = uuid4()
    memory = ProjectMemoryService(session)
    project = memory.create_project(
        tenant_id,
        Project(name="Graph Mail Integration"),
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

    delta_link = "https://graph.microsoft.com/v1.0/delta/final-token"
    transport = _FakeGraphTransport(
        [
            {
                "value": [_message()],
                "@odata.deltaLink": delta_link,
            }
        ]
    )
    connector = MicrosoftGraphMailConnector(_config(), transport)
    store = InMemoryCheckpointStore()

    run = ConnectorRunner(session, store).run(
        tenant_id=tenant_id,
        project_id=project.id,
        connector=connector,
        page_size=10,
    )

    assert run.status == ConnectorRunStatus.SUCCESS
    assert run.ingested == 1
    assert run.end_cursor == delta_link

    evidence = memory.repository.get_evidence_by_source_identity(
        tenant_id,
        project.id,
        "microsoft_graph_mail",
        "msg-1",
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
