"""Durable notification preferences, leases and delivery history."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import UUID, uuid4

from sqlalchemy import or_, select, update
from sqlalchemy.orm import Session

from pmwizard.persistence.orm import (
    AppUserORM,
    NotificationDeliveryORM,
    NotificationPreferenceORM,
    ProjectMembershipORM,
    ProjectORM,
)

from .contracts import NotificationPreferenceClaim
from .schemas import (
    NotificationChannel,
    NotificationDeliveryStatus,
    NotificationDeliveryView,
)


class NotificationRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def require_user_project(
        self,
        *,
        tenant_id: UUID,
        user_id: UUID,
        project_id: UUID,
    ) -> tuple[AppUserORM, ProjectMembershipORM]:
        row = self.session.execute(
            select(AppUserORM, ProjectMembershipORM)
            .join(
                ProjectMembershipORM,
                (ProjectMembershipORM.user_id == AppUserORM.id)
                & (ProjectMembershipORM.tenant_id == AppUserORM.tenant_id),
            )
            .join(
                ProjectORM,
                (ProjectORM.id == ProjectMembershipORM.project_id)
                & (ProjectORM.tenant_id == ProjectMembershipORM.tenant_id),
            )
            .where(
                AppUserORM.tenant_id == tenant_id,
                AppUserORM.id == user_id,
                AppUserORM.is_active.is_(True),
                ProjectMembershipORM.project_id == project_id,
                ProjectORM.tenant_id == tenant_id,
            )
        ).first()
        if row is None:
            raise LookupError("User project access not found.")
        return row[0], row[1]

    def get_preference(
        self,
        *,
        tenant_id: UUID,
        user_id: UUID,
        project_id: UUID,
    ) -> NotificationPreferenceORM | None:
        return self.session.scalar(
            select(NotificationPreferenceORM).where(
                NotificationPreferenceORM.tenant_id == tenant_id,
                NotificationPreferenceORM.user_id == user_id,
                NotificationPreferenceORM.project_id == project_id,
            )
        )

    def list_deliveries(
        self,
        *,
        tenant_id: UUID,
        user_id: UUID,
        project_id: UUID,
        limit: int = 20,
    ) -> list[NotificationDeliveryORM]:
        return list(
            self.session.scalars(
                select(NotificationDeliveryORM)
                .where(
                    NotificationDeliveryORM.tenant_id == tenant_id,
                    NotificationDeliveryORM.user_id == user_id,
                    NotificationDeliveryORM.project_id == project_id,
                )
                .order_by(
                    NotificationDeliveryORM.attempted_at.desc(),
                    NotificationDeliveryORM.created_at.desc(),
                )
                .limit(limit)
            ).all()
        )

    def successful_signal_ids(
        self,
        *,
        tenant_id: UUID,
        user_id: UUID,
        project_id: UUID,
        channel: NotificationChannel,
    ) -> set[str]:
        rows = self.session.scalars(
            select(NotificationDeliveryORM).where(
                NotificationDeliveryORM.tenant_id == tenant_id,
                NotificationDeliveryORM.user_id == user_id,
                NotificationDeliveryORM.project_id == project_id,
                NotificationDeliveryORM.channel == channel.value,
                NotificationDeliveryORM.status
                == NotificationDeliveryStatus.SUCCESS.value,
            )
        ).all()
        return {
            signal_id
            for row in rows
            for signal_id in (row.signal_ids or [])
            if isinstance(signal_id, str)
        }

    def record_delivery(
        self,
        *,
        tenant_id: UUID,
        preference_id: UUID,
        user_id: UUID,
        project_id: UUID,
        channel: NotificationChannel,
        status: NotificationDeliveryStatus,
        signal_ids: list[str],
        attempted_at: datetime,
        error_message: str | None = None,
    ) -> NotificationDeliveryORM:
        row = NotificationDeliveryORM(
            id=uuid4(),
            tenant_id=tenant_id,
            preference_id=preference_id,
            user_id=user_id,
            project_id=project_id,
            channel=channel.value,
            status=status.value,
            signal_ids=signal_ids,
            signal_count=len(signal_ids),
            attempted_at=attempted_at,
            delivered_at=(
                attempted_at
                if status == NotificationDeliveryStatus.SUCCESS
                else None
            ),
            error_message=self._sanitize_error(error_message),
        )
        self.session.add(row)
        self.session.commit()
        self.session.refresh(row)
        return row

    def claim_due(
        self,
        *,
        worker_id: str,
        now: datetime,
        lease_seconds: int,
        limit: int,
    ) -> list[NotificationPreferenceClaim]:
        if limit < 1:
            return []
        candidates = list(
            self.session.scalars(
                select(NotificationPreferenceORM.id)
                .where(
                    NotificationPreferenceORM.is_enabled.is_(True),
                    NotificationPreferenceORM.next_delivery_at <= now,
                    or_(
                        NotificationPreferenceORM.lease_expires_at.is_(None),
                        NotificationPreferenceORM.lease_expires_at <= now,
                    ),
                )
                .order_by(
                    NotificationPreferenceORM.next_delivery_at,
                    NotificationPreferenceORM.id,
                )
                .limit(limit)
            ).all()
        )

        claims: list[NotificationPreferenceClaim] = []
        for preference_id in candidates:
            token = f"{worker_id}:{uuid4()}"
            expires_at = now + timedelta(seconds=lease_seconds)
            result = self.session.execute(
                update(NotificationPreferenceORM)
                .where(
                    NotificationPreferenceORM.id == preference_id,
                    NotificationPreferenceORM.is_enabled.is_(True),
                    NotificationPreferenceORM.next_delivery_at <= now,
                    or_(
                        NotificationPreferenceORM.lease_expires_at.is_(None),
                        NotificationPreferenceORM.lease_expires_at <= now,
                    ),
                )
                .values(
                    lease_owner=token,
                    lease_expires_at=expires_at,
                    updated_at=now,
                )
            )
            self.session.commit()
            if result.rowcount != 1:
                continue
            row = self.session.get(NotificationPreferenceORM, preference_id)
            if row is None:
                continue
            claims.append(
                NotificationPreferenceClaim(
                    preference_id=row.id,
                    tenant_id=row.tenant_id,
                    user_id=row.user_id,
                    project_id=row.project_id,
                    lease_token=token,
                )
            )
        return claims

    def finish_claim(
        self,
        *,
        claim: NotificationPreferenceClaim,
        now: datetime,
    ) -> None:
        row = self.session.get(NotificationPreferenceORM, claim.preference_id)
        if row is None:
            return
        if row.lease_owner != claim.lease_token:
            raise RuntimeError("Notification preference lease was lost.")
        row.last_delivery_at = now
        row.next_delivery_at = now + timedelta(minutes=row.interval_minutes)
        row.lease_owner = None
        row.lease_expires_at = None
        row.updated_at = now
        self.session.commit()

    @staticmethod
    def delivery_view(row: NotificationDeliveryORM) -> NotificationDeliveryView:
        return NotificationDeliveryView(
            id=row.id,
            project_id=row.project_id,
            channel=row.channel,
            status=row.status,
            signal_count=row.signal_count,
            signal_ids=list(row.signal_ids or []),
            attempted_at=NotificationRepository._aware(row.attempted_at),
            delivered_at=(
                NotificationRepository._aware(row.delivered_at)
                if row.delivered_at is not None
                else None
            ),
            error_message=row.error_message,
        )

    @staticmethod
    def _sanitize_error(value: str | None) -> str | None:
        if value is None:
            return None
        return " ".join(value.replace("\x00", "").split())[:500]

    @staticmethod
    def _aware(value: datetime) -> datetime:
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value
