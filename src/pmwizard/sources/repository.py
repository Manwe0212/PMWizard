"""Persistence and sanitized projections for source observability."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from hashlib import sha256
from uuid import UUID, uuid4

from sqlalchemy import delete, or_, select, update
from sqlalchemy.orm import Session

from pmwizard.connectors import ConnectorDescriptor, ConnectorRunResult
from pmwizard.persistence.orm import (
    ConnectorCheckpointORM,
    ConnectorRunORM,
    ProjectORM,
    SourceConnectionORM,
)


def checkpoint_fingerprint(cursor: str | None) -> str | None:
    if cursor is None:
        return None
    return sha256(cursor.encode("utf-8")).hexdigest()[:16]


@dataclass(frozen=True)
class SourceConnectionTestClaim:
    tenant_id: UUID
    project_id: UUID
    source_connection_id: UUID
    lease_token: str


class SourceRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def require_project(self, tenant_id: UUID, project_id: UUID) -> None:
        exists = self.session.scalar(
            select(ProjectORM.id).where(
                ProjectORM.tenant_id == tenant_id,
                ProjectORM.id == project_id,
            )
        )
        if exists is None:
            raise LookupError("Project not found for tenant")

    def upsert_connection(
        self,
        *,
        tenant_id: UUID,
        project_id: UUID,
        connector_key: str,
        descriptor: ConnectorDescriptor,
    ) -> SourceConnectionORM:
        self.require_project(tenant_id, project_id)
        row = self.session.scalar(
            select(SourceConnectionORM).where(
                SourceConnectionORM.tenant_id == tenant_id,
                SourceConnectionORM.project_id == project_id,
                SourceConnectionORM.connector_key == connector_key,
            )
        )
        if row is None:
            row = SourceConnectionORM(
                id=uuid4(),
                tenant_id=tenant_id,
                project_id=project_id,
                connector_key=connector_key,
                source_type=descriptor.source_type,
                source_system=descriptor.source_system,
                display_name=descriptor.display_name,
                permission_scope=descriptor.permission_scope,
                safe_config=descriptor.safe_config,
                is_enabled=True,
            )
            self.session.add(row)
        else:
            row.source_type = descriptor.source_type
            row.source_system = descriptor.source_system
            row.display_name = descriptor.display_name
            row.permission_scope = descriptor.permission_scope
            row.safe_config = descriptor.safe_config
        self.session.flush()
        return row

    def get_connection(
        self,
        *,
        tenant_id: UUID,
        project_id: UUID,
        connector_key: str,
    ) -> SourceConnectionORM | None:
        return self.session.scalar(
            select(SourceConnectionORM).where(
                SourceConnectionORM.tenant_id == tenant_id,
                SourceConnectionORM.project_id == project_id,
                SourceConnectionORM.connector_key == connector_key,
            )
        )

    def get_connection_by_id(
        self,
        *,
        tenant_id: UUID,
        project_id: UUID,
        source_connection_id: UUID,
    ) -> SourceConnectionORM | None:
        return self.session.scalar(
            select(SourceConnectionORM).where(
                SourceConnectionORM.tenant_id == tenant_id,
                SourceConnectionORM.project_id == project_id,
                SourceConnectionORM.id == source_connection_id,
            )
        )

    def create_admin_connection(
        self,
        *,
        tenant_id: UUID,
        project_id: UUID,
        source_connection_id: UUID,
        connector_key: str,
        descriptor: ConnectorDescriptor,
        enabled: bool,
    ) -> SourceConnectionORM:
        self.require_project(tenant_id, project_id)
        row = SourceConnectionORM(
            id=source_connection_id,
            tenant_id=tenant_id,
            project_id=project_id,
            connector_key=connector_key,
            source_type=descriptor.source_type,
            source_system=descriptor.source_system,
            display_name=descriptor.display_name,
            permission_scope=descriptor.permission_scope,
            safe_config=descriptor.safe_config,
            is_enabled=enabled,
        )
        self.session.add(row)
        self.session.flush()
        return row

    def update_admin_connection(
        self,
        *,
        tenant_id: UUID,
        project_id: UUID,
        source_connection_id: UUID,
        display_name: str | None = None,
        safe_config: dict | None = None,
        enabled: bool | None = None,
    ) -> SourceConnectionORM:
        row = self.get_connection_by_id(
            tenant_id=tenant_id,
            project_id=project_id,
            source_connection_id=source_connection_id,
        )
        if row is None:
            raise LookupError("Source connection not found")
        if display_name is not None:
            row.display_name = display_name
        if safe_config is not None:
            row.safe_config = safe_config
        if enabled is not None:
            row.is_enabled = enabled
        self.session.flush()
        return row

    def clear_checkpoint(
        self,
        *,
        tenant_id: UUID,
        project_id: UUID,
        connector_key: str,
    ) -> None:
        self.session.execute(
            delete(ConnectorCheckpointORM).where(
                ConnectorCheckpointORM.tenant_id == tenant_id,
                ConnectorCheckpointORM.project_id == project_id,
                ConnectorCheckpointORM.connector_key == connector_key,
            )
        )
        self.session.flush()

    def queue_connection_test(
        self,
        *,
        tenant_id: UUID,
        project_id: UUID,
        source_connection_id: UUID,
        requested_by: UUID,
        now: datetime,
    ) -> SourceConnectionORM:
        row = self.get_connection_by_id(
            tenant_id=tenant_id,
            project_id=project_id,
            source_connection_id=source_connection_id,
        )
        if row is None:
            raise LookupError("Source connection not found")
        if row.test_lease_expires_at is not None:
            lease_expiry = self._aware(row.test_lease_expires_at)
            if lease_expiry > now:
                raise ValueError("Source connection test is already running")
        row.test_requested_at = now
        row.test_requested_by = requested_by
        self.session.flush()
        return row

    def claim_pending_tests(
        self,
        *,
        worker_id: str,
        now: datetime,
        lease_seconds: int,
        limit: int,
    ) -> list[SourceConnectionTestClaim]:
        candidates = list(
            self.session.scalars(
                select(SourceConnectionORM)
                .where(
                    SourceConnectionORM.is_enabled.is_(True),
                    SourceConnectionORM.credential_ref.is_not(None),
                    SourceConnectionORM.test_requested_at.is_not(None),
                    or_(
                        SourceConnectionORM.last_test_at.is_(None),
                        SourceConnectionORM.last_test_at
                        < SourceConnectionORM.test_requested_at,
                    ),
                    or_(
                        SourceConnectionORM.test_lease_expires_at.is_(None),
                        SourceConnectionORM.test_lease_expires_at <= now,
                    ),
                )
                .order_by(
                    SourceConnectionORM.test_requested_at,
                    SourceConnectionORM.id,
                )
                .limit(limit)
            ).all()
        )

        claims: list[SourceConnectionTestClaim] = []
        for row in candidates:
            lease_token = f"{worker_id}:{uuid4().hex}"
            updated = self.session.execute(
                update(SourceConnectionORM)
                .where(
                    SourceConnectionORM.id == row.id,
                    SourceConnectionORM.tenant_id == row.tenant_id,
                    SourceConnectionORM.project_id == row.project_id,
                    or_(
                        SourceConnectionORM.test_lease_expires_at.is_(None),
                        SourceConnectionORM.test_lease_expires_at <= now,
                    ),
                )
                .values(
                    test_lease_owner=lease_token,
                    test_lease_expires_at=now + timedelta(seconds=lease_seconds),
                )
            )
            if updated.rowcount == 1:
                claims.append(
                    SourceConnectionTestClaim(
                        tenant_id=row.tenant_id,
                        project_id=row.project_id,
                        source_connection_id=row.id,
                        lease_token=lease_token,
                    )
                )
        self.session.commit()
        return claims

    def finish_connection_test(
        self,
        *,
        claim: SourceConnectionTestClaim,
        now: datetime,
        status: str,
        message: str,
    ) -> None:
        row = self.get_connection_by_id(
            tenant_id=claim.tenant_id,
            project_id=claim.project_id,
            source_connection_id=claim.source_connection_id,
        )
        if row is None:
            raise LookupError("Source connection not found")

        lease_expiry = (
            self._aware(row.test_lease_expires_at)
            if row.test_lease_expires_at is not None
            else None
        )
        if (
            row.test_lease_owner != claim.lease_token
            or lease_expiry is None
            or lease_expiry <= now
        ):
            raise RuntimeError(
                "Source connection test lease was lost or expired"
            )

        row.last_test_at = now
        row.last_test_status = status
        row.last_test_message = message[:1000]
        row.test_lease_owner = None
        row.test_lease_expires_at = None
        self.session.commit()

    @staticmethod
    def _aware(value: datetime) -> datetime:
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value

    def bind_credential_reference(
        self,
        *,
        tenant_id: UUID,
        project_id: UUID,
        source_connection_id: UUID,
        credential_ref: str | None,
    ) -> SourceConnectionORM:
        row = self.get_connection_by_id(
            tenant_id=tenant_id,
            project_id=project_id,
            source_connection_id=source_connection_id,
        )
        if row is None:
            raise LookupError("Source connection not found")
        row.credential_ref = credential_ref
        self.session.flush()
        return row

    def list_connections(
        self,
        *,
        tenant_id: UUID,
        project_id: UUID,
    ) -> list[SourceConnectionORM]:
        return list(
            self.session.scalars(
                select(SourceConnectionORM)
                .where(
                    SourceConnectionORM.tenant_id == tenant_id,
                    SourceConnectionORM.project_id == project_id,
                )
                .order_by(
                    SourceConnectionORM.source_system,
                    SourceConnectionORM.display_name,
                    SourceConnectionORM.id,
                )
            ).all()
        )

    def get_checkpoint(
        self,
        *,
        tenant_id: UUID,
        project_id: UUID,
        connector_key: str,
    ) -> ConnectorCheckpointORM | None:
        return self.session.scalar(
            select(ConnectorCheckpointORM).where(
                ConnectorCheckpointORM.tenant_id == tenant_id,
                ConnectorCheckpointORM.project_id == project_id,
                ConnectorCheckpointORM.connector_key == connector_key,
            )
        )

    def list_runs(
        self,
        *,
        tenant_id: UUID,
        project_id: UUID,
        connector_key: str,
        limit: int = 5,
    ) -> list[ConnectorRunORM]:
        return list(
            self.session.scalars(
                select(ConnectorRunORM)
                .where(
                    ConnectorRunORM.tenant_id == tenant_id,
                    ConnectorRunORM.project_id == project_id,
                    ConnectorRunORM.connector_key == connector_key,
                )
                .order_by(
                    ConnectorRunORM.finished_at.desc(),
                    ConnectorRunORM.created_at.desc(),
                )
                .limit(limit)
            ).all()
        )

    def record_run(
        self,
        *,
        tenant_id: UUID,
        project_id: UUID,
        connector_key: str,
        descriptor: ConnectorDescriptor | None,
        result: ConnectorRunResult,
    ) -> ConnectorRunORM:
        connection = None
        if descriptor is not None:
            connection = self.upsert_connection(
                tenant_id=tenant_id,
                project_id=project_id,
                connector_key=connector_key,
                descriptor=descriptor,
            )

        row = ConnectorRunORM(
            id=uuid4(),
            tenant_id=tenant_id,
            project_id=project_id,
            source_connection_id=connection.id if connection is not None else None,
            connector_key=connector_key,
            status=result.status.value,
            started_at=result.started_at,
            finished_at=result.finished_at,
            pages_processed=result.pages_processed,
            fetched=result.fetched,
            ingested=result.ingested,
            duplicates=result.duplicates,
            source_changed=result.source_changed,
            empty_content=result.empty_content,
            skipped=result.skipped,
            skips=[
                {
                    "external_id": skip.external_id,
                    "reason": skip.reason,
                }
                for skip in result.skips[:100]
            ],
            errors=[
                {
                    "stage": error.stage,
                    "message": error.message,
                    "external_id": error.external_id,
                }
                for error in result.errors[:100]
            ],
            start_checkpoint_present=result.start_cursor is not None,
            end_checkpoint_present=result.end_cursor is not None,
            checkpoint_fingerprint=checkpoint_fingerprint(result.end_cursor),
            created_at=datetime.now(timezone.utc),
        )
        self.session.add(row)
        self.session.flush()
        return row
