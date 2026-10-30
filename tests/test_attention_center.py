"""Tests for Project Notifications & Attention Center V0."""

from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from pmwizard.api import create_app
from pmwizard.attention import (
    AttentionCenterService,
    AttentionStateCommand,
    AttentionUserState,
)
from pmwizard.models import AISuggestion, ActionItem, Evidence, Project
from pmwizard.models.enums import ActionItemStatus, SuggestionType
from pmwizard.persistence import Base, ProjectMemoryService
from pmwizard.persistence.orm import ActionItemORM


NOW = datetime(2026, 10, 30, 16, 0, tzinfo=timezone.utc)


@pytest.fixture()
def attention_env():
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
            Project(name="Attention Demo"),
        )
    return tenant_id, user_id, project


def _headers(tenant_id, user_id, *permissions):
    return {
        "X-PMWizard-Tenant-ID": str(tenant_id),
        "X-PMWizard-User-ID": str(user_id),
        "X-PMWizard-Permissions": ",".join(permissions),
    }


def _blocked_action(factory, tenant_id, project_id):
    with factory() as session:
        action = ProjectMemoryService(session).add_action_item(
            tenant_id,
            ActionItem(
                project_id=project_id,
                title="Resolve production blocker",
                status=ActionItemStatus.BLOCKED,
                due_date=NOW.date() - timedelta(days=1),
                priority="high",
            ),
        )
    return action


def test_attention_signal_is_personal_and_acknowledgement_does_not_change_truth(
    attention_env,
) -> None:
    tenant_id, user_a, project = _seed_project(attention_env)
    user_b = uuid4()
    action = _blocked_action(attention_env, tenant_id, project.id)

    with attention_env() as session:
        service = AttentionCenterService(session)
        first = service.snapshot(
            tenant_id=tenant_id,
            user_id=user_a,
            project_id=project.id,
            permissions={"project:read"},
            now=NOW,
        )
        signal = next(
            item
            for item in first.signals
            if item.signal_key == f"action:blocked:{action.id}"
        )
        assert signal.state == AttentionUserState.UNREAD

        updated = service.update_state(
            tenant_id=tenant_id,
            user_id=user_a,
            project_id=project.id,
            permissions={"project:read"},
            signal_id=signal.id,
            command=AttentionStateCommand(action="acknowledge"),
            now=NOW,
        )
        assert updated.signal.state == AttentionUserState.ACKNOWLEDGED

        other_user = service.snapshot(
            tenant_id=tenant_id,
            user_id=user_b,
            project_id=project.id,
            permissions={"project:read"},
            now=NOW,
        )

    other = next(
        item
        for item in other_user.signals
        if item.signal_key == f"action:blocked:{action.id}"
    )
    assert other.state == AttentionUserState.UNREAD

    with attention_env() as session:
        row = session.get(ActionItemORM, action.id)
        assert row is not None
        assert row.status == ActionItemStatus.BLOCKED.value


def test_changed_problem_version_returns_to_unread(attention_env) -> None:
    tenant_id, user_id, project = _seed_project(attention_env)
    action = _blocked_action(attention_env, tenant_id, project.id)

    with attention_env() as session:
        service = AttentionCenterService(session)
        snapshot = service.snapshot(
            tenant_id=tenant_id,
            user_id=user_id,
            project_id=project.id,
            permissions={"project:read"},
            now=NOW,
        )
        signal = next(
            item
            for item in snapshot.signals
            if item.signal_key == f"action:blocked:{action.id}"
        )
        old_id = signal.id
        service.update_state(
            tenant_id=tenant_id,
            user_id=user_id,
            project_id=project.id,
            permissions={"project:read"},
            signal_id=signal.id,
            command=AttentionStateCommand(action="acknowledge"),
            now=NOW,
        )

    with attention_env() as session:
        row = session.get(ActionItemORM, action.id)
        assert row is not None
        row.updated_at = NOW + timedelta(minutes=5)
        row.priority = "critical"
        session.commit()

    with attention_env() as session:
        current = AttentionCenterService(session).snapshot(
            tenant_id=tenant_id,
            user_id=user_id,
            project_id=project.id,
            permissions={"project:read"},
            now=NOW + timedelta(minutes=6),
        )

    changed = next(
        item
        for item in current.signals
        if item.signal_key == f"action:blocked:{action.id}"
    )
    assert changed.id != old_id
    assert changed.state == AttentionUserState.UNREAD


def test_resolved_condition_disappears_without_closing_notification(
    attention_env,
) -> None:
    tenant_id, user_id, project = _seed_project(attention_env)
    action = _blocked_action(attention_env, tenant_id, project.id)

    with attention_env() as session:
        before = AttentionCenterService(session).snapshot(
            tenant_id=tenant_id,
            user_id=user_id,
            project_id=project.id,
            permissions={"project:read"},
            now=NOW,
        )
    assert any(
        item.signal_key == f"action:blocked:{action.id}"
        for item in before.signals
    )

    with attention_env() as session:
        row = session.get(ActionItemORM, action.id)
        assert row is not None
        row.status = ActionItemStatus.COMPLETED.value
        row.completed_at = NOW
        row.updated_at = NOW
        session.commit()

    with attention_env() as session:
        after = AttentionCenterService(session).snapshot(
            tenant_id=tenant_id,
            user_id=user_id,
            project_id=project.id,
            permissions={"project:read"},
            now=NOW + timedelta(minutes=1),
        )

    assert not any(
        item.signal_key == f"action:blocked:{action.id}"
        for item in after.signals
    )
    assert not any(
        item.signal_key == f"action:overdue:{action.id}"
        for item in after.signals
    )


def test_snooze_expires_back_to_seen(attention_env) -> None:
    tenant_id, user_id, project = _seed_project(attention_env)
    action = _blocked_action(attention_env, tenant_id, project.id)

    with attention_env() as session:
        service = AttentionCenterService(session)
        snapshot = service.snapshot(
            tenant_id=tenant_id,
            user_id=user_id,
            project_id=project.id,
            permissions={"project:read"},
            now=NOW,
        )
        signal = next(
            item
            for item in snapshot.signals
            if item.signal_key == f"action:blocked:{action.id}"
        )
        snoozed = service.update_state(
            tenant_id=tenant_id,
            user_id=user_id,
            project_id=project.id,
            permissions={"project:read"},
            signal_id=signal.id,
            command=AttentionStateCommand(
                action="snooze",
                snoozed_until=NOW + timedelta(hours=1),
            ),
            now=NOW,
        )
        assert snoozed.signal.state == AttentionUserState.SNOOZED

        later = service.snapshot(
            tenant_id=tenant_id,
            user_id=user_id,
            project_id=project.id,
            permissions={"project:read"},
            now=NOW + timedelta(hours=2),
        )

    current = next(
        item
        for item in later.signals
        if item.signal_key == f"action:blocked:{action.id}"
    )
    assert current.state == AttentionUserState.SEEN


def test_pending_inbox_signal_respects_evidence_permissions(attention_env) -> None:
    tenant_id, user_id, project = _seed_project(attention_env)

    with attention_env() as session:
        memory = ProjectMemoryService(session)
        evidence = memory.add_evidence(
            tenant_id,
            Evidence(
                project_id=project.id,
                source_type="document",
                captured_at=NOW,
                content_excerpt="Restricted project update.",
                permission_scope=["project:read", "source:secret"],
            ),
        )
        suggestion = memory.add_ai_suggestion(
            tenant_id,
            AISuggestion(
                project_id=project.id,
                suggestion_type=SuggestionType.NEW_ACTION_ITEM,
                reason="Restricted evidence suggests a follow-up.",
                evidence_ids=[evidence.id],
                confidence=0.9,
            ),
        )

    with attention_env() as session:
        restricted = AttentionCenterService(session).snapshot(
            tenant_id=tenant_id,
            user_id=user_id,
            project_id=project.id,
            permissions={"project:read"},
            now=NOW,
        )
        allowed = AttentionCenterService(session).snapshot(
            tenant_id=tenant_id,
            user_id=user_id,
            project_id=project.id,
            permissions={"project:read", "source:secret"},
            now=NOW,
        )

    assert suggestion.id
    assert not any(
        item.signal_key == "review:pending-inbox"
        for item in restricted.signals
    )
    assert any(
        item.signal_key == "review:pending-inbox"
        for item in allowed.signals
    )


def test_api_allows_personal_attention_state_with_project_read_only(
    attention_env,
) -> None:
    tenant_id, user_id, project = _seed_project(attention_env)
    action = _blocked_action(attention_env, tenant_id, project.id)
    app = create_app(attention_env, allow_trusted_headers=True)

    with TestClient(app) as client:
        response = client.get(
            f"/v1/projects/{project.id}/attention",
            headers=_headers(
                tenant_id,
                user_id,
                "project:read",
            ),
        )
        assert response.status_code == 200
        signal = next(
            item
            for item in response.json()["signals"]
            if item["signal_key"] == f"action:blocked:{action.id}"
        )

        acknowledged = client.post(
            f"/v1/projects/{project.id}/attention/{signal['id']}/state",
            json={"action": "acknowledge"},
            headers=_headers(
                tenant_id,
                user_id,
                "project:read",
            ),
        )

    assert acknowledged.status_code == 200
    assert acknowledged.json()["signal"]["state"] == "acknowledged"


def test_snooze_rejects_past_and_excessive_windows(attention_env) -> None:
    tenant_id, user_id, project = _seed_project(attention_env)
    action = _blocked_action(attention_env, tenant_id, project.id)

    with attention_env() as session:
        service = AttentionCenterService(session)
        snapshot = service.snapshot(
            tenant_id=tenant_id,
            user_id=user_id,
            project_id=project.id,
            permissions={"project:read"},
            now=NOW,
        )
        signal = next(
            item
            for item in snapshot.signals
            if item.signal_key == f"action:blocked:{action.id}"
        )

        with pytest.raises(ValueError, match="future"):
            service.update_state(
                tenant_id=tenant_id,
                user_id=user_id,
                project_id=project.id,
                permissions={"project:read"},
                signal_id=signal.id,
                command=AttentionStateCommand(
                    action="snooze",
                    snoozed_until=NOW - timedelta(minutes=1),
                ),
                now=NOW,
            )

        with pytest.raises(ValueError, match="at most 30 days"):
            service.update_state(
                tenant_id=tenant_id,
                user_id=user_id,
                project_id=project.id,
                permissions={"project:read"},
                signal_id=signal.id,
                command=AttentionStateCommand(
                    action="snooze",
                    snoozed_until=NOW + timedelta(days=31),
                ),
                now=NOW,
            )
