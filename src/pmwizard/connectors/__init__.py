"""PMWizard source connector framework."""

from .checkpoints import CheckpointStore, InMemoryCheckpointStore
from .contracts import (
    ConnectorError,
    ConnectorPage,
    ConnectorRunResult,
    ConnectorRunStatus,
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
from .runner import ConnectorRunner
from .synthetic import SyntheticConnector

__all__ = [
    "CheckpointStore",
    "ConnectorError",
    "ConnectorPage",
    "ConnectorRunResult",
    "ConnectorRunStatus",
    "ConnectorRunner",
    "ConnectorTestResult",
    "GraphJsonTransport",
    "GraphTransportError",
    "InMemoryCheckpointStore",
    "MicrosoftGraphHttpTransport",
    "MicrosoftGraphMailConfig",
    "MicrosoftGraphMailConnector",
    "SourceConnector",
    "SyntheticConnector",
]
