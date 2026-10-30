"""A bounded, tenant-scoped timeline across existing project activity records.

Only safe metadata leaves this service. Raw audit states, source errors, AI
prompts, reviewer notes, connector keys, and worker identifiers are excluded.
"""

from __future__ import annotations

import base64
import json
from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import and_, or_, select
from sqlalchemy.orm import Session

from pmwizard.persistence.orm import (
    AISuggestionORM,
    AuditLogORM,
    AutomationRunORM,
    ConnectorRunORM,
    EventORM,
    EvidenceORM,
    HumanReviewORM,
    ProjectHealthSnapshotORM,
    ProjectORM,
)

from .schemas import ActivityCategory, ActivityItem, ActivityTimeline


# Only named, governance-safe fields are described, never their stored values.
SAFE_CHANGE_FIELDS = frozenset({
    "status",
    "priority",
    "due_date",
    "planned_end_date",
    "forecast_end_date",
    "lifecycle_phase",
    "owner_id",
    "progress_summary",
    "review_status",
    "score",
    "band",
    "is_enabled",
})


def _utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _changed(before: dict | None, after: dict | None) -> list[str]:
    if before is None or after is None:
        return []
    return sorted(
        name
        for name in SAFE_CHANGE_FIELDS & (before.keys() | after.keys())
        if before.get(name) != after.get(name)
    )


def _uuid_list(values: list | None) -> list[UUID]:
    result = []
    for value in values or []:
        try:
            result.append(UUID(str(value)))
        except (TypeError, ValueError, AttributeError):
            continue
    return result


def _cursor_for(item: ActivityItem) -> str:
    payload = {
        "t": _utc(item.occurred_at).isoformat(),
        "c": item.category.value,
        "id": str(item.id),
    }
    raw = json.dumps(payload, separators=(",", ":"), sort_keys=True).encode()
    return base64.urlsafe_b64encode(raw).decode().rstrip("=")


def _parse_cursor(cursor: str | None) -> tuple[datetime, ActivityCategory, UUID] | None:
    if cursor is None:
        return None
    if len(cursor) > 256 or not cursor:
        raise ValueError("Invalid activity cursor")
    try:
        raw = base64.b64decode(
            cursor + "=" * (-len(cursor) % 4),
            altchars=b"-_",
            validate=True,
        )
        payload = json.loads(raw)
        if not isinstance(payload, dict) or set(payload) != {"t", "c", "id"}:
            raise ValueError
        timestamp = datetime.fromisoformat(payload["t"])
        if timestamp.tzinfo is None:
            raise ValueError
        return _utc(timestamp), ActivityCategory(payload["c"]), UUID(payload["id"])
    except (ValueError, TypeError, KeyError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("Invalid activity cursor") from exc


class ProjectActivityService:
    """Unifies immutable activity without modifying project truth."""

    def __init__(self, session: Session) -> None:
        self.session = session

    def timeline(
        self,
        *,
        tenant_id: UUID,
        project_id: UUID,
        permissions: set[str],
        categories: list[ActivityCategory] | None = None,
        actor_id: UUID | None = None,
        since: datetime | None = None,
        until: datetime | None = None,
        cursor: str | None = None,
        limit: int = 40,
    ) -> ActivityTimeline:
        if "project:read" not in permissions:
            raise PermissionError("project:read is required")
        if type(limit) is not int or not 1 <= limit <= 100:
            raise ValueError("limit must be between 1 and 100")
        if (since is not None and since.tzinfo is None) or (
            until is not None and until.tzinfo is None
        ):
            raise ValueError("Date filters must include timezone offsets")
        if since is not None and until is not None and since > until:
            raise ValueError("since must be on or before until")

        exists = self.session.scalar(
            select(ProjectORM.id).where(
                ProjectORM.tenant_id == tenant_id,
                ProjectORM.id == project_id,
            )
        )
        if exists is None:
            raise LookupError("Project not found for tenant")

        position = _parse_cursor(cursor)
        chosen = set(categories) if categories is not None else set(ActivityCategory)
        sources = (
            (ActivityCategory.EVENT, EventORM, EventORM.occurred_at, EventORM.actor_id),
            (
                ActivityCategory.HUMAN_REVIEW, HumanReviewORM,
                HumanReviewORM.reviewed_at, HumanReviewORM.reviewer_id,
            ),
            (ActivityCategory.AUDIT, AuditLogORM, AuditLogORM.created_at, AuditLogORM.actor_id),
            (ActivityCategory.SOURCE_RUN, ConnectorRunORM, ConnectorRunORM.finished_at, None),
            (
                ActivityCategory.AUTOMATION_RUN, AutomationRunORM,
                AutomationRunORM.started_at, None,
            ),
            (
                ActivityCategory.HEALTH_SNAPSHOT, ProjectHealthSnapshotORM,
                ProjectHealthSnapshotORM.captured_at, ProjectHealthSnapshotORM.captured_by,
            ),
        )
        rows: list[tuple[ActivityCategory, object]] = []
        for category, model, timestamp_field, actor_field in sources:
            if category not in chosen or (actor_id is not None and actor_field is None):
                continue
            statement = select(model).where(
                model.tenant_id == tenant_id,
                model.project_id == project_id,
            )
            if since is not None:
                statement = statement.where(timestamp_field >= _utc(since))
            if until is not None:
                statement = statement.where(timestamp_field <= _utc(until))
            if actor_id is not None:
                statement = statement.where(actor_field == actor_id)
            if position is not None:
                ts, cursor_category, cursor_id = position
                if category.value < cursor_category.value:
                    statement = statement.where(timestamp_field <= ts)
                elif category.value > cursor_category.value:
                    statement = statement.where(timestamp_field < ts)
                else:
                    statement = statement.where(
                        or_(
                            timestamp_field < ts,
                            and_(timestamp_field == ts, model.id < cursor_id),
                        )
                    )
            statement = statement.order_by(
                timestamp_field.desc(), model.id.desc()
            ).limit(limit + 1)
            rows.extend(
                (category, row)
                for row in self.session.scalars(statement).all()
            )

        # Reviews reference suggestions; fetch only tenant/project-matched IDs.
        review_ids = {
            row.suggestion_id for category, row in rows
            if category == ActivityCategory.HUMAN_REVIEW
        }
        suggestion_evidence: dict[UUID, list[UUID]] = {}
        if review_ids:
            suggestions = self.session.execute(
                select(AISuggestionORM.id, AISuggestionORM.evidence_ids).where(
                    AISuggestionORM.tenant_id == tenant_id,
                    AISuggestionORM.project_id == project_id,
                    AISuggestionORM.id.in_(review_ids),
                )
            )
            suggestion_evidence = {
                suggestion_id: _uuid_list(evidence)
                for suggestion_id, evidence in suggestions
            }

        linked_ids: set[UUID] = set()
        for category, row in rows:
            if category == ActivityCategory.EVENT and row.source_evidence_id:
                linked_ids.add(row.source_evidence_id)
            elif category == ActivityCategory.AUDIT:
                linked_ids.update(_uuid_list(row.evidence_ids))
            elif category == ActivityCategory.HUMAN_REVIEW:
                linked_ids.update(suggestion_evidence.get(row.suggestion_id, []))
        visible_ids: set[UUID] = set()
        if linked_ids:
            evidence_rows = self.session.execute(
                select(EvidenceORM.id, EvidenceORM.permission_scope).where(
                    EvidenceORM.tenant_id == tenant_id,
                    EvidenceORM.project_id == project_id,
                    EvidenceORM.id.in_(linked_ids),
                )
            )
            visible_ids = {
                evidence_id for evidence_id, required_scopes in evidence_rows
                if set(required_scopes or []).issubset(permissions)
            }

        items = [
            self._item(category, row, visible_ids, suggestion_evidence)
            for category, row in rows
        ]
        items.sort(
            key=lambda item: (
                _utc(item.occurred_at),
                item.category.value,
                str(item.id),
            ),
            reverse=True,
        )
        has_more = len(items) > limit
        page = items[:limit]
        return ActivityTimeline(
            project_id=project_id,
            count=len(page),
            items=page,
            next_cursor=_cursor_for(page[-1]) if has_more and page else None,
        )

    @staticmethod
    def _item(
        category: ActivityCategory,
        row: object,
        visible_ids: set[UUID],
        suggestion_evidence: dict[UUID, list[UUID]],
    ) -> ActivityItem:
        base = {"id": row.id, "category": category}
        if category == ActivityCategory.EVENT:
            linked = [row.source_evidence_id] if row.source_evidence_id else []
            return ActivityItem(
                **base,
                occurred_at=_utc(row.occurred_at),
                actor_kind="human" if row.actor_id else "system",
                actor_id=row.actor_id,
                action=row.event_type,
                entity_type=row.entity_type,
                entity_id=row.entity_id,
                changed_fields=_changed(row.previous_value, row.new_value),
                evidence_ids=[value for value in linked if value in visible_ids],
            )
        if category == ActivityCategory.HUMAN_REVIEW:
            return ActivityItem(
                **base,
                occurred_at=_utc(row.reviewed_at),
                actor_kind="human",
                actor_id=row.reviewer_id,
                action="suggestion_reviewed",
                entity_type="AISuggestion",
                entity_id=row.suggestion_id,
                status=row.status,
                summary="Human review of an AI-proposed change.",
                changed_fields=sorted(SAFE_CHANGE_FIELDS & row.final_changes.keys()),
                evidence_ids=[
                    value for value in suggestion_evidence.get(row.suggestion_id, [])
                    if value in visible_ids
                ],
            )
        if category == ActivityCategory.AUDIT:
            return ActivityItem(
                **base,
                occurred_at=_utc(row.created_at),
                actor_kind="human" if row.actor_id else "system",
                actor_id=row.actor_id,
                action=row.action,
                entity_type=row.entity_type,
                entity_id=row.entity_id,
                summary="Governance action recorded.",
                changed_fields=_changed(row.previous_state, row.final_state),
                evidence_ids=[
                    value for value in _uuid_list(row.evidence_ids)
                    if value in visible_ids
                ],
            )
        if category == ActivityCategory.SOURCE_RUN:
            return ActivityItem(
                **base,
                occurred_at=_utc(row.finished_at),
                actor_kind="worker",
                action="source_sync",
                entity_type="ConnectorRun",
                entity_id=row.id,
                status=row.status,
                summary=f"Ingested {row.ingested}; duplicates {row.duplicates}; skipped {row.skipped}.",
            )
        if category == ActivityCategory.AUTOMATION_RUN:
            return ActivityItem(
                **base,
                occurred_at=_utc(row.started_at),
                actor_kind="worker",
                action=row.task_type,
                entity_type="AutomationSchedule",
                entity_id=row.schedule_id,
                status=row.status,
                summary=f"Trigger: {row.trigger}.",
            )
        return ActivityItem(
            **base,
            occurred_at=_utc(row.captured_at),
            actor_kind="human" if row.captured_by else "worker",
            actor_id=row.captured_by,
            action="health_captured",
            entity_type="ProjectHealthSnapshot",
            entity_id=row.id,
            status=row.band,
            summary=(
                f"Health score {row.score if row.score is not None else 'N/A'}; "
                f"coverage {row.coverage_percent}%."
            ),
        )
