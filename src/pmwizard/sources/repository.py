"""Persistence and sanitized projections for source observability."""

from __future__ import annotations

from datetime import datetime, timezone
from hashlib import sha256
from uuid import UUID, uuid4

from sqlalchemy import select
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
