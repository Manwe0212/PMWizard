"""Bounded, permission-preserving exports of the Project Activity timeline.

An export contains only the redacted ActivityItem contract from PR #23.
The SHA-256 header is a *file checksum*, not an authenticity signature.
"""

from __future__ import annotations

import csv
import hashlib
import io
import json
from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Literal
from uuid import UUID

from sqlalchemy.orm import Session

from .schemas import ActivityCategory, ActivityItem
from .service import ProjectActivityService

ExportFormat = Literal["csv", "json"]
MAX_EXPORT_ROWS = 500
PAGE_SIZE = 100

CSV_COLUMNS = (
    "id",
    "occurred_at",
    "category",
    "action",
    "status",
    "actor_kind",
    "actor_id",
    "entity_type",
    "entity_id",
    "summary",
    "changed_fields",
    "evidence_ids",
)


@dataclass(frozen=True)
class ActivityExport:
    body: bytes
    content_type: str
    filename: str
    sha256: str
    count: int
    truncated: bool


def _csv_safe(value: object) -> str:
    """Prevent spreadsheet formula evaluation, including whitespace-prefixed cells."""
    text = "" if value is None else str(value)
    if text.lstrip(" \t\r\n\ufeff").startswith(("=", "+", "-", "@")):
        return "'" + text
    return text


def _record(item: ActivityItem) -> dict[str, object]:
    return item.model_dump(mode="json")


class ProjectActivityExportService:
    def __init__(self, session: Session) -> None:
        self.activity = ProjectActivityService(session)

    def export(
        self,
        *,
        tenant_id: UUID,
        project_id: UUID,
        permissions: set[str],
        export_format: ExportFormat = "csv",
        categories: list[ActivityCategory] | None = None,
        actor_id: UUID | None = None,
        since: datetime | None = None,
        until: datetime | None = None,
        max_rows: int = MAX_EXPORT_ROWS,
    ) -> ActivityExport:
        # A bulk download is more privileged than browsing individual pages.
        if not {"project:read", "project:review"}.issubset(permissions):
            raise PermissionError("Export requires project:read and project:review")
        if export_format not in ("csv", "json"):
            raise ValueError("Unsupported export format")
        if type(max_rows) is not int or not 1 <= max_rows <= MAX_EXPORT_ROWS:
            raise ValueError("Invalid export row limit")

        collected: list[ActivityItem] = []
        cursor: str | None = None
        truncated = False
        while len(collected) < max_rows:
            page = self.activity.timeline(
                tenant_id=tenant_id,
                project_id=project_id,
                permissions=permissions,
                categories=categories,
                actor_id=actor_id,
                since=since,
                until=until,
                cursor=cursor,
                limit=min(PAGE_SIZE, max_rows - len(collected)),
            )
            collected.extend(page.items)
            if page.next_cursor is None:
                break
            if len(collected) >= max_rows:
                truncated = True
                break
            cursor = page.next_cursor

        generated_at = datetime.now(timezone.utc)
        if export_format == "csv":
            output = io.StringIO(newline="")
            writer = csv.writer(output, lineterminator="\r\n")
            writer.writerow(CSV_COLUMNS)
            for item in collected:
                item_data = _record(item)
                cells: list[object] = [
                    item_data["id"],
                    item_data["occurred_at"],
                    item_data["category"],
                    item_data["action"],
                    item_data["status"],
                    item_data["actor_kind"],
                    item_data["actor_id"],
                    item_data["entity_type"],
                    item_data["entity_id"],
                    item_data["summary"],
                    ";".join(item_data["changed_fields"]),
                    ";".join(item_data["evidence_ids"]),
                ]
                writer.writerow([_csv_safe(value) for value in cells])
            body = output.getvalue().encode("utf-8")
            content_type = "text/csv; charset=utf-8"
        else:
            by_category = Counter(item.category.value for item in collected)
            document = {
                "schema_version": "activity-export-v0",
                "generated_at": generated_at.isoformat(),
                "project_id": str(project_id),
                "filters": {
                    "category": (
                        sorted(set(category.value for category in categories))
                        if categories is not None else None
                    ),
                    "actor_id": str(actor_id) if actor_id is not None else None,
                    "since": since.astimezone(timezone.utc).isoformat() if since else None,
                    "until": until.astimezone(timezone.utc).isoformat() if until else None,
                },
                "row_count": len(collected),
                "truncated": truncated,
                "category_counts": dict(sorted(by_category.items())),
                "items": [_record(item) for item in collected],
                "limitations": [
                    "Only authorized, redacted activity metadata is included.",
                    "Evidence IDs are references, not evidence contents.",
                    "SHA-256 is a checksum, not a signature or immutable audit chain.",
                ],
            }
            body = (
                json.dumps(document, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
                + "\n"
            ).encode("utf-8")
            content_type = "application/json; charset=utf-8"

        filename = (
            f"pmwizard-activity-{str(project_id)[:8]}-"
            f"{generated_at:%Y%m%dT%H%M%SZ}.{export_format}"
        )
        return ActivityExport(
            body=body,
            content_type=content_type,
            filename=filename,
            sha256=hashlib.sha256(body).hexdigest(),
            count=len(collected),
            truncated=truncated,
        )
