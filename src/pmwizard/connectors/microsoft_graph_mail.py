"""Microsoft Graph Mail connector for PMWizard V0.

OAuth/token acquisition is intentionally external. This module accepts a token
provider and performs read-only Graph calls against one configured mail folder.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any, Callable, Protocol, runtime_checkable
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlencode
from urllib.request import Request, urlopen
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

from pmwizard.ingestion import SourceRecord

from .contracts import ConnectorPage, ConnectorTestResult


GRAPH_BASE_URL = "https://graph.microsoft.com/v1.0"


class GraphTransportError(RuntimeError):
    """Provider/HTTP boundary error with no secret material."""

    def __init__(self, message: str, *, status_code: int | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code


@runtime_checkable
class GraphJsonTransport(Protocol):
    def get_json(self, url: str, *, headers: dict[str, str]) -> dict[str, Any]:
        ...


class MicrosoftGraphHttpTransport:
    """Minimal stdlib HTTP transport using an externally supplied bearer token."""

    def __init__(
        self,
        token_provider: Callable[[], str],
        *,
        timeout_seconds: float = 30.0,
    ) -> None:
        if timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be positive")
        self.token_provider = token_provider
        self.timeout_seconds = timeout_seconds

    def get_json(self, url: str, *, headers: dict[str, str]) -> dict[str, Any]:
        token = self.token_provider().strip()
        if not token:
            raise GraphTransportError("Token provider returned an empty token.")

        request_headers = {
            "Authorization": f"Bearer {token}",
            "Accept": "application/json",
            **headers,
        }
        request = Request(url, headers=request_headers, method="GET")

        try:
            with urlopen(request, timeout=self.timeout_seconds) as response:
                payload = response.read()
        except HTTPError as exc:
            raise GraphTransportError(
                f"Microsoft Graph returned HTTP {exc.code}.",
                status_code=exc.code,
            ) from exc
        except URLError as exc:
            raise GraphTransportError(
                f"Microsoft Graph request failed: {exc.reason}"
            ) from exc

        try:
            parsed = json.loads(payload.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise GraphTransportError("Microsoft Graph returned invalid JSON.") from exc

        if not isinstance(parsed, dict):
            raise GraphTransportError("Microsoft Graph returned a non-object JSON payload.")
        return parsed

    def get_bytes(
        self,
        url: str,
        *,
        headers: dict[str, str],
        max_bytes: int | None = None,
    ) -> bytes:
        token = self.token_provider().strip()
        if not token:
            raise GraphTransportError("Token provider returned an empty token.")
        if max_bytes is not None and max_bytes < 1:
            raise ValueError("max_bytes must be positive when provided")

        request_headers = {
            "Authorization": f"Bearer {token}",
            **headers,
        }
        request = Request(url, headers=request_headers, method="GET")

        try:
            with urlopen(request, timeout=self.timeout_seconds) as response:
                payload = (
                    response.read(max_bytes + 1)
                    if max_bytes is not None
                    else response.read()
                )
        except HTTPError as exc:
            raise GraphTransportError(
                f"Microsoft Graph returned HTTP {exc.code}.",
                status_code=exc.code,
            ) from exc
        except URLError as exc:
            raise GraphTransportError(
                f"Microsoft Graph request failed: {exc.reason}"
            ) from exc

        if max_bytes is not None and len(payload) > max_bytes:
            raise GraphTransportError(
                f"Microsoft Graph file exceeds the {max_bytes}-byte V0 limit."
            )
        return payload


class MicrosoftGraphMailConfig(BaseModel):
    """One project-scoped Microsoft Graph mail-folder connection."""

    model_config = ConfigDict(extra="forbid")

    connection_name: str = Field(min_length=1)
    mailbox: str = Field(default="me", min_length=1)
    folder_id: str = Field(default="inbox", min_length=1)
    permission_scope: list[str] = Field(min_length=1)
    received_after: datetime | None = None

    @field_validator("connection_name", "mailbox", "folder_id")
    @classmethod
    def _strip_nonempty(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("value must not be empty")
        return value

    @field_validator("received_after")
    @classmethod
    def _require_timezone(cls, value: datetime | None) -> datetime | None:
        if value is not None and value.tzinfo is None:
            raise ValueError("received_after must be timezone-aware")
        return value


class MicrosoftGraphMailConnector:
    """Read-only incremental Outlook mail connector using folder delta queries."""

    def __init__(
        self,
        config: MicrosoftGraphMailConfig,
        transport: GraphJsonTransport,
    ) -> None:
        self.config = config
        self.transport = transport

    @property
    def connector_key(self) -> str:
        return f"microsoft-graph-mail:{self.config.connection_name}:v0"

    def test_connection(self) -> ConnectorTestResult:
        url = self._folder_url()
        query = urlencode({"$select": "id,displayName"})
        try:
            payload = self.transport.get_json(
                f"{url}?{query}",
                headers={"Accept": "application/json"},
            )
        except Exception as exc:
            return ConnectorTestResult(
                ok=False,
                message=f"{type(exc).__name__}: {exc}",
            )

        display_name = payload.get("displayName") or self.config.folder_id
        return ConnectorTestResult(
            ok=True,
            message=f"Microsoft Graph mail folder is reachable: {display_name}",
        )

    def fetch_page(
        self,
        *,
        project_id: UUID,
        cursor: str | None,
        limit: int,
    ) -> ConnectorPage:
        if type(limit) is not int or limit < 1:
            raise ValueError("limit must be a positive integer")

        url = cursor or self._initial_delta_url()
        payload = self.transport.get_json(
            url,
            headers={
                "Accept": "application/json",
                "Prefer": (
                    'outlook.body-content-type="text", '
                    f"odata.maxpagesize={limit}"
                ),
            },
        )

        values = payload.get("value")
        if not isinstance(values, list):
            raise GraphTransportError(
                "Microsoft Graph delta response is missing a list-valued 'value'."
            )

        records: list[SourceRecord] = []
        for item in values:
            if not isinstance(item, dict):
                raise GraphTransportError(
                    "Microsoft Graph delta response contains a non-object message."
                )
            if "@removed" in item:
                # Evidence is immutable in V0. Deletions/moves do not delete prior
                # Evidence and are intentionally ignored by this connector.
                continue
            records.append(self._map_message(project_id, item))

        next_link = payload.get("@odata.nextLink")
        delta_link = payload.get("@odata.deltaLink")

        if next_link is not None and not isinstance(next_link, str):
            raise GraphTransportError("@odata.nextLink must be a string.")
        if delta_link is not None and not isinstance(delta_link, str):
            raise GraphTransportError("@odata.deltaLink must be a string.")

        has_more = bool(next_link)
        next_cursor = next_link or delta_link

        if next_cursor is None:
            raise GraphTransportError(
                "Microsoft Graph delta response returned neither nextLink nor deltaLink."
            )

        return ConnectorPage(
            records=records,
            next_cursor=next_cursor,
            has_more=has_more,
        )

    def _mailbox_path(self) -> str:
        if self.config.mailbox.casefold() == "me":
            return "/me"
        return f"/users/{quote(self.config.mailbox, safe='')}"

    def _folder_url(self) -> str:
        folder = quote(self.config.folder_id, safe="")
        return f"{GRAPH_BASE_URL}{self._mailbox_path()}/mailFolders/{folder}"

    def _initial_delta_url(self) -> str:
        params: dict[str, str] = {
            "changeType": "created",
            "$select": (
                "id,subject,body,bodyPreview,from,sender,receivedDateTime,"
                "sentDateTime,lastModifiedDateTime,webLink,internetMessageId,isDraft"
            ),
        }
        if self.config.received_after is not None:
            timestamp = (
                self.config.received_after.astimezone(timezone.utc)
                .isoformat()
                .replace("+00:00", "Z")
            )
            params["$filter"] = f"receivedDateTime ge {timestamp}"

        return (
            f"{self._folder_url()}/messages/delta?"
            f"{urlencode(params)}"
        )

    def _map_message(self, project_id: UUID, item: dict[str, Any]) -> SourceRecord:
        message_id = item.get("id")
        if not isinstance(message_id, str) or not message_id.strip():
            raise GraphTransportError("Microsoft Graph message is missing a valid id.")

        timestamp = (
            item.get("receivedDateTime")
            or item.get("sentDateTime")
            or item.get("lastModifiedDateTime")
        )
        if not isinstance(timestamp, str):
            raise GraphTransportError(
                f"Microsoft Graph message {message_id} is missing a usable timestamp."
            )

        captured_at = _parse_graph_datetime(timestamp)

        subject = item.get("subject")
        subject_text = subject.strip() if isinstance(subject, str) else ""

        body_text = _message_body_text(item)
        content = _compose_message_content(subject_text, body_text)

        author = _message_author(item)
        web_link = item.get("webLink")
        source_reference = web_link if isinstance(web_link, str) else None

        return SourceRecord(
            project_id=project_id,
            source_type="email",
            source_system="microsoft_graph_mail",
            external_id=message_id,
            source_reference=source_reference,
            author=author,
            captured_at=captured_at,
            effective_at=captured_at,
            content=content,
            permission_scope=self.config.permission_scope,
        )


def _parse_graph_datetime(value: str) -> datetime:
    normalized = value.replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError as exc:
        raise GraphTransportError(
            f"Microsoft Graph returned an invalid datetime: {value}"
        ) from exc
    if parsed.tzinfo is None:
        raise GraphTransportError(
            f"Microsoft Graph returned a timezone-naive datetime: {value}"
        )
    return parsed


def _compose_message_content(subject: str, body: str) -> str:
    """Combine subject/body while removing only an exact leading duplication."""
    if not subject:
        return body.strip()
    if not body:
        return subject.strip()

    subject = subject.strip()
    body = body.strip()

    if body.casefold().startswith(subject.casefold()):
        remainder = body[len(subject) :].lstrip(" :-\n\t")
        if remainder:
            return f"{subject}\n\n{remainder}"
        return subject

    return f"{subject}\n\n{body}"


def _message_body_text(item: dict[str, Any]) -> str:
    body = item.get("body")
    if isinstance(body, dict):
        content = body.get("content")
        content_type = body.get("contentType")
        if (
            isinstance(content, str)
            and isinstance(content_type, str)
            and content_type.casefold() == "text"
        ):
            return content.strip()

    preview = item.get("bodyPreview")
    return preview.strip() if isinstance(preview, str) else ""


def _message_author(item: dict[str, Any]) -> str | None:
    for field in ("from", "sender"):
        envelope = item.get(field)
        if not isinstance(envelope, dict):
            continue
        email_address = envelope.get("emailAddress")
        if not isinstance(email_address, dict):
            continue

        address = email_address.get("address")
        if isinstance(address, str) and address.strip():
            return address.strip()

        name = email_address.get("name")
        if isinstance(name, str) and name.strip():
            return name.strip()
    return None
