"""Tests for Notification Delivery & Preferences V0."""

from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from pmwizard.api import create_app
from pmwizard.attention import AttentionCenterService, AttentionUserState
from pmwizard.auth import AuthRepository
from pmwizard.models import ActionItem, Project
from pmwizard.models.enums import ActionItemStatus
from pmwizard.notifications import (
    NotificationDeliveryWorker,
    NotificationPreferenceCommand,
    NotificationPreferenceService,
)
from pmwizard.persistence import Base, ProjectMemoryService
from pmwizard.persistence.orm import (
    ActionItemORM,
    AttentionReceiptORM,
    NotificationDeliveryORM,
)


NOW = datetime(2026, 10, 30, 18, 30, tzinfo=timezone.utc)


@pytest.fixture()
def notification_env():
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


def _seed_user_project(factory):
    tenant_id = uuid4()
    user_id = uuid4()

    with factory() as session:
        project = ProjectMemoryService(session).create_project(
            tenant_id,
            Project(name="Notification Demo"),
        )

    with factory() as session:
        auth = AuthRepository(session)
        user = auth.create_user(
            tenant_id=tenant_id,
            email="pm@example.com",
            display_name="Project Manager",
            password_hash="test-hash",
        )
        assert user.id != user_id
        user_id = user.id
        auth.add_project_membership(
            tenant_id=tenant_id,
            user_id=user_id,
            project_id=project.id,
            role="project_manager",
            permissions=["project:read", "project:review"],
        )
        session.commit()

    return tenant_id, user_id, project


def _blocked_action(factory, tenant_id, project_id):
    with factory() as session:
        return ProjectMemoryService(session).add_action_item(
            tenant_id,
            ActionItem(
                project_id=project_id,
                title="Resolve production blocker",
                status=ActionItemStatus.BLOCKED,
                due_date=NOW.date() - timedelta(days=1),
                priority="high",
            ),
        )


class FakeEmailProvider:
    def __init__(self) -> None:
        self.calls: list[dict] = []

    def send(self, *, to_email: str, subject: str, text: str) -> None:
        self.calls.append(
            {
                "to_email": to_email,
                "subject": subject,
                "text": text,
            }
        )


class LeakingEmailProvider:
    def send(self, *, to_email: str, subject: str, text: str) -> None:
        raise RuntimeError(
            "smtp password TOP-SECRET and https://secret.example/token"
        )


class FakeTeamsProvider:
    def __init__(self) -> None:
        self.calls: list[dict] = []

    def send(
        self,
        *,
        webhook_reference: str,
        title: str,
        text: str,
    ) -> None:
        self.calls.append(
            {
                "webhook_reference": webhook_reference,
                "title": title,
                "text": text,
            }
        )


def _save_execution_email_pref(
    factory,
    tenant_id,
    user_id,
    project_id,
    *,
    now=NOW,
) -> None:
    with factory() as session:
        NotificationPreferenceService(session).save(
            tenant_id=tenant_id,
            user_id=user_id,
            project_id=project_id,
            command=NotificationPreferenceCommand(
                enabled=True,
                email_enabled=True,
                teams_enabled=False,
                minimum_severity="warning",
                categories=["execution"],
                interval_minutes=60,
            ),
            now=now,
        )


def test_default_preferences_are_non_persistent_and_use_account_email(
    notification_env,
) -> None:
    tenant_id, user_id, project = _seed_user_project(notification_env)

    with notification_env() as session:
        snapshot = NotificationPreferenceService(session).snapshot(
            tenant_id=tenant_id,
            user_id=user_id,
            project_id=project.id,
            now=NOW,
        )

    assert snapshot.preference.id is None
    assert snapshot.preference.project_id == project.id
    assert snapshot.preference.email_destination == "pm@example.com"
    assert snapshot.preference.enabled is False


def test_notification_delivery_deduplicates_signal_versions_and_preserves_unread(
    notification_env,
) -> None:
    tenant_id, user_id, project = _seed_user_project(notification_env)
    action = _blocked_action(
        notification_env,
        tenant_id,
        project.id,
    )
    _save_execution_email_pref(
        notification_env,
        tenant_id,
        user_id,
        project.id,
    )
    email = FakeEmailProvider()
    worker = NotificationDeliveryWorker(
        notification_env,
        worker_id="notify-worker",
        email_provider=email,
        lease_seconds=60,
    )

    assert worker.run_once(now=NOW) == 1
    assert len(email.calls) == 1
    assert email.calls[0]["to_email"] == "pm@example.com"
    assert "Resolve production blocker" in email.calls[0]["text"]

    with notification_env() as session:
        attention = AttentionCenterService(session).snapshot(
            tenant_id=tenant_id,
            user_id=user_id,
            project_id=project.id,
            permissions={"project:read", "project:review"},
            now=NOW,
        )
        signal = next(
            item
            for item in attention.signals
            if item.signal_key == f"action:blocked:{action.id}"
        )
        assert signal.state == AttentionUserState.UNREAD
        receipts = session.scalars(select(AttentionReceiptORM)).all()
        assert receipts == []

    assert worker.run_once(now=NOW + timedelta(minutes=60)) == 1
    assert len(email.calls) == 1

    with notification_env() as session:
        row = session.get(ActionItemORM, action.id)
        assert row is not None
        row.priority = "critical"
        row.updated_at = NOW + timedelta(minutes=61)
        session.commit()

    assert worker.run_once(now=NOW + timedelta(minutes=120)) == 1
    assert len(email.calls) == 2

    with notification_env() as session:
        deliveries = session.scalars(
            select(NotificationDeliveryORM).where(
                NotificationDeliveryORM.status == "success"
            )
        ).all()
    assert len(deliveries) == 2
    assert deliveries[0].signal_ids != deliveries[1].signal_ids


def test_provider_failure_is_sanitized_and_retried_next_interval(
    notification_env,
) -> None:
    tenant_id, user_id, project = _seed_user_project(notification_env)
    _blocked_action(notification_env, tenant_id, project.id)
    _save_execution_email_pref(
        notification_env,
        tenant_id,
        user_id,
        project.id,
    )
    worker = NotificationDeliveryWorker(
        notification_env,
        worker_id="notify-worker",
        email_provider=LeakingEmailProvider(),
        lease_seconds=60,
    )

    worker.run_once(now=NOW)
    worker.run_once(now=NOW + timedelta(minutes=60))

    with notification_env() as session:
        rows = session.scalars(
            select(NotificationDeliveryORM)
            .where(NotificationDeliveryORM.channel == "email")
            .order_by(NotificationDeliveryORM.attempted_at)
        ).all()

    assert len(rows) == 2
    assert all(row.status == "failed" for row in rows)
    serialized = " ".join(row.error_message or "" for row in rows)
    assert "TOP-SECRET" not in serialized
    assert "secret.example" not in serialized
    assert serialized.count("Email notification delivery failed.") == 2


def test_teams_delivery_uses_opaque_alias_only(notification_env) -> None:
    tenant_id, user_id, project = _seed_user_project(notification_env)
    _blocked_action(notification_env, tenant_id, project.id)

    with notification_env() as session:
        snapshot = NotificationPreferenceService(session).save(
            tenant_id=tenant_id,
            user_id=user_id,
            project_id=project.id,
            command=NotificationPreferenceCommand(
                enabled=True,
                email_enabled=False,
                teams_enabled=True,
                teams_webhook_ref="env:TEAMS_PROJECT_ALERTS",
                minimum_severity="warning",
                categories=["execution"],
                interval_minutes=60,
            ),
            now=NOW,
        )
    assert snapshot.preference.teams_webhook_configured is True
    assert not hasattr(snapshot.preference, "teams_webhook_ref")

    teams = FakeTeamsProvider()
    worker = NotificationDeliveryWorker(
        notification_env,
        worker_id="notify-worker",
        teams_provider=teams,
        lease_seconds=60,
    )
    worker.run_once(now=NOW)

    assert len(teams.calls) == 1
    assert teams.calls[0]["webhook_reference"] == "env:TEAMS_PROJECT_ALERTS"


def test_api_rejects_destination_override_and_unsafe_teams_alias(
    notification_env,
) -> None:
    tenant_id, user_id, project = _seed_user_project(notification_env)
    app = create_app(notification_env, allow_trusted_headers=True)
    headers = {
        "X-PMWizard-Tenant-ID": str(tenant_id),
        "X-PMWizard-User-ID": str(user_id),
        "X-PMWizard-Permissions": "project:read",
    }

    with TestClient(app) as client:
        default = client.get(
            f"/v1/projects/{project.id}/notifications",
            headers=headers,
        )
        redirected = client.put(
            f"/v1/projects/{project.id}/notifications",
            headers=headers,
            json={
                "enabled": True,
                "email_enabled": True,
                "email_destination": "attacker@example.com",
                "teams_enabled": False,
                "minimum_severity": "warning",
                "categories": ["health"],
                "interval_minutes": 60,
            },
        )
        unsafe = client.put(
            f"/v1/projects/{project.id}/notifications",
            headers=headers,
            json={
                "enabled": True,
                "email_enabled": False,
                "teams_enabled": True,
                "teams_webhook_ref": "env:GRAPH_ADMIN",
                "minimum_severity": "warning",
                "categories": ["health"],
                "interval_minutes": 60,
            },
        )

    assert default.status_code == 200
    assert default.json()["preference"]["email_destination"] == "pm@example.com"
    assert redirected.status_code == 422
    assert unsafe.status_code == 422


def test_disabled_categories_and_severity_filter_delivery(
    notification_env,
) -> None:
    tenant_id, user_id, project = _seed_user_project(notification_env)
    _blocked_action(notification_env, tenant_id, project.id)

    with notification_env() as session:
        NotificationPreferenceService(session).save(
            tenant_id=tenant_id,
            user_id=user_id,
            project_id=project.id,
            command=NotificationPreferenceCommand(
                enabled=True,
                email_enabled=True,
                teams_enabled=False,
                minimum_severity="critical",
                categories=["source"],
                interval_minutes=60,
            ),
            now=NOW,
        )

    email = FakeEmailProvider()
    worker = NotificationDeliveryWorker(
        notification_env,
        worker_id="notify-worker",
        email_provider=email,
        lease_seconds=60,
    )
    worker.run_once(now=NOW)
    assert email.calls == []
