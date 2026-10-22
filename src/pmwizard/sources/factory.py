"""Composition helpers for durable connector execution."""

from sqlalchemy.orm import Session

from pmwizard.connectors import ConnectorRunner, SQLAlchemyCheckpointStore

from .service import SourceTelemetryService


def create_durable_connector_runner(session: Session) -> ConnectorRunner:
    """Create the production-oriented V0 connector runner composition."""
    return ConnectorRunner(
        session,
        SQLAlchemyCheckpointStore(session),
        telemetry=SourceTelemetryService(session),
    )
