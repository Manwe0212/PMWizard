"""Source Connection Administration V0 application service."""

from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID, uuid4

from pydantic import ValidationError
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from pmwizard.connectors import (
    ConnectorDescriptor,
    MicrosoftGraphMailConfig,
    MicrosoftGraphSharePointConfig,
)
from pmwizard.persistence.orm import AutomationScheduleORM

from .repository import SourceRepository
from .schemas import (
    CreateSourceConnectionRequest,
    SourceConnectionTestResponse,
    SourceConnectionTestStatus,
    SourceConnectionView,
    UpdateSourceConnectionRequest,
)
from .service import SourcesWorkspaceService


_SUPPORTED = {
    "microsoft_graph_mail",
    "microsoft_graph_sharepoint",
}


class SourceConnectionAdminService:
    def __init__(self, session: Session) -> None:
        self.session = session
        self.repository = SourceRepository(session)

    def create(
        self,
        *,
        tenant_id: UUID,
        project_id: UUID,
        command: CreateSourceConnectionRequest,
    ) -> SourceConnectionView:
        source_id = uuid4()
        descriptor = self._descriptor(
            source_system=command.source_system,
            display_name=command.display_name,
            safe_config=command.safe_config,
            permission_scope=command.permission_scope,
        )
        prefix = (
            "microsoft-graph-mail"
            if command.source_system == "microsoft_graph_mail"
            else "microsoft-graph-sharepoint"
        )
        connector_key = f"{prefix}:admin:{source_id}:v0"

        self.repository.create_admin_connection(
            tenant_id=tenant_id,
            project_id=project_id,
            source_connection_id=source_id,
            connector_key=connector_key,
            descriptor=descriptor,
            enabled=command.enabled,
        )
        self.session.commit()
        return self._view(tenant_id, project_id, source_id)

    def update(
        self,
        *,
        tenant_id: UUID,
        project_id: UUID,
        source_connection_id: UUID,
        command: UpdateSourceConnectionRequest,
    ) -> SourceConnectionView:
        row = self.repository.get_connection_by_id(
            tenant_id=tenant_id,
            project_id=project_id,
            source_connection_id=source_connection_id,
        )
        if row is None:
            raise LookupError("Source connection not found")
        if row.source_system not in _SUPPORTED:
            raise ValueError(
                "This Source system is not administrable in V0."
            )

        display_name = command.display_name or row.display_name
        safe_config = (
            command.safe_config
            if command.safe_config is not None
            else row.safe_config
        )
        permission_scope = (
            command.permission_scope
            if command.permission_scope is not None
            else row.permission_scope
        )
        descriptor = self._descriptor(
            source_system=row.source_system,
            display_name=display_name,
            safe_config=safe_config,
            permission_scope=permission_scope,
        )

        config_changed = (
            command.safe_config is not None
            and descriptor.safe_config != row.safe_config
        )

        updated = self.repository.update_admin_connection(
            tenant_id=tenant_id,
            project_id=project_id,
            source_connection_id=source_connection_id,
            display_name=descriptor.display_name,
            safe_config=descriptor.safe_config,
            enabled=command.enabled,
        )
        updated.permission_scope = descriptor.permission_scope

        if config_changed:
            self.repository.clear_checkpoint(
                tenant_id=tenant_id,
                project_id=project_id,
                connector_key=row.connector_key,
            )

        if command.enabled is False:
            self._pause_source_sync_schedules(
                tenant_id=tenant_id,
                project_id=project_id,
                source_connection_id=source_connection_id,
            )

        self.session.commit()
        return self._view(tenant_id, project_id, source_connection_id)

    def queue_test(
        self,
        *,
        tenant_id: UUID,
        project_id: UUID,
        source_connection_id: UUID,
        requested_by: UUID,
        now: datetime | None = None,
    ) -> SourceConnectionTestResponse:
        timestamp = self._aware(now or datetime.now(timezone.utc))
        row = self.repository.get_connection_by_id(
            tenant_id=tenant_id,
            project_id=project_id,
            source_connection_id=source_connection_id,
        )
        if row is None:
            raise LookupError("Source connection not found")
        if row.source_system not in _SUPPORTED:
            raise ValueError(
                "Connection testing is not supported for this Source system."
            )
        if not row.is_enabled:
            raise ValueError(
                "Enable the Source connection before testing it."
            )
        if not row.credential_ref:
            raise ValueError(
                "Bind a runtime credential before testing the Source."
            )

        self.repository.queue_connection_test(
            tenant_id=tenant_id,
            project_id=project_id,
            source_connection_id=source_connection_id,
            requested_by=requested_by,
            now=timestamp,
        )
        self.session.commit()
        return SourceConnectionTestResponse(
            source_connection_id=source_connection_id,
            status=SourceConnectionTestStatus.QUEUED,
            requested_at=timestamp,
        )

    def _view(
        self,
        tenant_id: UUID,
        project_id: UUID,
        source_connection_id: UUID,
    ) -> SourceConnectionView:
        snapshot = SourcesWorkspaceService(self.session).snapshot(
            tenant_id=tenant_id,
            project_id=project_id,
        )
        for item in snapshot.sources:
            if item.id == source_connection_id:
                return item
        raise LookupError("Source connection not found")

    def _pause_source_sync_schedules(
        self,
        *,
        tenant_id: UUID,
        project_id: UUID,
        source_connection_id: UUID,
    ) -> None:
        schedules = list(
            self.session.scalars(
                select(AutomationScheduleORM).where(
                    AutomationScheduleORM.tenant_id == tenant_id,
                    AutomationScheduleORM.project_id == project_id,
                    AutomationScheduleORM.task_type == "source_sync",
                    AutomationScheduleORM.is_enabled.is_(True),
                )
            ).all()
        )
        source_id = str(source_connection_id)
        for schedule in schedules:
            if schedule.config.get("source_connection_id") == source_id:
                schedule.is_enabled = False

    @staticmethod
    def _descriptor(
        *,
        source_system: str,
        display_name: str,
        safe_config: dict,
        permission_scope: list[str],
    ) -> ConnectorDescriptor:
        try:
            if source_system == "microsoft_graph_mail":
                config = MicrosoftGraphMailConfig(
                    connection_name=display_name,
                    permission_scope=permission_scope,
                    **safe_config,
                )
                return ConnectorDescriptor(
                    source_type="email",
                    source_system=source_system,
                    display_name=config.connection_name,
                    permission_scope=config.permission_scope,
                    safe_config={
                        "mailbox": config.mailbox,
                        "folder_id": config.folder_id,
                        "received_after": (
                            config.received_after.isoformat()
                            if config.received_after is not None
                            else None
                        ),
                    },
                )

            if source_system == "microsoft_graph_sharepoint":
                config = MicrosoftGraphSharePointConfig(
                    connection_name=display_name,
                    permission_scope=permission_scope,
                    **safe_config,
                )
                return ConnectorDescriptor(
                    source_type="document",
                    source_system=source_system,
                    display_name=config.connection_name,
                    permission_scope=config.permission_scope,
                    safe_config={
                        "drive_id": config.drive_id,
                        "initial_sync_mode": config.initial_sync_mode,
                        "supported_extensions": config.supported_extensions,
                        "max_file_bytes": config.max_file_bytes,
                    },
                )
        except (ValidationError, TypeError, ValueError) as exc:
            raise ValueError(
                f"Invalid safe configuration for {source_system}: {exc}"
            ) from exc

        raise ValueError(
            f"Source system {source_system!r} is not supported by V0 administration."
        )

    @staticmethod
    def _aware(value: datetime) -> datetime:
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value
