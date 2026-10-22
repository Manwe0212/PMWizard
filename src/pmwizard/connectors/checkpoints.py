"""Checkpoint abstractions for incremental connector synchronization."""

from __future__ import annotations

from hashlib import sha256
from typing import Protocol, runtime_checkable
from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from pmwizard.persistence.orm import ConnectorCheckpointORM


@runtime_checkable
class CheckpointStore(Protocol):
    def get_checkpoint(
        self,
        *,
        tenant_id: UUID,
        project_id: UUID,
        connector_key: str,
    ) -> str | None:
        ...

    def set_checkpoint(
        self,
        *,
        tenant_id: UUID,
        project_id: UUID,
        connector_key: str,
        cursor: str,
    ) -> None:
        ...


class InMemoryCheckpointStore:
    """Simple checkpoint store for tests, local demos, and V0 composition."""

    def __init__(self) -> None:
        self._values: dict[tuple[UUID, UUID, str], str] = {}

    def get_checkpoint(
        self,
        *,
        tenant_id: UUID,
        project_id: UUID,
        connector_key: str,
    ) -> str | None:
        return self._values.get((tenant_id, project_id, connector_key))

    def set_checkpoint(
        self,
        *,
        tenant_id: UUID,
        project_id: UUID,
        connector_key: str,
        cursor: str,
    ) -> None:
        self._values[(tenant_id, project_id, connector_key)] = cursor


class SQLAlchemyCheckpointStore:
    """Durable opaque checkpoints stored in the PMWizard database.

    Raw cursor values are required to resume provider delta streams but must not
    be returned by source observability APIs. A short SHA-256 fingerprint is
    stored separately for safe operational comparison.
    """

    def __init__(self, session: Session) -> None:
        self.session = session

    def get_checkpoint(
        self,
        *,
        tenant_id: UUID,
        project_id: UUID,
        connector_key: str,
    ) -> str | None:
        return self.session.scalar(
            select(ConnectorCheckpointORM.cursor).where(
                ConnectorCheckpointORM.tenant_id == tenant_id,
                ConnectorCheckpointORM.project_id == project_id,
                ConnectorCheckpointORM.connector_key == connector_key,
            )
        )

    def set_checkpoint(
        self,
        *,
        tenant_id: UUID,
        project_id: UUID,
        connector_key: str,
        cursor: str,
    ) -> None:
        row = self.session.scalar(
            select(ConnectorCheckpointORM).where(
                ConnectorCheckpointORM.tenant_id == tenant_id,
                ConnectorCheckpointORM.project_id == project_id,
                ConnectorCheckpointORM.connector_key == connector_key,
            )
        )
        fingerprint = sha256(cursor.encode("utf-8")).hexdigest()[:16]

        if row is None:
            row = ConnectorCheckpointORM(
                id=uuid4(),
                tenant_id=tenant_id,
                project_id=project_id,
                connector_key=connector_key,
                cursor=cursor,
                fingerprint=fingerprint,
            )
            self.session.add(row)
        else:
            row.cursor = cursor
            row.fingerprint = fingerprint

        self.session.commit()
