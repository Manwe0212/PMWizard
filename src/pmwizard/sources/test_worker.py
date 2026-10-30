"""Worker-owned Source connection tests with expiring leases."""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy.orm import Session, sessionmaker

from pmwizard.security import SecretProvider

from .repository import SourceRepository
from .runtime import SourceRuntimeResolver


class SourceConnectionTestWorker:
    def __init__(
        self,
        session_factory: sessionmaker,
        *,
        worker_id: str,
        secret_provider: SecretProvider,
        lease_seconds: int = 120,
        batch_size: int = 10,
        graph_transport_factory=None,
    ) -> None:
        self.session_factory = session_factory
        self.worker_id = worker_id
        self.secret_provider = secret_provider
        self.lease_seconds = lease_seconds
        self.batch_size = batch_size
        self.graph_transport_factory = graph_transport_factory

    def run_once(
        self,
        *,
        now: datetime | None = None,
    ) -> int:
        timestamp = now or datetime.now(timezone.utc)
        with self.session_factory() as session:
            claims = SourceRepository(session).claim_pending_tests(
                worker_id=self.worker_id,
                now=timestamp,
                lease_seconds=self.lease_seconds,
                limit=self.batch_size,
            )

        completed = 0
        for claim in claims:
            with self.session_factory() as session:
                repository = SourceRepository(session)
                status = "failed"
                message = "Source connection test failed."
                try:
                    connector = SourceRuntimeResolver(
                        session,
                        self.secret_provider,
                        graph_transport_factory=self.graph_transport_factory,
                    ).resolve(
                        tenant_id=claim.tenant_id,
                        project_id=claim.project_id,
                        source_connection_id=claim.source_connection_id,
                    )
                    result = connector.test_connection()
                    status = "success" if result.ok else "failed"
                    message = self._sanitize(result.message)
                except Exception as exc:
                    message = self._sanitize(
                        f"{type(exc).__name__}: {exc}"
                    )

                repository.finish_connection_test(
                    claim=claim,
                    now=datetime.now(timezone.utc),
                    status=status,
                    message=message,
                )
                completed += 1
        return completed

    @staticmethod
    def _sanitize(message: str) -> str:
        return " ".join(message.split())[:1000]
