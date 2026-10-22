"""Connector execution orchestration for PMWizard V0."""

from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy.orm import Session

from pmwizard.ingestion import EvidenceIngestionService, IngestionOutcome

from .checkpoints import CheckpointStore
from .contracts import (
    ConnectorError,
    ConnectorRunResult,
    ConnectorRunStatus,
    SourceConnector,
)


class ConnectorRunner:
    """Fetch source pages, ingest records, and advance checkpoints safely.

    Checkpoints advance only after an entire page is processed without an
    unexpected error. Re-reading a page after failure is safe because Ingestion
    V0 is idempotent.
    """

    def __init__(
        self,
        session: Session,
        checkpoint_store: CheckpointStore,
        *,
        ingestion: EvidenceIngestionService | None = None,
    ) -> None:
        self.session = session
        self.checkpoint_store = checkpoint_store
        self.ingestion = ingestion or EvidenceIngestionService(session)

    def run(
        self,
        *,
        tenant_id: UUID,
        project_id: UUID,
        connector: SourceConnector,
        page_size: int = 100,
        max_pages: int = 100,
    ) -> ConnectorRunResult:
        if type(page_size) is not int or page_size < 1:
            raise ValueError("page_size must be a positive integer")
        if type(max_pages) is not int or max_pages < 1:
            raise ValueError("max_pages must be a positive integer")

        started_at = datetime.now(timezone.utc)
        start_cursor = self.checkpoint_store.get_checkpoint(
            tenant_id=tenant_id,
            project_id=project_id,
            connector_key=connector.connector_key,
        )
        cursor = start_cursor

        pages_processed = 0
        fetched = 0
        ingested = 0
        duplicates = 0
        source_changed = 0
        empty_content = 0
        errors: list[ConnectorError] = []
        status = ConnectorRunStatus.SUCCESS
        more_remaining = False

        for _ in range(max_pages):
            try:
                page = connector.fetch_page(
                    project_id=project_id,
                    cursor=cursor,
                    limit=page_size,
                )
            except Exception as exc:  # connector boundary: report, do not hide
                errors.append(
                    ConnectorError(
                        stage="fetch",
                        message=f"{type(exc).__name__}: {exc}",
                        cursor=cursor,
                    )
                )
                status = (
                    ConnectorRunStatus.FAILED
                    if pages_processed == 0
                    else ConnectorRunStatus.PARTIAL
                )
                break

            if page.has_more and page.next_cursor is None:
                errors.append(
                    ConnectorError(
                        stage="contract",
                        message="Connector returned has_more=true without next_cursor.",
                        cursor=cursor,
                    )
                )
                status = (
                    ConnectorRunStatus.FAILED
                    if pages_processed == 0
                    else ConnectorRunStatus.PARTIAL
                )
                break

            page_failed = False
            for record in page.records:
                fetched += 1
                if record.project_id != project_id:
                    errors.append(
                        ConnectorError(
                            stage="mapping",
                            message=(
                                "Connector emitted a SourceRecord for a different project."
                            ),
                            external_id=record.external_id,
                            cursor=cursor,
                        )
                    )
                    page_failed = True
                    continue

                try:
                    result = self.ingestion.ingest(tenant_id, record)
                except Exception as exc:
                    errors.append(
                        ConnectorError(
                            stage="ingestion",
                            message=f"{type(exc).__name__}: {exc}",
                            external_id=record.external_id,
                            cursor=cursor,
                        )
                    )
                    page_failed = True
                    continue

                if result.outcome == IngestionOutcome.INGESTED:
                    ingested += 1
                elif result.outcome == IngestionOutcome.DUPLICATE:
                    duplicates += 1
                elif result.outcome == IngestionOutcome.SOURCE_CHANGED:
                    source_changed += 1
                elif result.outcome == IngestionOutcome.EMPTY_CONTENT:
                    empty_content += 1

            if page_failed:
                status = (
                    ConnectorRunStatus.FAILED
                    if pages_processed == 0
                    else ConnectorRunStatus.PARTIAL
                )
                break

            pages_processed += 1

            if page.next_cursor is not None:
                self.checkpoint_store.set_checkpoint(
                    tenant_id=tenant_id,
                    project_id=project_id,
                    connector_key=connector.connector_key,
                    cursor=page.next_cursor,
                )
                cursor = page.next_cursor

            more_remaining = page.has_more
            if not page.has_more:
                break
        else:
            if more_remaining:
                status = ConnectorRunStatus.PARTIAL
                errors.append(
                    ConnectorError(
                        stage="runner",
                        message="Maximum page limit reached before connector exhaustion.",
                        cursor=cursor,
                    )
                )

        finished_at = datetime.now(timezone.utc)
        return ConnectorRunResult(
            connector_key=connector.connector_key,
            status=status,
            started_at=started_at,
            finished_at=finished_at,
            start_cursor=start_cursor,
            end_cursor=cursor,
            pages_processed=pages_processed,
            fetched=fetched,
            ingested=ingested,
            duplicates=duplicates,
            source_changed=source_changed,
            empty_content=empty_content,
            errors=errors,
        )
