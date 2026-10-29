"""Built-in Automation V0 task handlers."""

from __future__ import annotations

from uuid import UUID

from sqlalchemy.orm import Session

from pmwizard.health import ProjectHealthHistoryService
from pmwizard.security import SecretProvider
from pmwizard.sources import (
    SourceRuntimeError,
    SourceRuntimeResolver,
    create_durable_connector_runner,
)

from .contracts import AutomationClaim
from .schemas import AutomationTaskType


class HealthSnapshotAutomationHandler:
    task_type = AutomationTaskType.HEALTH_SNAPSHOT

    def execute(
        self,
        *,
        session: Session,
        claim: AutomationClaim,
    ) -> dict:
        result = ProjectHealthHistoryService(session).capture(
            tenant_id=claim.tenant_id,
            project_id=claim.project_id,
            captured_by=None,
            capture_source="automation",
        )
        snapshot = result.snapshot
        return {
            "created": result.created,
            "snapshot_id": str(snapshot.id),
            "score": snapshot.score,
            "band": snapshot.band.value,
            "coverage_percent": snapshot.coverage_percent,
            "captured_at": snapshot.captured_at.isoformat(),
        }



class SourceSyncAutomationHandler:
    task_type = AutomationTaskType.SOURCE_SYNC

    def __init__(
        self,
        secret_provider: SecretProvider,
        *,
        graph_transport_factory=None,
    ) -> None:
        self.secret_provider = secret_provider
        self.graph_transport_factory = graph_transport_factory

    def execute(
        self,
        *,
        session: Session,
        claim: AutomationClaim,
    ) -> dict:
        raw_source_id = claim.config.get("source_connection_id")
        if not isinstance(raw_source_id, str):
            raise SourceRuntimeError(
                "Source sync schedule is missing source_connection_id."
            )
        try:
            source_connection_id = UUID(raw_source_id)
        except ValueError as exc:
            raise SourceRuntimeError(
                "Source sync schedule has an invalid source_connection_id."
            ) from exc

        connector = SourceRuntimeResolver(
            session,
            self.secret_provider,
            graph_transport_factory=self.graph_transport_factory,
        ).resolve(
            tenant_id=claim.tenant_id,
            project_id=claim.project_id,
            source_connection_id=source_connection_id,
        )

        result = create_durable_connector_runner(session).run(
            tenant_id=claim.tenant_id,
            project_id=claim.project_id,
            connector=connector,
        )

        if result.status.value == "failed":
            raise SourceRuntimeError(
                "Scheduled Source sync failed; inspect Sources run telemetry."
            )

        return {
            "source_connection_id": str(source_connection_id),
            "connector_key": connector.connector_key,
            "status": result.status.value,
            "pages_processed": result.pages_processed,
            "fetched": result.fetched,
            "ingested": result.ingested,
            "duplicates": result.duplicates,
            "source_changed": result.source_changed,
            "empty_content": result.empty_content,
            "skipped": result.skipped,
            "error_count": len(result.errors),
        }
