"""Runtime secret resolution without persisting secret material."""

from __future__ import annotations

import json
import os
import re
from typing import Protocol

from pydantic import BaseModel, ConfigDict, Field, TypeAdapter
from typing_extensions import Annotated, Literal


_ENV_REF = re.compile(r"^env:([A-Z0-9_]{1,64})$")


class SecretResolutionError(RuntimeError):
    """Raised when a runtime secret cannot be resolved safely."""


class SecretProvider(Protocol):
    def resolve(self, reference: str) -> str: ...


class EnvironmentSecretProvider:
    """Resolve only PMWIZARD_SECRET_* variables from env:ALIAS references."""

    def resolve(self, reference: str) -> str:
        match = _ENV_REF.fullmatch(reference.strip())
        if match is None:
            raise SecretResolutionError(
                "Environment secret references must use env:ALIAS with "
                "uppercase letters, digits, or underscores."
            )

        variable = f"PMWIZARD_SECRET_{match.group(1)}"
        value = os.getenv(variable)
        if value is None or not value.strip():
            raise SecretResolutionError(
                "Referenced runtime secret is not configured."
            )
        return value


class BearerTokenCredential(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: Literal["bearer_token"]
    access_token: str = Field(min_length=1)


class EntraClientCredentials(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: Literal["entra_client_credentials"]
    tenant_id: str = Field(min_length=1)
    client_id: str = Field(min_length=1)
    client_secret: str = Field(min_length=1)
    scope: str = Field(
        default="https://graph.microsoft.com/.default",
        min_length=1,
    )


MicrosoftGraphCredential = Annotated[
    BearerTokenCredential | EntraClientCredentials,
    Field(discriminator="kind"),
]
_GRAPH_CREDENTIAL = TypeAdapter(MicrosoftGraphCredential)


def parse_graph_credential(raw: str) -> MicrosoftGraphCredential:
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise SecretResolutionError(
            "Microsoft Graph credential secret must be JSON."
        ) from exc

    try:
        return _GRAPH_CREDENTIAL.validate_python(payload)
    except Exception as exc:
        raise SecretResolutionError(
            "Microsoft Graph credential secret has an invalid schema."
        ) from exc
