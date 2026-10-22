"""Checkpoint abstractions for incremental connector synchronization."""

from __future__ import annotations

from typing import Protocol, runtime_checkable
from uuid import UUID


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
