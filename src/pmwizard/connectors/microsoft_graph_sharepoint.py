"""Microsoft Graph SharePoint document-library connector for PMWizard V0."""

from __future__ import annotations

import io
import zipfile
from datetime import datetime
from pathlib import PurePosixPath
from typing import Any, Literal, Protocol, runtime_checkable
from urllib.parse import quote, urlencode
import xml.etree.ElementTree as ET
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

from pmwizard.ingestion import SourceRecord

from .contracts import ConnectorPage, ConnectorSkip, ConnectorTestResult
from .microsoft_graph_mail import GRAPH_BASE_URL, GraphTransportError


_TEXT_EXTENSIONS = {
    ".txt",
    ".md",
    ".csv",
    ".json",
    ".xml",
    ".yaml",
    ".yml",
    ".log",
}
_DEFAULT_EXTENSIONS = sorted(_TEXT_EXTENSIONS | {".docx"})


@runtime_checkable
class GraphDocumentTransport(Protocol):
    def get_json(self, url: str, *, headers: dict[str, str]) -> dict[str, Any]:
        ...

    def get_bytes(
        self,
        url: str,
        *,
        headers: dict[str, str],
        max_bytes: int | None = None,
    ) -> bytes:
        ...


class MicrosoftGraphSharePointConfig(BaseModel):
    """One project-scoped SharePoint document-library connection."""

    model_config = ConfigDict(extra="forbid")

    connection_name: str = Field(min_length=1)
    drive_id: str = Field(min_length=1)
    permission_scope: list[str] = Field(min_length=1)
    initial_sync_mode: Literal["full", "latest"] = "latest"
    supported_extensions: list[str] = Field(
        default_factory=lambda: list(_DEFAULT_EXTENSIONS)
    )
    max_file_bytes: int = Field(default=10 * 1024 * 1024, ge=1)

    @field_validator("connection_name", "drive_id")
    @classmethod
    def _strip_nonempty(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("value must not be empty")
        return value

    @field_validator("supported_extensions")
    @classmethod
    def _normalize_extensions(cls, values: list[str]) -> list[str]:
        normalized: list[str] = []
        for value in values:
            value = value.strip().lower()
            if not value:
                raise ValueError("supported_extensions must not contain empty values")
            if not value.startswith("."):
                value = f".{value}"
            normalized.append(value)
        return sorted(set(normalized))


class MicrosoftGraphSharePointConnector:
    """Read-only incremental document-library sync using driveItem delta."""

    def __init__(
        self,
        config: MicrosoftGraphSharePointConfig,
        transport: GraphDocumentTransport,
    ) -> None:
        self.config = config
        self.transport = transport

    @property
    def connector_key(self) -> str:
        return f"microsoft-graph-sharepoint:{self.config.connection_name}:v0"

    def test_connection(self) -> ConnectorTestResult:
        drive_id = quote(self.config.drive_id, safe="")
        query = urlencode({"$select": "id,name,webUrl"})
        try:
            payload = self.transport.get_json(
                f"{GRAPH_BASE_URL}/drives/{drive_id}?{query}",
                headers={"Accept": "application/json"},
            )
        except Exception as exc:
            return ConnectorTestResult(
                ok=False,
                message=f"{type(exc).__name__}: {exc}",
            )

        name = payload.get("name") or self.config.drive_id
        return ConnectorTestResult(
            ok=True,
            message=f"Microsoft Graph document library is reachable: {name}",
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

        url = cursor or self._initial_delta_url(limit)
        payload = self.transport.get_json(
            url,
            headers={
                "Accept": "application/json",
                "deltaExcludeParent": "true",
            },
        )

        values = payload.get("value")
        if not isinstance(values, list):
            raise GraphTransportError(
                "Microsoft Graph delta response is missing a list-valued 'value'."
            )

        # Graph documents that the same item may occur more than once in a delta
        # feed. V0 keeps the last occurrence seen in this page.
        latest_by_id: dict[str, dict[str, Any]] = {}
        for item in values:
            if not isinstance(item, dict):
                raise GraphTransportError(
                    "Microsoft Graph delta response contains a non-object driveItem."
                )
            item_id = item.get("id")
            if not isinstance(item_id, str) or not item_id.strip():
                raise GraphTransportError(
                    "Microsoft Graph driveItem is missing a valid id."
                )
            latest_by_id[item_id] = item

        records: list[SourceRecord] = []
        skips: list[ConnectorSkip] = []

        for item_id, item in latest_by_id.items():
            if "deleted" in item:
                skips.append(
                    ConnectorSkip(
                        external_id=item_id,
                        reason="Drive item is deleted; historical Evidence is preserved.",
                    )
                )
                continue

            if "folder" in item or not isinstance(item.get("file"), dict):
                skips.append(
                    ConnectorSkip(
                        external_id=item_id,
                        reason="Drive item is not a downloadable file.",
                    )
                )
                continue

            record, skip = self._map_file(project_id, item)
            if record is not None:
                records.append(record)
            if skip is not None:
                skips.append(skip)

        next_link = payload.get("@odata.nextLink")
        delta_link = payload.get("@odata.deltaLink")

        if next_link is not None and not isinstance(next_link, str):
            raise GraphTransportError("@odata.nextLink must be a string.")
        if delta_link is not None and not isinstance(delta_link, str):
            raise GraphTransportError("@odata.deltaLink must be a string.")

        next_cursor = next_link or delta_link
        if next_cursor is None:
            raise GraphTransportError(
                "Microsoft Graph delta response returned neither nextLink nor deltaLink."
            )

        return ConnectorPage(
            records=records,
            skips=skips,
            next_cursor=next_cursor,
            has_more=bool(next_link),
        )

    def _initial_delta_url(self, limit: int) -> str:
        drive_id = quote(self.config.drive_id, safe="")
        params = {
            "$select": (
                "id,name,file,folder,deleted,lastModifiedDateTime,"
                "createdDateTime,webUrl,eTag,size,lastModifiedBy,parentReference"
            ),
            "$top": str(limit),
        }
        if self.config.initial_sync_mode == "latest":
            params["token"] = "latest"
        return (
            f"{GRAPH_BASE_URL}/drives/{drive_id}/root/delta?"
            f"{urlencode(params)}"
        )

    def _map_file(
        self,
        project_id: UUID,
        item: dict[str, Any],
    ) -> tuple[SourceRecord | None, ConnectorSkip | None]:
        item_id = str(item["id"])
        name = item.get("name")
        if not isinstance(name, str) or not name.strip():
            return None, ConnectorSkip(
                external_id=item_id,
                reason="Drive item is missing a usable file name.",
            )
        name = name.strip()

        extension = PurePosixPath(name).suffix.lower()
        if extension not in set(self.config.supported_extensions):
            return None, ConnectorSkip(
                external_id=item_id,
                reason=f"Unsupported document extension: {extension or '<none>'}.",
            )

        size = item.get("size")
        if isinstance(size, int) and size > self.config.max_file_bytes:
            return None, ConnectorSkip(
                external_id=item_id,
                reason=(
                    f"File exceeds V0 size limit of {self.config.max_file_bytes} bytes."
                ),
            )

        modified = item.get("lastModifiedDateTime") or item.get("createdDateTime")
        if not isinstance(modified, str):
            return None, ConnectorSkip(
                external_id=item_id,
                reason="Drive item is missing a usable source timestamp.",
            )
        captured_at = _parse_graph_datetime(modified)

        try:
            raw = self.transport.get_bytes(
                self._content_url(item_id),
                headers={"Accept": "*/*"},
                max_bytes=self.config.max_file_bytes,
            )
            extracted = _extract_document_text(name, raw)
        except Exception as exc:
            return None, ConnectorSkip(
                external_id=item_id,
                reason=f"Document extraction failed: {type(exc).__name__}: {exc}",
            )

        extracted = extracted.strip()
        if not extracted:
            return None, ConnectorSkip(
                external_id=item_id,
                reason="Document contains no extractable V0 text.",
            )

        content = _compose_document_content(name, extracted)

        etag = item.get("eTag")
        version = (
            etag.strip()
            if isinstance(etag, str) and etag.strip()
            else captured_at.isoformat()
        )
        external_id = f"{item_id}:{version}"

        web_url = item.get("webUrl")
        source_reference = web_url if isinstance(web_url, str) else None

        return (
            SourceRecord(
                project_id=project_id,
                source_type="document",
                source_system="microsoft_graph_sharepoint",
                external_id=external_id,
                source_reference=source_reference,
                author=_drive_item_author(item),
                captured_at=captured_at,
                effective_at=captured_at,
                content=content,
                permission_scope=self.config.permission_scope,
            ),
            None,
        )

    def _content_url(self, item_id: str) -> str:
        drive_id = quote(self.config.drive_id, safe="")
        encoded_item = quote(item_id, safe="")
        return (
            f"{GRAPH_BASE_URL}/drives/{drive_id}/items/{encoded_item}/content"
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


def _drive_item_author(item: dict[str, Any]) -> str | None:
    modified_by = item.get("lastModifiedBy")
    if not isinstance(modified_by, dict):
        return None
    user = modified_by.get("user")
    if not isinstance(user, dict):
        return None

    email = user.get("email")
    if isinstance(email, str) and email.strip():
        return email.strip()

    display_name = user.get("displayName")
    if isinstance(display_name, str) and display_name.strip():
        return display_name.strip()
    return None


def _compose_document_content(name: str, text: str) -> str:
    name = name.strip()
    text = text.strip()
    if text.casefold().startswith(name.casefold()):
        remainder = text[len(name) :].lstrip(" :-\n\t")
        return f"{name}\n\n{remainder}".strip() if remainder else name
    return f"{name}\n\n{text}".strip()


def _extract_document_text(name: str, raw: bytes) -> str:
    extension = PurePosixPath(name).suffix.lower()
    if extension in _TEXT_EXTENSIONS:
        try:
            return raw.decode("utf-8-sig")
        except UnicodeDecodeError as exc:
            raise GraphTransportError(
                f"{extension} document is not valid UTF-8 text."
            ) from exc

    if extension == ".docx":
        return _extract_docx_text(raw)

    raise GraphTransportError(f"No V0 extractor exists for {extension}.")


def _extract_docx_text(raw: bytes) -> str:
    try:
        with zipfile.ZipFile(io.BytesIO(raw)) as archive:
            xml = archive.read("word/document.xml")
    except (zipfile.BadZipFile, KeyError) as exc:
        raise GraphTransportError("Invalid DOCX document.") from exc

    try:
        root = ET.fromstring(xml)
    except ET.ParseError as exc:
        raise GraphTransportError("DOCX document.xml is invalid XML.") from exc

    namespace = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
    paragraph_tag = f"{{{namespace}}}p"
    text_tag = f"{{{namespace}}}t"

    lines: list[str] = []
    for paragraph in root.iter(paragraph_tag):
        fragments = [
            node.text or ""
            for node in paragraph.iter(text_tag)
        ]
        line = "".join(fragments).strip()
        if line:
            lines.append(line)

    return "\n".join(lines)
