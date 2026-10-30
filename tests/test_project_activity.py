"""Project Activity Timeline V0: chronology, scoping, cursor and redaction."""

import json
from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from pmwizard.activity import ActivityCategory, ProjectActivityService
from pmwizard.api import create_app
from pmwizard.models import Project
from pmwizard.persistence import Base, ProjectMemoryService
from pmwizard.persistence.orm import (
    AISuggestionORM,
    AuditLogORM,
    AutomationRunORM,
    ConnectorRunORM,
    EventORM,
    EvidenceORM,
    HumanReviewORM,
    ProjectHealthSnapshotORM,
)


NOW = datetime(2026, 10, 30, 19, 0, tzinfo=timezone.utc)


@pytest.fixture()
def timeline_env():
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, class_=Session, expire_on_commit=False)
    tenant_id, other_tenant, reviewer = uuid4(), uuid4(), uuid4()
    with factory() as session:
        project = ProjectMemoryService(session).create_project(
            tenant_id, Project(name="Project Activity Demo")
        )
    hidden_evidence_id = uuid4()
    visible_evidence_id = uuid4()
    suggestion_id = uuid4()
    ids = {}
    with factory() as session:
        for evidence_id, scope in (
            (hidden_evidence_id, ["evidence:confidential"]),
            (visible_evidence_id, ["project:read"]),
        ):
            session.add(
                EvidenceORM(
                    id=evidence_id,
                    tenant_id=tenant_id,
                    project_id=project.id,
                    source_type="email",
                    source_system="outlook",
                    captured_at=NOW,
                    content_excerpt="INTERNAL SECRET",
                    permission_scope=scope,
                    provenance={},
                )
            )
        session.add(
            AISuggestionORM(
                id=suggestion_id,
                tenant_id=tenant_id,
                project_id=project.id,
                suggestion_type="update_action",
                proposed_changes={"status": "completed"},
                reason="INTERNAL SECRET",
                evidence_ids=[str(visible_evidence_id)],
                confidence=0.91,
                review_status="accepted",
                provenance={},
            )
        )

        ids["event"] = uuid4()
        session.add(
            EventORM(
                id=ids["event"],
                tenant_id=tenant_id,
                project_id=project.id,
                event_type="action_changed",
                occurred_at=NOW,
                actor_id=reviewer,
                entity_type="ActionItem",
                entity_id=uuid4(),
                previous_value={"status": "open", "api_key": "INTERNAL SECRET"},
                new_value={"status": "completed", "api_key": "NEW SECRET"},
                source_evidence_id=hidden_evidence_id,
                provenance={},
            )
        )
        ids["audit"] = uuid4()
        session.add(
            AuditLogORM(
                id=ids["audit"],
                tenant_id=tenant_id,
                project_id=project.id,
                actor_id=reviewer,
                action="suggestion_accepted",
                entity_type="ActionItem",
                entity_id=uuid4(),
                previous_state={"priority": "low", "password": "INTERNAL SECRET"},
                final_state={"priority": "high", "password": "NEW SECRET"},
                proposed_state={"status": "completed"},
                evidence_ids=[str(hidden_evidence_id), str(visible_evidence_id)],
                created_at=NOW + timedelta(minutes=1),
            )
        )
        ids["human_review"] = uuid4()
        session.add(
            HumanReviewORM(
                id=ids["human_review"],
                tenant_id=tenant_id,
                project_id=project.id,
                suggestion_id=suggestion_id,
                reviewer_id=reviewer,
                status="accepted",
                reviewed_at=NOW + timedelta(minutes=2),
                reviewer_note="INTERNAL SECRET",
                final_changes={},
                provenance={},
            )
        )
        ids["source_run"] = uuid4()
        session.add(
            ConnectorRunORM(
                id=ids["source_run"],
                tenant_id=tenant_id,
                project_id=project.id,
                connector_key="env:INTERNAL_SECRET",
                status="success",
                started_at=NOW,
                finished_at=NOW + timedelta(minutes=3),
                pages_processed=2,
                fetched=5,
                ingested=3,
                duplicates=1,
                source_changed=0,
                empty_content=0,
                skipped=1,
                skips=["INTERNAL SECRET"],
                errors=["INTERNAL SECRET"],
                start_checkpoint_present=False,
                end_checkpoint_present=True,
            )
        )
        ids["automation_run"] = uuid4()
        session.add(
            AutomationRunORM(
                id=ids["automation_run"],
                tenant_id=tenant_id,
                project_id=project.id,
                schedule_id=uuid4(),
                task_type="health_snapshot",
                trigger="scheduled",
                status="success",
                worker_id="INTERNAL SECRET",
                scheduled_for=NOW,
                started_at=NOW + timedelta(minutes=4),
                summary={"secret": "INTERNAL SECRET"},
                error_message="INTERNAL SECRET",
            )
        )
        ids["health_snapshot"] = uuid4()
        session.add(
            ProjectHealthSnapshotORM(
                id=ids["health_snapshot"],
                tenant_id=tenant_id,
                project_id=project.id,
                captured_at=NOW + timedelta(minutes=5),
                captured_by=None,
                capture_source="automation",
                model_version="project-health-v0",
                score=73,
                band="watch",
                coverage_percent=80,
                coverage_band="good",
                available_weight=80,
                factor_scores={},
                key_drivers=[],
                snapshot_payload={"secret": "INTERNAL SECRET"},
                state_fingerprint="f" * 64,
            )
        )
        session.commit()
    return factory, tenant_id, other_tenant, reviewer, project.id, ids, visible_evidence_id


def test_activity_unifies_six_sources_in_order_and_redacts_secret_payloads(timeline_env):
    factory, tenant, _, _, project_id, ids, visible_evidence_id = timeline_env
    with factory() as session:
        result = ProjectActivityService(session).timeline(
            tenant_id=tenant, project_id=project_id, permissions={"project:read"}
        )

    assert result.count == 6
    assert [item.category.value for item in result.items] == [
        "health_snapshot", "automation_run", "source_run",
        "human_review", "audit", "event",
    ]
    assert result.items[-1].evidence_ids == []
    audit = next(item for item in result.items if item.category == ActivityCategory.AUDIT)
    assert audit.evidence_ids == [visible_evidence_id]
    assert audit.changed_fields == ["priority"]
    event = next(item for item in result.items if item.category == ActivityCategory.EVENT)
    assert event.changed_fields == ["status"]
    payload = json.dumps(result.model_dump(mode="json"))
    assert "INTERNAL SECRET" not in payload
    assert "NEW SECRET" not in payload
    assert "env:" not in payload
    assert set(item.id for item in result.items) == set(ids.values())


def test_activity_cursor_is_stable_and_filters_actor_category_time(timeline_env):
    factory, tenant, _, reviewer, project_id, ids, _ = timeline_env
    with factory() as session:
        service = ProjectActivityService(session)
        cursor = None
        collected = []
        for _ in range(4):
            result = service.timeline(
                tenant_id=tenant,
                project_id=project_id,
                permissions={"project:read"},
                cursor=cursor,
                limit=2,
            )
            collected.extend(item.id for item in result.items)
            cursor = result.next_cursor
            if cursor is None:
                break
        assert collected == [
            ids["health_snapshot"], ids["automation_run"], ids["source_run"],
            ids["human_review"], ids["audit"], ids["event"],
        ]
        assert cursor is None

        by_actor = service.timeline(
            tenant_id=tenant, project_id=project_id,
            permissions={"project:read"}, actor_id=reviewer,
        )
        assert [item.category.value for item in by_actor.items] == [
            "human_review", "audit", "event",
        ]
        by_category = service.timeline(
            tenant_id=tenant, project_id=project_id,
            permissions={"project:read"}, categories=[ActivityCategory.SOURCE_RUN],
        )
        assert [item.id for item in by_category.items] == [ids["source_run"]]
        by_time = service.timeline(
            tenant_id=tenant, project_id=project_id,
            permissions={"project:read"},
            since=NOW + timedelta(minutes=2),
            until=NOW + timedelta(minutes=4),
        )
        assert [item.id for item in by_time.items] == [
            ids["automation_run"], ids["source_run"], ids["human_review"],
        ]


def test_activity_enforces_tenant_and_validates_cursor(timeline_env):
    factory, tenant, other_tenant, _, project_id, _, _ = timeline_env
    with factory() as session:
        service = ProjectActivityService(session)
        with pytest.raises(LookupError):
            service.timeline(
                tenant_id=other_tenant, project_id=project_id,
                permissions={"project:read"},
            )
        with pytest.raises(PermissionError):
            service.timeline(
                tenant_id=tenant, project_id=project_id, permissions=set()
            )
        with pytest.raises(ValueError, match="cursor"):
            service.timeline(
                tenant_id=tenant, project_id=project_id,
                permissions={"project:read"}, cursor="invalid###"
            )
        with pytest.raises(ValueError, match="timezone"):
            service.timeline(
                tenant_id=tenant, project_id=project_id,
                permissions={"project:read"}, since=datetime(2026, 10, 30)
            )


def test_activity_api_permission_and_query_validation(timeline_env):
    factory, tenant, _, reviewer, project_id, ids, _ = timeline_env
    client = TestClient(create_app(factory, allow_trusted_headers=True))
    url = f"/v1/projects/{project_id}/activity"

    def headers(permissions):
        return {
            "X-PMWizard-Tenant-ID": str(tenant),
            "X-PMWizard-User-ID": str(reviewer),
            "X-PMWizard-Permissions": permissions,
        }

    assert client.get(url).status_code == 401
    assert client.get(url, headers=headers("")).status_code == 403
    ok = client.get(url + "?category=audit&limit=1", headers=headers("project:read"))
    assert ok.status_code == 200
    assert ok.json()["items"][0]["id"] == str(ids["audit"])
    assert client.get(url + "?cursor=garbage", headers=headers("project:read")).status_code == 422
    assert client.get(url + "?limit=101", headers=headers("project:read")).status_code == 422
