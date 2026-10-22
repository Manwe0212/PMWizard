"""PMWizard source connector framework."""

from .checkpoints import CheckpointStore, InMemoryCheckpointStore
from .contracts import (
    ConnectorError,
    ConnectorPage,
    ConnectorRunResult,
    ConnectorRunStatus,
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
    "ConnectorError",
    "ConnectorPage",
    "ConnectorRunResult",
    "ConnectorRunStatus",
    "ConnectorRunner",
    "ConnectorSkip",
    "ConnectorTestResult",
    "GraphDocumentTransport",
    "GraphJsonTransport",
    "GraphTransportError",
    "InMemoryCheckpointStore",
    "MicrosoftGraphHttpTransport",
    "MicrosoftGraphMailConfig",
    "MicrosoftGraphMailConnector",
    "MicrosoftGraphSharePointConfig",
    "MicrosoftGraphSharePointConnector",
    "SourceConnector",
    "SyntheticConnector",
]
