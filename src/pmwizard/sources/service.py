"""Sources telemetry recording and read-only workspace projection."""

from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy.orm import Session

from pmwizard.connectors import (
    ConnectorDescriptor,
    ConnectorRunResult,
    ConnectorRunStatus,
)

from .repository import SourceRepository
from .schemas import (
    BindSourceCredentialRequest,
    SourceConnectionTestStatus,
    SourceConnectionTestView,
    SourceConnectionView,
    SourceCredentialStatus,
    SourceHealthStatus,
    SourceRunView,
    SourcesSummary,
    SourcesWorkspaceSnapshot,
)


class SourceTelemetryService:
    """Persist sanitized connector metadata and run history."""

    def __init__(self, session: Session) -> None:
        self.session = session
        self.repository = SourceRepository(session)

    def register_connection(
        self,
        *,
        tenant_id: UUID,
        project_id: UUID,
        connector_key: str,
        descriptor: ConnectorDescriptor,
    ) -> None:
        self.repository.upsert_connection(
            tenant_id=tenant_id,
            project_id=project_id,
            connector_key=connector_key,
            descriptor=descriptor,
        )
        self.session.commit()

    def record_run(
        self,
        *,
        tenant_id: UUID,
        project_id: UUID,
        connector_key: str,
        descriptor: ConnectorDescriptor | None,
        result: ConnectorRunResult,
    ) -> None:
        self.repository.record_run(
            tenant_id=tenant_id,
            project_id=project_id,
            connector_key=connector_key,
            descriptor=descriptor,
            result=result,
        )
        self.session.commit()


class SourceCredentialService:
    """Bind opaque runtime references without reading secret material."""

    def __init__(self, session: Session) -> None:
        self.session = session
        self.repository = SourceRepository(session)

    def bind(
        self,
        *,
        tenant_id: UUID,
        project_id: UUID,
        source_connection_id: UUID,
        command: BindSourceCredentialRequest,
    ) -> SourceCredentialStatus:
        row = self.repository.bind_credential_reference(
            tenant_id=tenant_id,
            project_id=project_id,
            source_connection_id=source_connection_id,
            credential_ref=command.credential_ref,
        )
        self.session.commit()
        return SourceCredentialStatus(
            source_connection_id=row.id,
            credential_configured=True,
        )

    def clear(
        self,
        *,
        tenant_id: UUID,
        project_id: UUID,
        source_connection_id: UUID,
    ) -> SourceCredentialStatus:
        row = self.repository.bind_credential_reference(
            tenant_id=tenant_id,
            project_id=project_id,
            source_connection_id=source_connection_id,
            credential_ref=None,
        )
        self.session.commit()
        return SourceCredentialStatus(
            source_connection_id=row.id,
            credential_configured=False,
        )


class SourcesWorkspaceService:
    def __init__(self, session: Session) -> None:
        self.session = session
        self.repository = SourceRepository(session)

    def snapshot(
        self,
        *,
        tenant_id: UUID,
        project_id: UUID,
    ) -> SourcesWorkspaceSnapshot:
        self.repository.require_project(tenant_id, project_id)
        views: list[SourceConnectionView] = []

        for connection in self.repository.list_connections(
            tenant_id=tenant_id,
            project_id=project_id,
        ):
            checkpoint = self.repository.get_checkpoint(
                tenant_id=tenant_id,
                project_id=project_id,
                connector_key=connection.connector_key,
            )
            run_rows = self.repository.list_runs(
                tenant_id=tenant_id,
                project_id=project_id,
                connector_key=connection.connector_key,
                limit=5,
            )
            runs = [self._run_view(row) for row in run_rows]
            latest = runs[0] if runs else None

            views.append(
                SourceConnectionView(
                    id=connection.id,
                    connector_key=connection.connector_key,
                    source_type=connection.source_type,
                    source_system=connection.source_system,
                    display_name=connection.display_name,
                    permission_scope=connection.permission_scope,
                    safe_config=connection.safe_config,
                    is_enabled=connection.is_enabled,
                    credential_configured=bool(connection.credential_ref),
                    health=self._health(connection.is_enabled, latest),
                    checkpoint_present=checkpoint is not None,
                    checkpoint_fingerprint=(
                        checkpoint.fingerprint if checkpoint is not None else None
                    ),
                    checkpoint_updated_at=(
                        checkpoint.updated_at if checkpoint is not None else None
                    ),
                    latest_run=latest,
                    recent_runs=runs,
                    connection_test=self._test_view(connection),
                )
            )

        return SourcesWorkspaceSnapshot(
            project_id=project_id,
            summary=SourcesSummary(
                total=len(views),
                healthy=sum(item.health == SourceHealthStatus.HEALTHY for item in views),
                attention=sum(
                    item.health == SourceHealthStatus.ATTENTION for item in views
                ),
                failed=sum(item.health == SourceHealthStatus.FAILED for item in views),
                never_synced=sum(
                    item.health == SourceHealthStatus.NEVER_SYNCED for item in views
                ),
                disabled=sum(
                    item.health == SourceHealthStatus.DISABLED for item in views
                ),
                total_ingested=sum(
                    item.latest_run.ingested
                    for item in views
                    if item.latest_run is not None
                ),
                total_skipped=sum(
                    item.latest_run.skipped
                    for item in views
                    if item.latest_run is not None
                ),
                total_errors=sum(
                    len(item.latest_run.errors)
                    for item in views
                    if item.latest_run is not None
                ),
            ),
            sources=views,
        )

    @classmethod
    def _test_view(cls, connection) -> SourceConnectionTestView:
        now = datetime.now(timezone.utc)
        requested_at = (
            cls._aware(connection.test_requested_at)
            if connection.test_requested_at is not None
            else None
        )
        last_test_at = (
            cls._aware(connection.last_test_at)
            if connection.last_test_at is not None
            else None
        )
        lease_expires_at = (
            cls._aware(connection.test_lease_expires_at)
            if connection.test_lease_expires_at is not None
            else None
        )

        if (
            connection.test_lease_owner is not None
            and lease_expires_at is not None
            and lease_expires_at > now
        ):
            status = SourceConnectionTestStatus.RUNNING
        elif (
            requested_at is not None
            and (last_test_at is None or requested_at > last_test_at)
        ):
            status = SourceConnectionTestStatus.QUEUED
        elif connection.last_test_status == "success":
            status = SourceConnectionTestStatus.SUCCESS
        elif connection.last_test_status == "failed":
            status = SourceConnectionTestStatus.FAILED
        else:
            status = SourceConnectionTestStatus.NEVER_TESTED

        return SourceConnectionTestView(
            status=status,
            requested_at=requested_at,
            last_test_at=last_test_at,
            message=connection.last_test_message,
        )

    @staticmethod
    def _aware(value: datetime) -> datetime:
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value

    @staticmethod
    def _health(
        enabled: bool,
        latest: SourceRunView | None,
    ) -> SourceHealthStatus:
        if not enabled:
            return SourceHealthStatus.DISABLED
        if latest is None:
            return SourceHealthStatus.NEVER_SYNCED
        if latest.status == ConnectorRunStatus.FAILED:
            return SourceHealthStatus.FAILED
        if (
            latest.status == ConnectorRunStatus.PARTIAL
            or latest.skipped > 0
            or len(latest.errors) > 0
        ):
            return SourceHealthStatus.ATTENTION
        return SourceHealthStatus.HEALTHY

    @staticmethod
    def _run_view(row) -> SourceRunView:
        duration = max(
            0.0,
            (row.finished_at - row.started_at).total_seconds(),
        )
        return SourceRunView(
            id=row.id,
            status=row.status,
            started_at=row.started_at,
            finished_at=row.finished_at,
            duration_seconds=duration,
            pages_processed=row.pages_processed,
            fetched=row.fetched,
            ingested=row.ingested,
            duplicates=row.duplicates,
            source_changed=row.source_changed,
            empty_content=row.empty_content,
            skipped=row.skipped,
            errors=row.errors,
            skips=row.skips,
            start_checkpoint_present=row.start_checkpoint_present,
            end_checkpoint_present=row.end_checkpoint_present,
            checkpoint_fingerprint=row.checkpoint_fingerprint,
        )
