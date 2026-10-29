"""Security boundaries and runtime secret resolution."""

from .microsoft_identity import MicrosoftEntraClientCredentialsTokenProvider
from .secrets import (
    BearerTokenCredential,
    EntraClientCredentials,
    EnvironmentSecretProvider,
    MicrosoftGraphCredential,
    SecretProvider,
    SecretResolutionError,
    parse_graph_credential,
)

__all__ = [
    "BearerTokenCredential",
    "EntraClientCredentials",
    "EnvironmentSecretProvider",
    "MicrosoftEntraClientCredentialsTokenProvider",
    "MicrosoftGraphCredential",
    "SecretProvider",
    "SecretResolutionError",
    "parse_graph_credential",
]
