"""Security and completeness tests for Activity Export & Audit Pack V0."""

import csv
import hashlib
import io
import json
from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from pmwizard.activity.export import ProjectActivityExportService
from pmwizard.api import create_app
from pmwizard.models import Project
from pmwizard.persistence import Base, ProjectMemoryService
from pmwizard.persistence.orm import AuditLogORM, EventORM, EvidenceORM


NOW = datetime(2026, 10, 30, 19, 0, tzinfo=timezone.utc)
EXPORT_PERMISSIONS = {"project:read", "project:review"}


@pytest.fixture()
def export_env():
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, class_=Session, expire_on_commit=False)
    tenant, another_tenant, actor = uuid4(), uuid4(), uuid4()
    with factory() as session:
        project = ProjectMemoryService(session).create_project(
            tenant, Project(name="Activity Export Demo")
        )
    return factory, tenant, another_tenant, actor, project.id


def add_event(factory, tenant, project_id, *, action, time=NOW,
              actor=None, evidence_id=None):
    row_id = uuid4()
    with factory() as session:
        session.add(
            EventORM(
                id=row_id,
                tenant_id=tenant,
                project_id=project_id,
                event_type=action,
                occurred_at=time,
                actor_id=actor,
                entity_type="ActionItem",
                entity_id=uuid4(),
                previous_value={"status": "open", "secret": "DO-NOT-EXPORT"},
                new_value={"status": "completed", "secret": "SECRET-NEW"},
                source_evidence_id=evidence_id,
                provenance={},
            )
        )
        session.commit()
    return row_id


def test_json_export_has_manifest_checksum_and_redacted_evidence(export_env):
    factory, tenant, _, actor, project_id = export_env
    visible, hidden = uuid4(), uuid4()
    with factory() as session:
        for evidence_id, scope in (
            (visible, ["project:read"]),
            (hidden, ["secret:read"]),
        ):
            session.add(
                EvidenceORM(
                    id=evidence_id,
                    tenant_id=tenant,
                    project_id=project_id,
                    source_type="email",
                    captured_at=NOW,
                    content_excerpt="DO-NOT-EXPORT",
                    permission_scope=scope,
                    provenance={},
                )
            )
        session.add(
            AuditLogORM(
                id=uuid4(),
                tenant_id=tenant,
                project_id=project_id,
                actor_id=actor,
                action="review_accepted",
                entity_type="ActionItem",
                entity_id=uuid4(),
                previous_state={"priority": "low", "password": "DO-NOT-EXPORT"},
                proposed_state={"priority": "high", "token": "DO-NOT-EXPORT"},
                final_state={"priority": "high"},
                evidence_ids=[str(hidden), str(visible)],
                created_at=NOW + timedelta(minutes=1),
            )
        )
        session.commit()
    add_event(
        factory, tenant, project_id,
        action="task_completed", actor=actor, evidence_id=hidden,
    )

    with factory() as session:
        export = ProjectActivityExportService(session).export(
            tenant_id=tenant, project_id=project_id,
            permissions=EXPORT_PERMISSIONS, export_format="json",
            categories=None, actor_id=None,
        )

    document = json.loads(export.body)
    assert export.content_type.startswith("application/json")
    assert export.filename.endswith(".json")
    assert hashlib.sha256(export.body).hexdigest() == export.sha256
    assert document["row_count"] == 2
    assert document["truncated"] is False
    assert document["schema_version"] == "activity-export-v0"
    assert document["category_counts"] == {"audit": 1, "event": 1}
    assert [item["category"] for item in document["items"]] == ["audit", "event"]
    assert document["items"][0]["evidence_ids"] == [str(visible)]
    assert document["items"][1]["evidence_ids"] == []
    assert document["items"][0]["changed_fields"] == ["priority"]
    assert "DO-NOT-EXPORT" not in export.body.decode()
    assert "SECRET-NEW" not in export.body.decode()
    assert str(hidden) not in export.body.decode()


def test_csv_export_escapes_spreadsheet_injection(export_env):
    factory, tenant, _, actor, project_id = export_env
    add_event(
        factory, tenant, project_id,
        action='  =HYPERLINK("https://example.com","click")',
        actor=actor,
    )
    with factory() as session:
        export = ProjectActivityExportService(session).export(
            tenant_id=tenant, project_id=project_id,
            permissions=EXPORT_PERMISSIONS, export_format="csv",
        )
    cells = list(csv.DictReader(io.StringIO(export.body.decode("utf-8"))))
    assert len(cells) == 1
    assert cells[0]["action"].startswith("'  =HYPERLINK")
    assert cells[0]["changed_fields"] == "status"
    assert hashlib.sha256(export.body).hexdigest() == export.sha256
    assert export.filename.endswith(".csv")


def test_export_paginates_caps_and_marks_truncation(export_env):
    factory, tenant, _, _, project_id = export_env
    with factory() as session:
        session.add_all([
            EventORM(
                id=uuid4(),
                tenant_id=tenant,
                project_id=project_id,
                event_type="routine_event",
                occurred_at=NOW + timedelta(seconds=i),
                provenance={},
            )
            for i in range(126)
        ])
        session.commit()
    with factory() as session:
        service = ProjectActivityExportService(session)
        capped = service.export(
            tenant_id=tenant, project_id=project_id,
            permissions=EXPORT_PERMISSIONS, export_format="json", max_rows=105,
        )
        all_rows = service.export(
            tenant_id=tenant, project_id=project_id,
            permissions=EXPORT_PERMISSIONS, export_format="json", max_rows=126,
        )
        filtered = service.export(
            tenant_id=tenant, project_id=project_id,
            permissions=EXPORT_PERMISSIONS, export_format="json",
            since=NOW + timedelta(seconds=120), max_rows=126,
        )
    capped_doc = json.loads(capped.body)
    all_doc = json.loads(all_rows.body)
    assert capped.count == 105
    assert capped.truncated is True
    assert capped_doc["truncated"] is True
    assert all_rows.count == 126
    assert all_rows.truncated is False
    assert len(set(row["id"] for row in all_doc["items"])) == 126
    assert [row["occurred_at"] for row in all_doc["items"]] == sorted(
        [row["occurred_at"] for row in all_doc["items"]], reverse=True,
    )
    assert filtered.count == 6


def test_export_requires_privileged_scope_and_valid_dates(export_env):
    factory, tenant, other, _, project_id = export_env
    with factory() as session:
        service = ProjectActivityExportService(session)
        for perms in (set(), {"project:read"}, {"project:review"}):
            with pytest.raises(PermissionError):
                service.export(
                    tenant_id=tenant, project_id=project_id,
                    permissions=perms, export_format="csv",
                )
        with pytest.raises(LookupError):
            service.export(
                tenant_id=other, project_id=project_id,
                permissions=EXPORT_PERMISSIONS,
            )
        with pytest.raises(ValueError, match="timezone"):
            service.export(
                tenant_id=tenant, project_id=project_id,
                permissions=EXPORT_PERMISSIONS,
                since=datetime(2026, 10, 30),
            )
        with pytest.raises(ValueError, match="limit"):
            service.export(
                tenant_id=tenant, project_id=project_id,
                permissions=EXPORT_PERMISSIONS, max_rows=501,
            )


def test_export_api_checks_authorization_filters_and_safe_headers(export_env):
    factory, tenant, other, actor, project_id = export_env
    event_id = add_event(
        factory, tenant, project_id, action="task_completed", actor=actor,
    )
    client = TestClient(create_app(factory, allow_trusted_headers=True))
    endpoint = f"/v1/projects/{project_id}/activity/export"

    def headers(tenant_id, permissions):
        return {
            "X-PMWizard-Tenant-ID": str(tenant_id),
            "X-PMWizard-User-ID": str(actor),
            "X-PMWizard-Permissions": permissions,
        }

    assert client.get(endpoint).status_code == 401
    assert client.get(endpoint, headers=headers(tenant, "project:read")).status_code == 403
    assert client.get(endpoint, headers=headers(other, "project:read,project:review")).status_code == 404
    response = client.get(
        endpoint + f"?format=json&category=event&actor_id={actor}",
        headers=headers(tenant, "project:read,project:review"),
    )
    assert response.status_code == 200
    assert response.json()["items"][0]["id"] == str(event_id)
    assert response.headers["content-disposition"].startswith("attachment; filename=")
    assert response.headers["cache-control"] == "private, no-store"
    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.headers["x-pmwizard-export-count"] == "1"
    assert response.headers["x-pmwizard-export-truncated"] == "false"
    assert hashlib.sha256(response.content).hexdigest() == response.headers["x-pmwizard-export-sha256"]
    assert client.get(
        endpoint + "?format=xml", headers=headers(tenant, "project:read,project:review")
    ).status_code == 422
    assert client.get(
        endpoint + "?since=2026-10-30T19:00:00",
        headers=headers(tenant, "project:read,project:review"),
    ).status_code == 422


def test_default_export_hard_cap_at_500(export_env):
    factory, tenant, _, _, project_id = export_env
    with factory() as session:
        session.add_all([
            EventORM(
                id=uuid4(),
                tenant_id=tenant,
                project_id=project_id,
                event_type="bulk_event",
                occurred_at=NOW + timedelta(seconds=i),
                provenance={},
            )
            for i in range(501)
        ])
        session.commit()
    with factory() as session:
        export = ProjectActivityExportService(session).export(
            tenant_id=tenant, project_id=project_id,
            permissions=EXPORT_PERMISSIONS,
        )
    assert export.count == 500
    assert export.truncated is True
    rows = list(csv.DictReader(io.StringIO(export.body.decode("utf-8"))))
    assert len(rows) == 500
