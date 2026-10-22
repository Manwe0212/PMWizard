"""PMWizard source connector framework."""

from .checkpoints import (
    CheckpointStore,
    InMemoryCheckpointStore,
    SQLAlchemyCheckpointStore,
)
from .contracts import (
    ConnectorDescriptor,
    ConnectorError,
    ConnectorPage,
    ConnectorRunResult,
    ConnectorRunStatus,
    ConnectorRunTelemetry,
    ConnectorSkip,
    ConnectorTestResult,
    SourceConnector,
)
from .microsoft_graph_mail import (
    GraphJsonTransport,
    GraphTransportError,
    MicrosoftGraphHttpTransport,
    MicrosoftGraphMailConfig,
    MicrosoftGraphMailConnector,
)
from .microsoft_graph_sharepoint import (
    GraphDocumentTransport,
    MicrosoftGraphSharePointConfig,
    MicrosoftGraphSharePointConnector,
)
from .runner import ConnectorRunner
from .synthetic import SyntheticConnector

__all__ = [
    "CheckpointStore",
    "ConnectorDescriptor",
    "ConnectorError",
    "ConnectorPage",
    "ConnectorRunResult",
    "ConnectorRunStatus",
    "ConnectorRunTelemetry",
    "ConnectorRunner",
    "ConnectorSkip",
    "ConnectorTestResult",
    "GraphDocumentTransport",
    "GraphJsonTransport",
    "GraphTransportError",
    "InMemoryCheckpointStore",
    "SQLAlchemyCheckpointStore",
    "MicrosoftGraphHttpTransport",
    "MicrosoftGraphMailConfig",
    "MicrosoftGraphMailConnector",
    "MicrosoftGraphSharePointConfig",
    "MicrosoftGraphSharePointConnector",
    "SourceConnector",
    "SyntheticConnector",
]
