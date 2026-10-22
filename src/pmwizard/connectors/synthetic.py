"""Synthetic connector used to validate the connector framework without secrets."""

from __future__ import annotations

from uuid import UUID

from pmwizard.ingestion import SourceRecord

from .contracts import ConnectorDescriptor, ConnectorPage, ConnectorTestResult


class SyntheticConnector:
    """Deterministic paginated connector backed by in-memory SourceRecords."""

    def __init__(
        self,
        records: list[SourceRecord],
        *,
        connector_key: str = "synthetic:v0",
    ) -> None:
        if not connector_key.strip():
            raise ValueError("connector_key must not be empty")
        self._records = list(records)
        self._connector_key = connector_key

    @property
    def connector_key(self) -> str:
        return self._connector_key

    @property
    def descriptor(self) -> ConnectorDescriptor:
        return ConnectorDescriptor(
            source_type="synthetic",
            source_system="synthetic",
            display_name=self._connector_key,
            permission_scope=["project:read"],
            safe_config={},
        )

    def test_connection(self) -> ConnectorTestResult:
        return ConnectorTestResult(
            ok=True,
            message="Synthetic connector is available.",
        )

    def fetch_page(
        self,
        *,
        project_id: UUID,
        cursor: str | None,
        limit: int,
    ) -> ConnectorPage:
        if type(limit) is not int or limit < 1:
            raise ValueError("limit must be a positive integer")

        try:
            offset = int(cursor) if cursor is not None else 0
        except ValueError as exc:
            raise ValueError("Synthetic cursor must be an integer offset") from exc

        if offset < 0:
            raise ValueError("Synthetic cursor must not be negative")

        records = [
            record for record in self._records if record.project_id == project_id
        ]
        page_records = records[offset : offset + limit]
        next_offset = offset + len(page_records)
        has_more = next_offset < len(records)

        return ConnectorPage(
            records=page_records,
            next_cursor=str(next_offset),
            has_more=has_more,
        )
