"""User-owned notification preference workspace."""

from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID, uuid4

from sqlalchemy.orm import Session

from pmwizard.persistence.orm import NotificationPreferenceORM

from .repository import NotificationRepository
from .schemas import (
    NotificationPreferenceCommand,
    NotificationPreferenceView,
    NotificationWorkspaceSnapshot,
)


class NotificationPreferenceService:
    def __init__(self, session: Session) -> None:
        self.session = session
        self.repository = NotificationRepository(session)

    def snapshot(
        self,
        *,
        tenant_id: UUID,
        user_id: UUID,
        project_id: UUID,
        now: datetime | None = None,
    ) -> NotificationWorkspaceSnapshot:
        timestamp = self._aware(now or datetime.now(timezone.utc))
        user, _ = self.repository.require_user_project(
            tenant_id=tenant_id,
            user_id=user_id,
            project_id=project_id,
        )
        row = self.repository.get_preference(
            tenant_id=tenant_id,
            user_id=user_id,
            project_id=project_id,
        )
        preference = self._view(row, user.email, project_id, timestamp)
        deliveries = self.repository.list_deliveries(
            tenant_id=tenant_id,
            user_id=user_id,
            project_id=project_id,
        )
        return NotificationWorkspaceSnapshot(
            project_id=project_id,
            generated_at=timestamp,
            preference=preference,
            recent_deliveries=[
                self.repository.delivery_view(item)
                for item in deliveries
            ],
        )

    def save(
        self,
        *,
        tenant_id: UUID,
        user_id: UUID,
        project_id: UUID,
        command: NotificationPreferenceCommand,
        now: datetime | None = None,
    ) -> NotificationWorkspaceSnapshot:
        timestamp = self._aware(now or datetime.now(timezone.utc))
        user, _ = self.repository.require_user_project(
            tenant_id=tenant_id,
            user_id=user_id,
            project_id=project_id,
        )
        row = self.repository.get_preference(
            tenant_id=tenant_id,
            user_id=user_id,
            project_id=project_id,
        )
        existing_ref = row.teams_webhook_ref if row is not None else None
        teams_ref = (
            None
            if command.clear_teams_webhook
            else command.teams_webhook_ref or existing_ref
        )
        if command.teams_enabled and teams_ref is None:
            raise ValueError(
                "Configure a Teams webhook alias before enabling Teams delivery."
            )

        if row is None:
            row = NotificationPreferenceORM(
                id=uuid4(),
                tenant_id=tenant_id,
                user_id=user_id,
                project_id=project_id,
                is_enabled=command.enabled,
                email_enabled=command.email_enabled,
                teams_enabled=command.teams_enabled,
                teams_webhook_ref=teams_ref,
                minimum_severity=command.minimum_severity.value,
                categories=[item.value for item in command.categories],
                interval_minutes=command.interval_minutes,
                next_delivery_at=timestamp,
                last_delivery_at=None,
                lease_owner=None,
                lease_expires_at=None,
                created_at=timestamp,
                updated_at=timestamp,
            )
            self.session.add(row)
        else:
            row.is_enabled = command.enabled
            row.email_enabled = command.email_enabled
            row.teams_enabled = command.teams_enabled
            row.teams_webhook_ref = teams_ref
            row.minimum_severity = command.minimum_severity.value
            row.categories = [item.value for item in command.categories]
            row.interval_minutes = command.interval_minutes
            row.next_delivery_at = timestamp
            if not command.enabled:
                row.lease_owner = None
                row.lease_expires_at = None
            row.updated_at = timestamp

        self.session.commit()
        self.session.refresh(row)
        return self.snapshot(
            tenant_id=tenant_id,
            user_id=user_id,
            project_id=project_id,
            now=timestamp,
        )

    @staticmethod
    def _view(
        row: NotificationPreferenceORM | None,
        email: str,
        project_id: UUID,
        now: datetime,
    ) -> NotificationPreferenceView:
        if row is None:
            return NotificationPreferenceView(
                id=None,
                project_id=project_id,
                enabled=False,
                email_enabled=False,
                email_destination=email,
                teams_enabled=False,
                teams_webhook_configured=False,
                minimum_severity="warning",
                categories=[
                    "health",
                    "execution",
                    "raid",
                    "decision",
                    "source",
                    "automation",
                    "review",
                ],
                interval_minutes=60,
                next_delivery_at=now,
                last_delivery_at=None,
                created_at=now,
                updated_at=now,
            )
        return NotificationPreferenceView(
            id=row.id,
            project_id=row.project_id,
            enabled=row.is_enabled,
            email_enabled=row.email_enabled,
            email_destination=email,
            teams_enabled=row.teams_enabled,
            teams_webhook_configured=row.teams_webhook_ref is not None,
            minimum_severity=row.minimum_severity,
            categories=list(row.categories or []),
            interval_minutes=row.interval_minutes,
            next_delivery_at=NotificationPreferenceService._aware(
                row.next_delivery_at
            ),
            last_delivery_at=(
                NotificationPreferenceService._aware(row.last_delivery_at)
                if row.last_delivery_at is not None
                else None
            ),
            created_at=NotificationPreferenceService._aware(row.created_at),
            updated_at=NotificationPreferenceService._aware(row.updated_at),
        )

    @staticmethod
    def _aware(value: datetime) -> datetime:
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value
