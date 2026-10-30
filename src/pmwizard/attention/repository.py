"""Per-user receipt persistence for the Attention Center."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from pmwizard.persistence.orm import AttentionReceiptORM


class AttentionReceiptRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def list_for_project(
        self,
        *,
        tenant_id: UUID,
        user_id: UUID,
        project_id: UUID,
    ) -> dict[str, AttentionReceiptORM]:
        rows = self.session.scalars(
            select(AttentionReceiptORM).where(
                AttentionReceiptORM.tenant_id == tenant_id,
                AttentionReceiptORM.user_id == user_id,
                AttentionReceiptORM.project_id == project_id,
            )
        ).all()
        return {row.signal_key: row for row in rows}

    def get(
        self,
        *,
        tenant_id: UUID,
        user_id: UUID,
        project_id: UUID,
        signal_key: str,
    ) -> AttentionReceiptORM | None:
        return self.session.scalar(
            select(AttentionReceiptORM).where(
                AttentionReceiptORM.tenant_id == tenant_id,
                AttentionReceiptORM.user_id == user_id,
                AttentionReceiptORM.project_id == project_id,
                AttentionReceiptORM.signal_key == signal_key,
            )
        )

    def apply(
        self,
        *,
        tenant_id: UUID,
        user_id: UUID,
        project_id: UUID,
        signal_key: str,
        signal_fingerprint: str,
        action: str,
        now: datetime,
        snoozed_until: datetime | None = None,
    ) -> AttentionReceiptORM:
        row = self.get(
            tenant_id=tenant_id,
            user_id=user_id,
            project_id=project_id,
            signal_key=signal_key,
        )
        if row is None:
            row = AttentionReceiptORM(
                id=uuid4(),
                tenant_id=tenant_id,
                user_id=user_id,
                project_id=project_id,
                signal_key=signal_key,
                signal_fingerprint=signal_fingerprint,
            )
            self.session.add(row)

        if row.signal_fingerprint != signal_fingerprint:
            row.signal_fingerprint = signal_fingerprint
            row.seen_at = None
            row.acknowledged_at = None
            row.snoozed_until = None

        if action == "seen":
            row.seen_at = now
            row.acknowledged_at = None
            row.snoozed_until = None
        elif action == "acknowledge":
            row.seen_at = row.seen_at or now
            row.acknowledged_at = now
            row.snoozed_until = None
        elif action == "snooze":
            row.seen_at = row.seen_at or now
            row.acknowledged_at = None
            row.snoozed_until = snoozed_until
        elif action == "reset":
            row.seen_at = None
            row.acknowledged_at = None
            row.snoozed_until = None
        else:
            raise ValueError("Unsupported Attention state action")

        self.session.commit()
        self.session.refresh(row)
        return row
