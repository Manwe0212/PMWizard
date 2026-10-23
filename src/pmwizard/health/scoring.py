"""Deterministic and explainable Project Health V0 scoring."""

from __future__ import annotations

from datetime import date
from math import floor

from pmwizard.memory import ProjectMemorySnapshot
from pmwizard.models.enums import (
    ActionItemStatus,
    AssumptionStatus,
    DecisionStatus,
    DependencyStatus,
    IssueStatus,
    RiskStatus,
)
from pmwizard.sources import SourceHealthStatus, SourcesWorkspaceSnapshot

from .schemas import (
    CoverageBand,
    HealthBand,
    HealthFactor,
    HealthSignal,
    ProjectHealthSnapshot,
    SignalSeverity,
)


DELIVERY_WEIGHT = 35
RAID_WEIGHT = 35
DECISIONS_WEIGHT = 15
SOURCES_WEIGHT = 15


def score_band(score: int) -> HealthBand:
    if score >= 80:
        return HealthBand.GREEN
    if score >= 60:
        return HealthBand.AMBER
    return HealthBand.RED


def coverage_band(coverage: int) -> CoverageBand:
    if coverage >= 75:
        return CoverageBand.HIGH
    if coverage >= 50:
        return CoverageBand.MEDIUM
    return CoverageBand.LOW


def evaluate_project_health(
    memory: ProjectMemorySnapshot,
    sources: SourcesWorkspaceSnapshot,
    *,
    as_of: date,
) -> ProjectHealthSnapshot:
    factors = [
        _delivery_factor(memory, as_of),
        _raid_factor(memory),
        _decisions_factor(memory, as_of),
        _sources_factor(sources),
    ]

    available = [factor for factor in factors if factor.available]
    available_weight = sum(factor.weight for factor in available)
    coverage = available_weight

    if available_weight == 0:
        overall_score = None
        overall_band = HealthBand.INSUFFICIENT_DATA
        explanation = (
            "No operational health factors contain enough governed data to score "
            "this project yet."
        )
    else:
        weighted = sum(
            (factor.score or 0) * factor.weight
            for factor in available
        )
        overall_score = round(weighted / available_weight)
        overall_band = (
            HealthBand.INSUFFICIENT_DATA
            if coverage < 35
            else score_band(overall_score)
        )
        explanation = _overall_explanation(
            overall_score,
            overall_band,
            coverage,
        )

    drivers = [
        signal
        for factor in factors
        for signal in factor.signals
        if signal.penalty > 0
    ]
    drivers.sort(
        key=lambda item: (
            0 if item.severity == SignalSeverity.CRITICAL else 1,
            -item.penalty,
            item.title,
        )
    )

    return ProjectHealthSnapshot(
        project_id=memory.project.id,
        project_name=memory.project.name,
        assessed_on=as_of,
        score=overall_score,
        band=overall_band,
        coverage_percent=coverage,
        coverage_band=coverage_band(coverage),
        available_weight=available_weight,
        explanation=explanation,
        factors=factors,
        key_drivers=drivers[:5],
    )


def _delivery_factor(
    memory: ProjectMemorySnapshot,
    as_of: date,
) -> HealthFactor:
    actions = memory.action_items
    project = memory.project
    has_schedule = (
        project.planned_end_date is not None
        or project.forecast_end_date is not None
    )
    available = bool(actions) or has_schedule

    if not available:
        return _unavailable_factor(
            "delivery",
            "Delivery",
            DELIVERY_WEIGHT,
            "No Action Items or schedule dates are recorded yet.",
        )

    score = 100
    signals: list[HealthSignal] = []
    open_actions = [
        item
        for item in actions
        if item.status
        not in {
            ActionItemStatus.COMPLETED,
            ActionItemStatus.CANCELLED,
        }
    ]

    if open_actions:
        blocked = [
            item for item in open_actions
            if item.status == ActionItemStatus.BLOCKED
        ]
        if blocked:
            penalty = min(
                35,
                round(35 * len(blocked) / len(open_actions)),
            )
            score -= penalty
            signals.append(
                HealthSignal(
                    severity=SignalSeverity.CRITICAL,
                    title="Blocked Action Items",
                    detail=(
                        f"{len(blocked)} of {len(open_actions)} open Action Items "
                        "are blocked."
                    ),
                    penalty=penalty,
                    entity_type="ActionItem",
                    entity_ids=[item.id for item in blocked[:10]],
                )
            )

        overdue = [
            item for item in open_actions
            if item.due_date is not None and item.due_date < as_of
        ]
        if overdue:
            penalty = min(
                30,
                round(30 * len(overdue) / len(open_actions)),
            )
            score -= penalty
            signals.append(
                HealthSignal(
                    severity=SignalSeverity.WARNING,
                    title="Overdue Action Items",
                    detail=(
                        f"{len(overdue)} of {len(open_actions)} open Action Items "
                        "are past due."
                    ),
                    penalty=penalty,
                    entity_type="ActionItem",
                    entity_ids=[item.id for item in overdue[:10]],
                )
            )

        pending_external = [
            item for item in open_actions
            if item.status == ActionItemStatus.PENDING_EXTERNAL
        ]
        if pending_external:
            penalty = min(
                15,
                round(15 * len(pending_external) / len(open_actions)),
            )
            score -= penalty
            signals.append(
                HealthSignal(
                    severity=SignalSeverity.WARNING,
                    title="External Dependencies on Delivery",
                    detail=(
                        f"{len(pending_external)} open Action Items are waiting on "
                        "external parties."
                    ),
                    penalty=penalty,
                    entity_type="ActionItem",
                    entity_ids=[item.id for item in pending_external[:10]],
                )
            )

    if (
        project.planned_end_date is not None
        and project.forecast_end_date is not None
        and project.forecast_end_date > project.planned_end_date
    ):
        slip_days = (
            project.forecast_end_date - project.planned_end_date
        ).days
        if slip_days <= 7:
            penalty = 10
        elif slip_days <= 30:
            penalty = 20
        else:
            penalty = 30
        score -= penalty
        signals.append(
            HealthSignal(
                severity=(
                    SignalSeverity.CRITICAL
                    if slip_days > 30
                    else SignalSeverity.WARNING
                ),
                title="Forecast Schedule Slip",
                detail=(
                    f"Forecast end is {slip_days} day"
                    f"{'s' if slip_days != 1 else ''} later than planned."
                ),
                penalty=penalty,
                entity_type="Project",
                entity_ids=[project.id],
            )
        )

    score = max(0, score)
    if not signals:
        signals.append(
            HealthSignal(
                severity=SignalSeverity.POSITIVE,
                title="Delivery signals are stable",
                detail=(
                    "No blocked/overdue Action Item or forecast-slip penalties "
                    "are currently active."
                ),
            )
        )
    return _factor(
        "delivery",
        "Delivery",
        DELIVERY_WEIGHT,
        score,
        signals,
    )


def _raid_factor(memory: ProjectMemorySnapshot) -> HealthFactor:
    total = (
        len(memory.risks)
        + len(memory.assumptions)
        + len(memory.issues)
        + len(memory.dependencies)
    )
    if total == 0:
        return _unavailable_factor(
            "raid",
            "RAID",
            RAID_WEIGHT,
            "No Risks, Assumptions, Issues, or Dependencies are recorded yet.",
        )

    score = 100
    signals: list[HealthSignal] = []

    materialized = [
        item for item in memory.risks
        if item.status == RiskStatus.MATERIALIZED
    ]
    if materialized:
        penalty = min(40, 20 * len(materialized))
        score -= penalty
        signals.append(
            HealthSignal(
                severity=SignalSeverity.CRITICAL,
                title="Materialized Risks",
                detail=f"{len(materialized)} Risk(s) have materialized.",
                penalty=penalty,
                entity_type="Risk",
                entity_ids=[item.id for item in materialized[:10]],
            )
        )

    high_risks = [
        item for item in memory.risks
        if item.status in {RiskStatus.OPEN, RiskStatus.MITIGATING}
        and _severity_value(item.impact) >= 3
    ]
    if high_risks:
        penalty = min(25, 10 * len(high_risks))
        score -= penalty
        signals.append(
            HealthSignal(
                severity=SignalSeverity.WARNING,
                title="High-impact Open Risks",
                detail=f"{len(high_risks)} open/mitigating Risk(s) have high impact.",
                penalty=penalty,
                entity_type="Risk",
                entity_ids=[item.id for item in high_risks[:10]],
            )
        )

    blocked_issues = [
        item for item in memory.issues
        if item.status == IssueStatus.BLOCKED
    ]
    if blocked_issues:
        penalty = min(30, 15 * len(blocked_issues))
        score -= penalty
        signals.append(
            HealthSignal(
                severity=SignalSeverity.CRITICAL,
                title="Blocked Issues",
                detail=f"{len(blocked_issues)} Issue(s) are blocked.",
                penalty=penalty,
                entity_type="Issue",
                entity_ids=[item.id for item in blocked_issues[:10]],
            )
        )

    severe_issues = [
        item for item in memory.issues
        if item.status not in {IssueStatus.RESOLVED, IssueStatus.CLOSED}
        and _severity_value(item.severity) >= 3
    ]
    if severe_issues:
        penalty = min(25, 10 * len(severe_issues))
        score -= penalty
        signals.append(
            HealthSignal(
                severity=SignalSeverity.WARNING,
                title="High-severity Open Issues",
                detail=f"{len(severe_issues)} unresolved Issue(s) are high severity.",
                penalty=penalty,
                entity_type="Issue",
                entity_ids=[item.id for item in severe_issues[:10]],
            )
        )

    blocked_dependencies = [
        item for item in memory.dependencies
        if item.status == DependencyStatus.BLOCKED
    ]
    if blocked_dependencies:
        penalty = min(25, 12 * len(blocked_dependencies))
        score -= penalty
        signals.append(
            HealthSignal(
                severity=SignalSeverity.CRITICAL,
                title="Blocked Dependencies",
                detail=f"{len(blocked_dependencies)} Dependency record(s) are blocked.",
                penalty=penalty,
                entity_type="Dependency",
                entity_ids=[item.id for item in blocked_dependencies[:10]],
            )
        )

    invalidated = [
        item for item in memory.assumptions
        if item.status == AssumptionStatus.INVALIDATED
    ]
    if invalidated:
        penalty = min(15, 8 * len(invalidated))
        score -= penalty
        signals.append(
            HealthSignal(
                severity=SignalSeverity.WARNING,
                title="Invalidated Assumptions",
                detail=f"{len(invalidated)} Assumption(s) were invalidated.",
                penalty=penalty,
                entity_type="Assumption",
                entity_ids=[item.id for item in invalidated[:10]],
            )
        )

    score = max(0, score)
    if not signals:
        signals.append(
            HealthSignal(
                severity=SignalSeverity.POSITIVE,
                title="RAID signals are controlled",
                detail="No active critical RAID penalties are currently detected.",
            )
        )
    return _factor("raid", "RAID", RAID_WEIGHT, score, signals)


def _decisions_factor(
    memory: ProjectMemorySnapshot,
    as_of: date,
) -> HealthFactor:
    decisions = memory.decisions
    if not decisions:
        return _unavailable_factor(
            "decisions",
            "Decisions",
            DECISIONS_WEIGHT,
            "No governed Decision records are available yet.",
        )

    score = 100
    signals: list[HealthSignal] = []

    unresolved = [
        item for item in decisions
        if item.status in {
            DecisionStatus.PROPOSED,
            DecisionStatus.PENDING,
        }
    ]
    if unresolved:
        penalty = min(40, 10 * len(unresolved))
        score -= penalty
        signals.append(
            HealthSignal(
                severity=SignalSeverity.WARNING,
                title="Decision Debt",
                detail=(
                    f"{len(unresolved)} Decision(s) remain proposed or pending."
                ),
                penalty=penalty,
                entity_type="Decision",
                entity_ids=[item.id for item in unresolved[:10]],
            )
        )

    overdue_reviews = [
        item for item in decisions
        if item.review_date is not None
        and item.review_date < as_of
        and item.status
        not in {
            DecisionStatus.REJECTED,
            DecisionStatus.SUPERSEDED,
            DecisionStatus.REVERSED,
        }
    ]
    if overdue_reviews:
        penalty = min(30, 15 * len(overdue_reviews))
        score -= penalty
        signals.append(
            HealthSignal(
                severity=SignalSeverity.WARNING,
                title="Overdue Decision Reviews",
                detail=f"{len(overdue_reviews)} Decision review date(s) are overdue.",
                penalty=penalty,
                entity_type="Decision",
                entity_ids=[item.id for item in overdue_reviews[:10]],
            )
        )

    score = max(0, score)
    if not signals:
        approved = sum(
            item.status == DecisionStatus.APPROVED
            for item in decisions
        )
        signals.append(
            HealthSignal(
                severity=SignalSeverity.POSITIVE,
                title="Decision governance is current",
                detail=(
                    f"{approved} approved Decision(s); no pending-decision or "
                    "overdue-review penalty is active."
                ),
            )
        )
    return _factor(
        "decisions",
        "Decisions",
        DECISIONS_WEIGHT,
        score,
        signals,
    )


def _sources_factor(
    sources: SourcesWorkspaceSnapshot,
) -> HealthFactor:
    enabled = [item for item in sources.sources if item.is_enabled]
    if not enabled:
        reason = (
            "No enabled source connections are registered yet."
            if not sources.sources
            else "All registered source connections are disabled."
        )
        return _unavailable_factor(
            "sources",
            "Sources",
            SOURCES_WEIGHT,
            reason,
        )

    values = {
        SourceHealthStatus.HEALTHY: 100,
        SourceHealthStatus.ATTENTION: 65,
        SourceHealthStatus.FAILED: 20,
        SourceHealthStatus.NEVER_SYNCED: 45,
        SourceHealthStatus.DISABLED: 100,
    }
    score = round(
        sum(values[item.health] for item in enabled) / len(enabled)
    )
    signals: list[HealthSignal] = []

    failed = [item for item in enabled if item.health == SourceHealthStatus.FAILED]
    attention = [
        item for item in enabled if item.health == SourceHealthStatus.ATTENTION
    ]
    never_synced = [
        item for item in enabled if item.health == SourceHealthStatus.NEVER_SYNCED
    ]

    if failed:
        signals.append(
            HealthSignal(
                severity=SignalSeverity.CRITICAL,
                title="Failed Source Connections",
                detail=f"{len(failed)} enabled source connection(s) are failed.",
                penalty=min(80, 80 * len(failed) // len(enabled)),
                entity_type="SourceConnection",
                entity_ids=[item.id for item in failed[:10]],
            )
        )
    if attention:
        signals.append(
            HealthSignal(
                severity=SignalSeverity.WARNING,
                title="Sources Need Attention",
                detail=f"{len(attention)} source connection(s) need attention.",
                penalty=min(35, 35 * len(attention) // len(enabled)),
                entity_type="SourceConnection",
                entity_ids=[item.id for item in attention[:10]],
            )
        )
    if never_synced:
        signals.append(
            HealthSignal(
                severity=SignalSeverity.WARNING,
                title="Sources Never Synced",
                detail=f"{len(never_synced)} source connection(s) have never synced.",
                penalty=min(55, 55 * len(never_synced) // len(enabled)),
                entity_type="SourceConnection",
                entity_ids=[item.id for item in never_synced[:10]],
            )
        )
    if not signals:
        signals.append(
            HealthSignal(
                severity=SignalSeverity.POSITIVE,
                title="Sources are healthy",
                detail=f"All {len(enabled)} enabled source connection(s) are healthy.",
            )
        )

    return _factor(
        "sources",
        "Sources",
        SOURCES_WEIGHT,
        score,
        signals,
    )


def _severity_value(value: str | None) -> int:
    if value is None:
        return 0
    normalized = value.strip().casefold().replace("_", " ")
    if normalized in {"critical", "very high", "severe"}:
        return 4
    if normalized in {"high", "major"}:
        return 3
    if normalized in {"medium", "moderate"}:
        return 2
    if normalized in {"low", "minor"}:
        return 1
    return 0


def _factor(
    key: str,
    name: str,
    weight: int,
    score: int,
    signals: list[HealthSignal],
) -> HealthFactor:
    bounded = max(0, min(100, floor(score)))
    return HealthFactor(
        key=key,
        name=name,
        weight=weight,
        available=True,
        score=bounded,
        band=score_band(bounded),
        signals=signals,
    )


def _unavailable_factor(
    key: str,
    name: str,
    weight: int,
    detail: str,
) -> HealthFactor:
    return HealthFactor(
        key=key,
        name=name,
        weight=weight,
        available=False,
        score=None,
        band=HealthBand.INSUFFICIENT_DATA,
        signals=[
            HealthSignal(
                severity=SignalSeverity.INFO,
                title=f"{name} data unavailable",
                detail=detail,
            )
        ],
    )


def _overall_explanation(
    score: int,
    band: HealthBand,
    coverage: int,
) -> str:
    if band == HealthBand.INSUFFICIENT_DATA:
        return (
            f"Provisional score {score}/100, but only {coverage}% of the health "
            "model has governed data. Treat the result as insufficiently covered."
        )
    return (
        f"Project Health is {band.value.upper()} at {score}/100 using "
        f"{coverage}% of the explainable V0 health model."
    )
