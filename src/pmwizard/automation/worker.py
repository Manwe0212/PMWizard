"""Lightweight polling worker for Automation & Scheduler V0."""

from __future__ import annotations

import argparse
import os
import socket
import time
from datetime import datetime, timezone
from uuid import uuid4

from sqlalchemy.orm import sessionmaker

from pmwizard.persistence import create_engine_from_url, create_session_factory
from pmwizard.security import EnvironmentSecretProvider, SecretProvider
from pmwizard.sources.test_worker import SourceConnectionTestWorker

from .executor import AutomationExecutor
from .handlers import (
    HealthSnapshotAutomationHandler,
    SourceSyncAutomationHandler,
)
from .repository import AutomationRepository


class AutomationWorker:
    def __init__(
        self,
        session_factory: sessionmaker,
        *,
        worker_id: str,
        lease_seconds: int = 300,
        batch_size: int = 10,
        secret_provider: SecretProvider | None = None,
        graph_transport_factory=None,
    ) -> None:
        if lease_seconds < 30:
            raise ValueError("lease_seconds must be at least 30")
        if batch_size < 1 or batch_size > 100:
            raise ValueError("batch_size must be between 1 and 100")

        self.session_factory = session_factory
        self.worker_id = worker_id
        self.lease_seconds = lease_seconds
        self.batch_size = batch_size
        self.secret_provider = secret_provider
        self.graph_transport_factory = graph_transport_factory

    def run_once(
        self,
        *,
        now: datetime | None = None,
    ) -> list:
        timestamp = now or datetime.now(timezone.utc)
        if self.secret_provider is not None:
            SourceConnectionTestWorker(
                self.session_factory,
                worker_id=self.worker_id,
                secret_provider=self.secret_provider,
                lease_seconds=min(self.lease_seconds, 120),
                batch_size=self.batch_size,
                graph_transport_factory=self.graph_transport_factory,
            ).run_once(now=timestamp)

        with self.session_factory() as session:
            claims = AutomationRepository(session).claim_due(
                worker_id=self.worker_id,
                now=timestamp,
                lease_seconds=self.lease_seconds,
                limit=self.batch_size,
            )

        results = []
        for claim in claims:
            with self.session_factory() as session:
                handlers = [HealthSnapshotAutomationHandler()]
                if self.secret_provider is not None:
                    handlers.append(
                        SourceSyncAutomationHandler(
                            self.secret_provider,
                            graph_transport_factory=self.graph_transport_factory,
                        )
                    )
                result = AutomationExecutor(
                    session,
                    handlers=handlers,
                ).execute(
                    claim=claim,
                    worker_id=self.worker_id,
                )
                results.append(result)
        return results


def _worker_id() -> str:
    configured = os.getenv("PMWIZARD_AUTOMATION_WORKER_ID", "").strip()
    if configured:
        return configured
    return f"{socket.gethostname()}:{os.getpid()}:{uuid4().hex[:8]}"


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Run the PMWizard Automation Scheduler worker."
    )
    parser.add_argument(
        "--once",
        action="store_true",
        help="Process one due batch and exit.",
    )
    args = parser.parse_args()

    database_url = os.getenv("PMWIZARD_DATABASE_URL", "").strip()
    if not database_url:
        raise RuntimeError(
            "PMWIZARD_DATABASE_URL is required for the automation worker."
        )

    poll_seconds = int(
        os.getenv("PMWIZARD_AUTOMATION_POLL_SECONDS", "15")
    )
    lease_seconds = int(
        os.getenv("PMWIZARD_AUTOMATION_LEASE_SECONDS", "300")
    )
    batch_size = int(
        os.getenv("PMWIZARD_AUTOMATION_BATCH_SIZE", "10")
    )
    if poll_seconds < 1:
        raise RuntimeError(
            "PMWIZARD_AUTOMATION_POLL_SECONDS must be positive."
        )

    engine = create_engine_from_url(database_url)
    worker = AutomationWorker(
        create_session_factory(engine),
        worker_id=_worker_id(),
        lease_seconds=lease_seconds,
        batch_size=batch_size,
        secret_provider=EnvironmentSecretProvider(),
    )

    if args.once:
        worker.run_once()
        return

    while True:
        worker.run_once()
        time.sleep(poll_seconds)


if __name__ == "__main__":
    main()
