"""Deterministic Project Attention Center composition service."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from hashlib import sha256
import json
from uuid import UUID

from sqlalchemy.orm import Session

from pmwizard.automation import (
    AutomationRunStatus,
    AutomationScheduleService,
)
from pmwizard.health import ProjectHealthHistoryService, ProjectHealthService
from pmwizard.health.history_schemas import TrendDirection
from pmwizard.health.schemas import HealthBand
from pmwizard.inbox import ProjectInboxService
from pmwizard.memory import ProjectMemoryQueryService
from pmwizard.models.enums import (
    ActionItemStatus,
    AssumptionStatus,
    DecisionStatus,
    DependencyStatus,
    IssueStatus,
    ReviewStatus,
    RiskStatus,
)
from pmwizard.sources import (
    SourceConnectionTestStatus,
    SourceHealthStatus,
    SourcesWorkspaceService,
)

from .repository import AttentionReceiptRepository
from .schemas import (
    AttentionCategory,
    AttentionCenterSnapshot,
    AttentionSeverity,
    AttentionSignalView,
    AttentionStateCommand,
    AttentionStateResponse,
    AttentionSummary,
    AttentionUserState,
)


_SEVERE = {"critical", "severe"}
_HIGH = {"high"}
_OPEN_ACTION = {
    ActionItemStatus.NOT_STARTED,
    ActionItemStatus.IN_PROGRESS,
    ActionItemStatus.BLOCKED,
    ActionItemStatus.PENDING_EXTERNAL,
    ActionItemStatus.READY_FOR_REVIEW,
}


@dataclass(frozen=True)
class _RawSignal:
    id: str
    signal_key: str
    fingerprint: str
    category: AttentionCategory
    severity: AttentionSeverity
    title: str
    detail: str
    target_view: str
    action_label: str
    entity_type: str | None = None
    entity_id: UUID | None = None
    due_date: date | None = None
    observed_at: datetime | None = None


class AttentionCenterService:
    def __init__(self, session: Session) -> None:
        self.session = session
        self.receipts = AttentionReceiptRepository(session)

    def snapshot(
        self,
        *,
        tenant_id: UUID,
        user_id: UUID,
        project_id: UUID,
        permissions: set[str],
        now: datetime | None = None,
    ) -> AttentionCenterSnapshot:
        timestamp = self._aware(now or datetime.now(timezone.utc))
        signals = self._active_signals(
            tenant_id=tenant_id,
            project_id=project_id,
            permissions=permissions,
            now=timestamp,
        )
        receipts = self.receipts.list_for_project(
            tenant_id=tenant_id,
            user_id=user_id,
            project_id=project_id,
        )
        views = [
            self._decorate(signal, receipts.get(signal.signal_key), timestamp)
            for signal in signals
        ]
        views.sort(key=self._sort_key)

        return AttentionCenterSnapshot(
            project_id=project_id,
            generated_at=timestamp,
            summary=AttentionSummary(
                active=len(views),
                unread=sum(item.state == AttentionUserState.UNREAD for item in views),
                critical=sum(item.severity == AttentionSeverity.CRITICAL for item in views),
                warning=sum(item.severity == AttentionSeverity.WARNING for item in views),
                info=sum(item.severity == AttentionSeverity.INFO for item in views),
                acknowledged=sum(
                    item.state == AttentionUserState.ACKNOWLEDGED for item in views
                ),
                snoozed=sum(item.state == AttentionUserState.SNOOZED for item in views),
            ),
            signals=views,
        )

    def update_state(
        self,
        *,
        tenant_id: UUID,
        user_id: UUID,
        project_id: UUID,
        permissions: set[str],
        signal_id: str,
        command: AttentionStateCommand,
        now: datetime | None = None,
    ) -> AttentionStateResponse:
        timestamp = self._aware(now or datetime.now(timezone.utc))
        signals = self._active_signals(
            tenant_id=tenant_id,
            project_id=project_id,
            permissions=permissions,
            now=timestamp,
        )
        signal = next((item for item in signals if item.id == signal_id), None)
        if signal is None:
            raise LookupError("Attention signal is no longer active.")

        snoozed_until = None
        if command.action == "snooze":
            snoozed_until = (
                self._aware(command.snoozed_until)
                if command.snoozed_until is not None
                else timestamp + timedelta(hours=24)
            )
            if snoozed_until <= timestamp:
                raise ValueError("snoozed_until must be in the future.")
            if snoozed_until > timestamp + timedelta(days=30):
                raise ValueError("Attention signals can be snoozed for at most 30 days.")
        elif command.snoozed_until is not None:
            raise ValueError("snoozed_until is only valid for snooze.")

        receipt = self.receipts.apply(
            tenant_id=tenant_id,
            user_id=user_id,
            project_id=project_id,
            signal_key=signal.signal_key,
            signal_fingerprint=signal.fingerprint,
            action=command.action,
            now=timestamp,
            snoozed_until=snoozed_until,
        )
        return AttentionStateResponse(
            signal=self._decorate(signal, receipt, timestamp)
        )

    def _active_signals(
        self,
        *,
        tenant_id: UUID,
        project_id: UUID,
        permissions: set[str],
        now: datetime,
    ) -> list[_RawSignal]:
        today = now.date()
        memory = ProjectMemoryQueryService(self.session).snapshot(
            tenant_id=tenant_id,
            project_id=project_id,
        )
        health = ProjectHealthService(self.session).snapshot(
            tenant_id=tenant_id,
            project_id=project_id,
            as_of=today,
        )
        history = ProjectHealthHistoryService(self.session).history(
            tenant_id=tenant_id,
            project_id=project_id,
            limit=2,
        )
        sources = SourcesWorkspaceService(self.session).snapshot(
            tenant_id=tenant_id,
            project_id=project_id,
        )
        automations = AutomationScheduleService(self.session).snapshot(
            tenant_id=tenant_id,
            project_id=project_id,
            now=now,
        )
        inbox = ProjectInboxService(self.session).list_items(
            tenant_id=tenant_id,
            project_id=project_id,
            permissions=permissions,
            statuses=[ReviewStatus.PENDING],
            limit=100,
        )

        signals: list[_RawSignal] = []
        signals.extend(self._health_signals(health, history))
        signals.extend(self._execution_signals(memory, today))
        signals.extend(self._raid_signals(memory))
        signals.extend(self._decision_signals(memory, today))
        signals.extend(self._source_signals(sources))
        signals.extend(self._automation_signals(automations))
        signals.extend(self._review_signals(inbox.items, now))
        return signals

    def _health_signals(self, health, history) -> list[_RawSignal]:
        signals: list[_RawSignal] = []
        if health.band == HealthBand.RED:
            signals.append(
                self._signal(
                    signal_key="health:band",
                    category=AttentionCategory.HEALTH,
                    severity=AttentionSeverity.CRITICAL,
                    title="Project Health is red",
                    detail=health.explanation,
                    target_view="health",
                    action_label="Open Project Health",
                    version={
                        "band": health.band.value,
                        "score": health.score,
                        "coverage": health.coverage_percent,
                        "drivers": [
                            (item.title, item.severity.value, item.penalty)
                            for item in health.key_drivers
                        ],
                    },
                )
            )
        elif health.band == HealthBand.AMBER:
            signals.append(
                self._signal(
                    signal_key="health:band",
                    category=AttentionCategory.HEALTH,
                    severity=AttentionSeverity.WARNING,
                    title="Project Health needs attention",
                    detail=health.explanation,
                    target_view="health",
                    action_label="Open Project Health",
                    version={
                        "band": health.band.value,
                        "score": health.score,
                        "coverage": health.coverage_percent,
                        "drivers": [
                            (item.title, item.severity.value, item.penalty)
                            for item in health.key_drivers
                        ],
                    },
                )
            )

        trend = history.trend
        if trend.direction == TrendDirection.DETERIORATING:
            severity = (
                AttentionSeverity.CRITICAL
                if trend.score_delta is not None and trend.score_delta <= -10
                else AttentionSeverity.WARNING
            )
            observed_at = (
                history.points[-1].captured_at if history.points else None
            )
            signals.append(
                self._signal(
                    signal_key="health:trend",
                    category=AttentionCategory.HEALTH,
                    severity=severity,
                    title="Project Health is deteriorating",
                    detail=trend.explanation,
                    target_view="health",
                    action_label="Review Health trend",
                    observed_at=observed_at,
                    version={
                        "from": str(trend.from_snapshot_id),
                        "to": str(trend.to_snapshot_id),
                        "delta": trend.score_delta,
                        "coverage_delta": trend.coverage_delta,
                    },
                )
            )
        return signals

    def _execution_signals(self, memory, today: date) -> list[_RawSignal]:
        signals: list[_RawSignal] = []
        for item in memory.action_items:
            if item.status == ActionItemStatus.BLOCKED:
                signals.append(
                    self._signal(
                        signal_key=f"action:blocked:{item.id}",
                        category=AttentionCategory.EXECUTION,
                        severity=AttentionSeverity.CRITICAL,
                        title=f"Blocked action: {item.title}",
                        detail="This governed Action Item is blocked.",
                        target_view="memory",
                        action_label="Open Project Memory",
                        entity_type="ActionItem",
                        entity_id=item.id,
                        due_date=item.due_date,
                        observed_at=item.updated_at,
                        version={
                            "status": item.status.value,
                            "due_date": item.due_date,
                            "priority": item.priority,
                            "updated_at": item.updated_at,
                        },
                    )
                )
                continue
            if (
                item.status in _OPEN_ACTION
                and item.due_date is not None
                and item.due_date < today
            ):
                severity = (
                    AttentionSeverity.CRITICAL
                    if (item.priority or "").casefold() in _SEVERE
                    else AttentionSeverity.WARNING
                )
                signals.append(
                    self._signal(
                        signal_key=f"action:overdue:{item.id}",
                        category=AttentionCategory.EXECUTION,
                        severity=severity,
                        title=f"Overdue action: {item.title}",
                        detail=f"Due date {item.due_date.isoformat()} has passed.",
                        target_view="memory",
                        action_label="Review Action Item",
                        entity_type="ActionItem",
                        entity_id=item.id,
                        due_date=item.due_date,
                        observed_at=item.updated_at,
                        version={
                            "status": item.status.value,
                            "due_date": item.due_date,
                            "priority": item.priority,
                            "updated_at": item.updated_at,
                        },
                    )
                )
        return signals

    def _raid_signals(self, memory) -> list[_RawSignal]:
        signals: list[_RawSignal] = []
        for risk in memory.risks:
            impact = (risk.impact or "").casefold()
            if risk.status == RiskStatus.MATERIALIZED:
                severity = AttentionSeverity.CRITICAL
                detail = "A governed project Risk has materialized."
            elif risk.status != RiskStatus.CLOSED and impact in _SEVERE | _HIGH:
                severity = (
                    AttentionSeverity.CRITICAL
                    if impact in _SEVERE
                    else AttentionSeverity.WARNING
                )
                detail = f"Active Risk impact is {risk.impact}."
            else:
                continue
            signals.append(
                self._signal(
                    signal_key=f"raid:risk:{risk.id}",
                    category=AttentionCategory.RAID,
                    severity=severity,
                    title=f"Risk: {risk.title}",
                    detail=detail,
                    target_view="memory",
                    action_label="Review RAID",
                    entity_type="Risk",
                    entity_id=risk.id,
                    due_date=risk.due_date,
                    observed_at=risk.updated_at,
                    version={
                        "status": risk.status.value,
                        "impact": risk.impact,
                        "exposure": risk.exposure,
                        "due_date": risk.due_date,
                        "updated_at": risk.updated_at,
                    },
                )
            )

        for assumption in memory.assumptions:
            if assumption.status != AssumptionStatus.INVALIDATED:
                continue
            signals.append(
                self._signal(
                    signal_key=f"raid:assumption:{assumption.id}",
                    category=AttentionCategory.RAID,
                    severity=AttentionSeverity.WARNING,
                    title=f"Invalidated assumption: {assumption.title}",
                    detail="A governed project Assumption was invalidated.",
                    target_view="memory",
                    action_label="Review RAID",
                    entity_type="Assumption",
                    entity_id=assumption.id,
                    due_date=assumption.validation_date,
                    observed_at=assumption.updated_at,
                    version={
                        "status": assumption.status.value,
                        "validation_date": assumption.validation_date,
                        "updated_at": assumption.updated_at,
                    },
                )
            )

        for issue in memory.issues:
            severity_label = (issue.severity or "").casefold()
            if issue.status == IssueStatus.BLOCKED:
                severity = AttentionSeverity.CRITICAL
                detail = "A governed project Issue is blocked."
            elif (
                issue.status not in {IssueStatus.RESOLVED, IssueStatus.CLOSED}
                and severity_label in _SEVERE | _HIGH
            ):
                severity = (
                    AttentionSeverity.CRITICAL
                    if severity_label in _SEVERE
                    else AttentionSeverity.WARNING
                )
                detail = f"Active Issue severity is {issue.severity}."
            else:
                continue
            signals.append(
                self._signal(
                    signal_key=f"raid:issue:{issue.id}",
                    category=AttentionCategory.RAID,
                    severity=severity,
                    title=f"Issue: {issue.title}",
                    detail=detail,
                    target_view="memory",
                    action_label="Review RAID",
                    entity_type="Issue",
                    entity_id=issue.id,
                    due_date=issue.due_date,
                    observed_at=issue.updated_at,
                    version={
                        "status": issue.status.value,
                        "severity": issue.severity,
                        "due_date": issue.due_date,
                        "updated_at": issue.updated_at,
                    },
                )
            )

        for dependency in memory.dependencies:
            criticality = (dependency.criticality or "").casefold()
            if dependency.status == DependencyStatus.BLOCKED:
                severity = AttentionSeverity.CRITICAL
                detail = "A governed project Dependency is blocked."
            elif (
                dependency.status
                not in {
                    DependencyStatus.SATISFIED,
                    DependencyStatus.WAIVED,
                    DependencyStatus.CLOSED,
                }
                and criticality in _SEVERE | _HIGH
            ):
                severity = (
                    AttentionSeverity.CRITICAL
                    if criticality in _SEVERE
                    else AttentionSeverity.WARNING
                )
                detail = (
                    f"Active Dependency criticality is {dependency.criticality}."
                )
            else:
                continue
            signals.append(
                self._signal(
                    signal_key=f"raid:dependency:{dependency.id}",
                    category=AttentionCategory.RAID,
                    severity=severity,
                    title=f"Dependency: {dependency.title}",
                    detail=detail,
                    target_view="memory",
                    action_label="Review RAID",
                    entity_type="Dependency",
                    entity_id=dependency.id,
                    due_date=dependency.required_by,
                    observed_at=dependency.updated_at,
                    version={
                        "status": dependency.status.value,
                        "criticality": dependency.criticality,
                        "required_by": dependency.required_by,
                        "updated_at": dependency.updated_at,
                    },
                )
            )
        return signals

    def _decision_signals(self, memory, today: date) -> list[_RawSignal]:
        signals: list[_RawSignal] = []
        for decision in memory.decisions:
            if (
                decision.status not in {DecisionStatus.PROPOSED, DecisionStatus.PENDING}
                or decision.review_date is None
                or decision.review_date >= today
            ):
                continue
            age = (today - decision.review_date).days
            signals.append(
                self._signal(
                    signal_key=f"decision:stale:{decision.id}",
                    category=AttentionCategory.DECISION,
                    severity=(
                        AttentionSeverity.CRITICAL
                        if age >= 7
                        else AttentionSeverity.WARNING
                    ),
                    title=f"Decision review overdue: {decision.title}",
                    detail=(
                        f"Decision review date {decision.review_date.isoformat()} "
                        "has passed."
                    ),
                    target_view="memory",
                    action_label="Review Decision",
                    entity_type="Decision",
                    entity_id=decision.id,
                    due_date=decision.review_date,
                    observed_at=decision.updated_at,
                    version={
                        "status": decision.status.value,
                        "review_date": decision.review_date,
                        "updated_at": decision.updated_at,
                    },
                )
            )
        return signals

    def _source_signals(self, sources) -> list[_RawSignal]:
        signals: list[_RawSignal] = []
        for source in sources.sources:
            if source.health == SourceHealthStatus.FAILED:
                signals.append(
                    self._signal(
                        signal_key=f"source:health:{source.id}",
                        category=AttentionCategory.SOURCE,
                        severity=AttentionSeverity.CRITICAL,
                        title=f"Source sync failed: {source.display_name}",
                        detail="The latest durable Source run failed.",
                        target_view="sources",
                        action_label="Open Sources",
                        entity_type="SourceConnection",
                        entity_id=source.id,
                        observed_at=(
                            source.latest_run.finished_at
                            if source.latest_run is not None
                            else None
                        ),
                        version={
                            "health": source.health.value,
                            "run_id": (
                                str(source.latest_run.id)
                                if source.latest_run is not None
                                else None
                            ),
                            "errors": (
                                source.latest_run.errors
                                if source.latest_run is not None
                                else []
                            ),
                        },
                    )
                )
            elif source.health == SourceHealthStatus.ATTENTION:
                signals.append(
                    self._signal(
                        signal_key=f"source:health:{source.id}",
                        category=AttentionCategory.SOURCE,
                        severity=AttentionSeverity.WARNING,
                        title=f"Source needs attention: {source.display_name}",
                        detail=(
                            "The latest Source run completed with skips or errors."
                        ),
                        target_view="sources",
                        action_label="Inspect Source",
                        entity_type="SourceConnection",
                        entity_id=source.id,
                        observed_at=(
                            source.latest_run.finished_at
                            if source.latest_run is not None
                            else None
                        ),
                        version={
                            "health": source.health.value,
                            "run_id": (
                                str(source.latest_run.id)
                                if source.latest_run is not None
                                else None
                            ),
                            "errors": (
                                source.latest_run.errors
                                if source.latest_run is not None
                                else []
                            ),
                            "skipped": (
                                source.latest_run.skipped
                                if source.latest_run is not None
                                else 0
                            ),
                        },
                    )
                )
            elif (
                source.health == SourceHealthStatus.NEVER_SYNCED
                and source.is_enabled
                and source.credential_configured
            ):
                signals.append(
                    self._signal(
                        signal_key=f"source:never-synced:{source.id}",
                        category=AttentionCategory.SOURCE,
                        severity=AttentionSeverity.INFO,
                        title=f"Source has not synced: {source.display_name}",
                        detail=(
                            "This enabled credential-ready Source has no durable "
                            "sync run yet."
                        ),
                        target_view="sources",
                        action_label="Open Sources",
                        entity_type="SourceConnection",
                        entity_id=source.id,
                        version={
                            "health": source.health.value,
                            "enabled": source.is_enabled,
                            "credential": source.credential_configured,
                        },
                    )
                )

            if (
                source.connection_test.status
                == SourceConnectionTestStatus.FAILED
            ):
                signals.append(
                    self._signal(
                        signal_key=f"source:test:{source.id}",
                        category=AttentionCategory.SOURCE,
                        severity=AttentionSeverity.WARNING,
                        title=f"Connection test failed: {source.display_name}",
                        detail=(
                            source.connection_test.message
                            or "The latest Source connection test failed."
                        ),
                        target_view="sources",
                        action_label="Inspect Source",
                        entity_type="SourceConnection",
                        entity_id=source.id,
                        observed_at=source.connection_test.last_test_at,
                        version={
                            "status": source.connection_test.status.value,
                            "last_test_at": source.connection_test.last_test_at,
                            "message": source.connection_test.message,
                        },
                    )
                )
        return signals

    def _automation_signals(self, automations) -> list[_RawSignal]:
        signals: list[_RawSignal] = []
        for schedule in automations.schedules:
            if not schedule.enabled:
                continue
            if schedule.last_status not in {
                AutomationRunStatus.FAILED,
                AutomationRunStatus.ABANDONED,
            }:
                continue
            signals.append(
                self._signal(
                    signal_key=f"automation:failure:{schedule.id}",
                    category=AttentionCategory.AUTOMATION,
                    severity=(
                        AttentionSeverity.CRITICAL
                        if schedule.consecutive_failures >= 3
                        else AttentionSeverity.WARNING
                    ),
                    title=f"Automation failing: {schedule.name}",
                    detail=(
                        f"Last run status is {schedule.last_status.value}; "
                        f"{schedule.consecutive_failures} consecutive failure(s)."
                    ),
                    target_view="automations",
                    action_label="Open Automations",
                    entity_type="AutomationSchedule",
                    entity_id=schedule.id,
                    observed_at=schedule.last_run_at,
                    version={
                        "last_status": schedule.last_status.value,
                        "last_run_at": schedule.last_run_at,
                        "consecutive_failures": schedule.consecutive_failures,
                    },
                )
            )
        return signals

    def _review_signals(self, items, now: datetime) -> list[_RawSignal]:
        if not items:
            return []
        oldest = min(item.created_at for item in items)
        if oldest.tzinfo is None:
            oldest = oldest.replace(tzinfo=timezone.utc)
        age = now - oldest
        severity = (
            AttentionSeverity.WARNING
            if age >= timedelta(days=3)
            else AttentionSeverity.INFO
        )
        return [
            self._signal(
                signal_key="review:pending-inbox",
                category=AttentionCategory.REVIEW,
                severity=severity,
                title=f"{len(items)} Project Inbox item(s) awaiting review",
                detail=(
                    "Evidence-backed AI suggestions remain pending human "
                    "governance."
                ),
                target_view="inbox",
                action_label="Open Project Inbox",
                observed_at=max(item.created_at for item in items),
                version={
                    "suggestions": sorted(
                        (str(item.id), item.created_at.isoformat())
                        for item in items
                    )
                },
            )
        ]

    def _signal(
        self,
        *,
        signal_key: str,
        category: AttentionCategory,
        severity: AttentionSeverity,
        title: str,
        detail: str,
        target_view: str,
        action_label: str,
        version: dict,
        entity_type: str | None = None,
        entity_id: UUID | None = None,
        due_date: date | None = None,
        observed_at: datetime | None = None,
    ) -> _RawSignal:
        fingerprint = self._fingerprint(version)
        signal_id = sha256(
            f"{signal_key}:{fingerprint}".encode("utf-8")
        ).hexdigest()[:24]
        return _RawSignal(
            id=signal_id,
            signal_key=signal_key,
            fingerprint=fingerprint,
            category=category,
            severity=severity,
            title=title,
            detail=detail,
            target_view=target_view,
            action_label=action_label,
            entity_type=entity_type,
            entity_id=entity_id,
            due_date=due_date,
            observed_at=observed_at,
        )

    @classmethod
    def _fingerprint(cls, value: dict) -> str:
        encoded = json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            default=cls._json_default,
        )
        return sha256(encoded.encode("utf-8")).hexdigest()

    @staticmethod
    def _json_default(value):
        if isinstance(value, (date, datetime)):
            return value.isoformat()
        if isinstance(value, UUID):
            return str(value)
        raise TypeError(f"Unsupported Attention fingerprint value: {type(value)!r}")

    def _decorate(self, signal: _RawSignal, receipt, now: datetime) -> AttentionSignalView:
        state = AttentionUserState.UNREAD
        snoozed_until = None
        if receipt is not None and receipt.signal_fingerprint == signal.fingerprint:
            if receipt.snoozed_until is not None:
                snoozed_until = self._aware(receipt.snoozed_until)
            if snoozed_until is not None and snoozed_until > now:
                state = AttentionUserState.SNOOZED
            elif receipt.acknowledged_at is not None:
                state = AttentionUserState.ACKNOWLEDGED
            elif receipt.seen_at is not None:
                state = AttentionUserState.SEEN

        return AttentionSignalView(
            id=signal.id,
            signal_key=signal.signal_key,
            category=signal.category,
            severity=signal.severity,
            title=signal.title,
            detail=signal.detail,
            target_view=signal.target_view,
            action_label=signal.action_label,
            entity_type=signal.entity_type,
            entity_id=signal.entity_id,
            due_date=signal.due_date,
            observed_at=signal.observed_at,
            state=state,
            snoozed_until=snoozed_until,
        )

    @staticmethod
    def _sort_key(signal: AttentionSignalView):
        state_rank = {
            AttentionUserState.UNREAD: 0,
            AttentionUserState.SEEN: 1,
            AttentionUserState.ACKNOWLEDGED: 2,
            AttentionUserState.SNOOZED: 3,
        }[signal.state]
        severity_rank = {
            AttentionSeverity.CRITICAL: 0,
            AttentionSeverity.WARNING: 1,
            AttentionSeverity.INFO: 2,
        }[signal.severity]
        return (
            state_rank,
            severity_rank,
            signal.due_date is None,
            signal.due_date or date.max,
            signal.title.casefold(),
        )

    @staticmethod
    def _aware(value: datetime) -> datetime:
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value
