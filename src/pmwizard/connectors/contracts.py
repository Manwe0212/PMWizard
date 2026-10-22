"""Common connector contracts for PMWizard Connector Framework V0."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Protocol, runtime_checkable
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from pmwizard.ingestion import SourceRecord


class ConnectorRunStatus(StrEnum):
    SUCCESS = "success"
    PARTIAL = "partial"
    FAILED = "failed"


class ConnectorTestResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    ok: bool
    message: str


class ConnectorPage(BaseModel):
    """One incrementally fetched page from a source connector."""

    model_config = ConfigDict(extra="forbid")

    records: list[SourceRecord] = Field(default_factory=list)
    skips: list[ConnectorSkip] = Field(default_factory=list)
    next_cursor: str | None = None
    has_more: bool = False


class ConnectorSkip(BaseModel):
    model_config = ConfigDict(extra="forbid")

    external_id: str | None = None
    reason: str


class ConnectorError(BaseModel):
    model_config = ConfigDict(extra="forbid")

    stage: str
    message: str
    external_id: str | None = None
    cursor: str | None = None


class ConnectorRunResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    connector_key: str
    status: ConnectorRunStatus
    started_at: datetime
    finished_at: datetime
    start_cursor: str | None = None
    end_cursor: str | None = None

    pages_processed: int = 0
    fetched: int = 0
    ingested: int = 0
    duplicates: int = 0
    source_changed: int = 0
    empty_content: int = 0
    skipped: int = 0
    skips: list[ConnectorSkip] = Field(default_factory=list)
    errors: list[ConnectorError] = Field(default_factory=list)


@runtime_checkable
class SourceConnector(Protocol):
    """Read-only source adapter that emits canonical SourceRecords."""

    @property
    def connector_key(self) -> str:
        """Stable identifier for checkpointing this connector configuration."""
        ...

    def test_connection(self) -> ConnectorTestResult:
        """Perform a lightweight source-connection check."""
        ...

    def fetch_page(
        self,
        *,
        project_id: UUID,
        cursor: str | None,
        limit: int,
    ) -> ConnectorPage:
        """Fetch one page of authorized source records."""
        ...
