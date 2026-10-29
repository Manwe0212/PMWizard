"""Secure reconstruction of Source connectors at worker runtime."""

from __future__ import annotations

from datetime import datetime
from typing import Callable
from uuid import UUID

from sqlalchemy.orm import Session

from pmwizard.connectors import (
    MicrosoftGraphHttpTransport,
    MicrosoftGraphMailConfig,
    MicrosoftGraphMailConnector,
    MicrosoftGraphSharePointConfig,
    MicrosoftGraphSharePointConnector,
    SourceConnector,
)
from pmwizard.security import (
    BearerTokenCredential,
    EntraClientCredentials,
    MicrosoftEntraClientCredentialsTokenProvider,
    SecretProvider,
    SecretResolutionError,
    parse_graph_credential,
)

from .repository import SourceRepository


GraphTransportFactory = Callable[[Callable[[], str]], object]


class SourceRuntimeError(RuntimeError):
    """Raised when a persisted Source cannot be reconstructed safely."""


class SourceRuntimeResolver:
    def __init__(
        self,
        session: Session,
        secret_provider: SecretProvider,
        *,
        graph_transport_factory: GraphTransportFactory | None = None,
    ) -> None:
        self.session = session
        self.repository = SourceRepository(session)
        self.secret_provider = secret_provider
        self.graph_transport_factory = (
            graph_transport_factory
            or (lambda token_provider: MicrosoftGraphHttpTransport(token_provider))
        )

    def resolve(
        self,
        *,
        tenant_id: UUID,
        project_id: UUID,
        source_connection_id: UUID,
    ) -> SourceConnector:
        row = self.repository.get_connection_by_id(
            tenant_id=tenant_id,
            project_id=project_id,
            source_connection_id=source_connection_id,
        )
        if row is None:
            raise SourceRuntimeError("Source connection not found.")
        if not row.is_enabled:
            raise SourceRuntimeError("Source connection is disabled.")
        if not row.credential_ref:
            raise SourceRuntimeError(
                "Source connection has no runtime credential reference."
            )

        try:
            raw = self.secret_provider.resolve(row.credential_ref)
            credential = parse_graph_credential(raw)
        except SecretResolutionError as exc:
            raise SourceRuntimeError(str(exc)) from exc

        if isinstance(credential, BearerTokenCredential):
            token = credential.access_token

            def token_provider() -> str:
                return token
        elif isinstance(credential, EntraClientCredentials):
            token_provider = MicrosoftEntraClientCredentialsTokenProvider(
                credential
            )
        else:  # defensive boundary for future credential variants
            raise SourceRuntimeError(
                "Unsupported Microsoft Graph credential type."
            )

        transport = self.graph_transport_factory(token_provider)

        if row.source_system == "microsoft_graph_mail":
            return MicrosoftGraphMailConnector(
                MicrosoftGraphMailConfig(
                    connection_name=row.display_name,
                    mailbox=self._required_string(
                        row.safe_config,
                        "mailbox",
                        default="me",
                    ),
                    folder_id=self._required_string(
                        row.safe_config,
                        "folder_id",
                        default="inbox",
                    ),
                    permission_scope=list(row.permission_scope),
                    received_after=self._optional_datetime(
                        row.safe_config.get("received_after")
                    ),
                ),
                transport,
            )

        if row.source_system == "microsoft_graph_sharepoint":
            return MicrosoftGraphSharePointConnector(
                MicrosoftGraphSharePointConfig(
                    connection_name=row.display_name,
                    drive_id=self._required_string(
                        row.safe_config,
                        "drive_id",
                    ),
                    permission_scope=list(row.permission_scope),
                    initial_sync_mode=str(
                        row.safe_config.get("initial_sync_mode", "latest")
                    ),
                    supported_extensions=list(
                        row.safe_config.get(
                            "supported_extensions",
                            [
                                ".csv",
                                ".docx",
                                ".json",
                                ".log",
                                ".md",
                                ".txt",
                                ".xml",
                                ".yaml",
                                ".yml",
                            ],
                        )
                    ),
                    max_file_bytes=int(
                        row.safe_config.get(
                            "max_file_bytes",
                            10 * 1024 * 1024,
                        )
                    ),
                ),
                transport,
            )

        raise SourceRuntimeError(
            f"Scheduled runtime is not supported for {row.source_system}."
        )

    @staticmethod
    def _required_string(
        config: dict,
        key: str,
        *,
        default: str | None = None,
    ) -> str:
        value = config.get(key, default)
        if not isinstance(value, str) or not value.strip():
            raise SourceRuntimeError(
                f"Source safe_config is missing {key!r}."
            )
        return value.strip()

    @staticmethod
    def _optional_datetime(value) -> datetime | None:
        if value is None:
            return None
        if not isinstance(value, str):
            raise SourceRuntimeError(
                "Source received_after must be an ISO datetime string."
            )
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError as exc:
            raise SourceRuntimeError(
                "Source received_after is not a valid ISO datetime."
            ) from exc
        if parsed.tzinfo is None:
            raise SourceRuntimeError(
                "Source received_after must be timezone-aware."
            )
        return parsed
