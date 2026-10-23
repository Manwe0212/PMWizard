"""Durable Project Health snapshots and deterministic trend analysis."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from hashlib import sha256
import json
from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from pmwizard.persistence.orm import ProjectHealthSnapshotORM, ProjectORM

from .history_schemas import (
    HealthHistoryPoint,
    HealthSnapshotCaptureResponse,
    HealthTrendSummary,
    ProjectHealthHistory,
    TrendDirection,
)
from .schemas import HealthSignal, ProjectHealthSnapshot
from .service import ProjectHealthService


MODEL_VERSION = "project-health-v0"
DEDUPLICATION_WINDOW = timedelta(minutes=5)
TREND_THRESHOLD = 3


class ProjectHealthHistoryService:
    def __init__(self, session: Session) -> None:
        self.session = session

    def capture(
        self,
        *,
        tenant_id: UUID,
        project_id: UUID,
        captured_by: UUID | None,
        capture_source: str = "manual",
        captured_at: datetime | None = None,
    ) -> HealthSnapshotCaptureResponse:
        timestamp = captured_at or datetime.now(timezone.utc)
        current = ProjectHealthService(self.session).snapshot(
            tenant_id=tenant_id,
            project_id=project_id,
            as_of=timestamp.date(),
        )
        fingerprint = self._fingerprint(current)
        latest = self._latest_row(tenant_id, project_id)

        if (
            latest is not None
            and latest.state_fingerprint == fingerprint
            and self._elapsed(timestamp, latest.captured_at) <= DEDUPLICATION_WINDOW
        ):
            return HealthSnapshotCaptureResponse(
                created=False,
                snapshot=self._point(latest),
            )

        row = ProjectHealthSnapshotORM(
            id=uuid4(),
            tenant_id=tenant_id,
            project_id=project_id,
            captured_at=timestamp,
            captured_by=captured_by,
            capture_source=capture_source,
            model_version=MODEL_VERSION,
            score=current.score,
            band=current.band.value,
            coverage_percent=current.coverage_percent,
            coverage_band=current.coverage_band.value,
            available_weight=current.available_weight,
            factor_scores={
                factor.key: factor.score
                for factor in current.factors
            },
            key_drivers=[
                driver.model_dump(mode="json")
                for driver in current.key_drivers
            ],
            snapshot_payload=current.model_dump(mode="json"),
            state_fingerprint=fingerprint,
            created_at=datetime.now(timezone.utc),
        )
        self.session.add(row)
        self.session.commit()
        self.session.refresh(row)

        return HealthSnapshotCaptureResponse(
            created=True,
            snapshot=self._point(row),
        )

    def history(
        self,
        *,
        tenant_id: UUID,
        project_id: UUID,
        limit: int = 90,
    ) -> ProjectHealthHistory:
        if type(limit) is not int or limit < 2 or limit > 365:
            raise ValueError("limit must be an integer between 2 and 365")
        self._require_project(tenant_id, project_id)

        rows = list(
            self.session.scalars(
                select(ProjectHealthSnapshotORM)
                .where(
                    ProjectHealthSnapshotORM.tenant_id == tenant_id,
                    ProjectHealthSnapshotORM.project_id == project_id,
                )
                .order_by(
                    ProjectHealthSnapshotORM.captured_at.desc(),
                    ProjectHealthSnapshotORM.created_at.desc(),
                )
                .limit(limit)
            ).all()
        )
        rows.reverse()
        points = [self._point(row) for row in rows]

        return ProjectHealthHistory(
            project_id=project_id,
            count=len(points),
            points=points,
            trend=self._trend(points),
        )

    def _require_project(self, tenant_id: UUID, project_id: UUID) -> None:
        exists = self.session.scalar(
            select(ProjectORM.id).where(
                ProjectORM.tenant_id == tenant_id,
                ProjectORM.id == project_id,
            )
        )
        if exists is None:
            raise LookupError("Project not found for tenant")

    def _latest_row(
        self,
        tenant_id: UUID,
        project_id: UUID,
    ) -> ProjectHealthSnapshotORM | None:
        return self.session.scalar(
            select(ProjectHealthSnapshotORM)
            .where(
                ProjectHealthSnapshotORM.tenant_id == tenant_id,
                ProjectHealthSnapshotORM.project_id == project_id,
            )
            .order_by(
                ProjectHealthSnapshotORM.captured_at.desc(),
                ProjectHealthSnapshotORM.created_at.desc(),
            )
            .limit(1)
        )

    @staticmethod
    def _point(row: ProjectHealthSnapshotORM) -> HealthHistoryPoint:
        return HealthHistoryPoint(
            id=row.id,
            captured_at=row.captured_at,
            captured_by=row.captured_by,
            capture_source=row.capture_source,
            model_version=row.model_version,
            score=row.score,
            band=row.band,
            coverage_percent=row.coverage_percent,
            coverage_band=row.coverage_band,
            factor_scores=row.factor_scores,
            key_drivers=[
                HealthSignal.model_validate(item)
                for item in row.key_drivers
            ],
        )

    @staticmethod
    def _fingerprint(snapshot: ProjectHealthSnapshot) -> str:
        payload = json.dumps(
            snapshot.model_dump(mode="json"),
            sort_keys=True,
            separators=(",", ":"),
        )
        return sha256(payload.encode("utf-8")).hexdigest()

    @staticmethod
    def _elapsed(later: datetime, earlier: datetime) -> timedelta:
        if earlier.tzinfo is None:
            earlier = earlier.replace(tzinfo=timezone.utc)
        if later.tzinfo is None:
            later = later.replace(tzinfo=timezone.utc)
        return later - earlier

    @classmethod
    def _trend(
        cls,
        points: list[HealthHistoryPoint],
    ) -> HealthTrendSummary:
        if len(points) < 2:
            return HealthTrendSummary(
                direction=TrendDirection.INSUFFICIENT_HISTORY,
                explanation=(
                    "At least two captured health snapshots are required "
                    "to determine a trend."
                ),
            )

        previous = points[-2]
        latest = points[-1]
        elapsed = cls._elapsed(latest.captured_at, previous.captured_at)
        coverage_delta = (
            latest.coverage_percent - previous.coverage_percent
        )

        factor_deltas = {
            key: latest.factor_scores[key] - previous.factor_scores[key]
            for key in latest.factor_scores.keys() & previous.factor_scores.keys()
            if latest.factor_scores[key] is not None
            and previous.factor_scores[key] is not None
        }

        previous_drivers = {
            driver.title for driver in previous.key_drivers
            if driver.penalty > 0
        }
        latest_drivers = {
            driver.title for driver in latest.key_drivers
            if driver.penalty > 0
        }

        if previous.score is None or latest.score is None:
            return HealthTrendSummary(
                direction=TrendDirection.INSUFFICIENT_HISTORY,
                from_snapshot_id=previous.id,
                to_snapshot_id=latest.id,
                score_delta=None,
                coverage_delta=coverage_delta,
                factor_deltas=factor_deltas,
                new_drivers=sorted(latest_drivers - previous_drivers),
                resolved_drivers=sorted(previous_drivers - latest_drivers),
                elapsed_hours=round(elapsed.total_seconds() / 3600, 2),
                explanation=(
                    "The two latest snapshots cannot be compared numerically "
                    "because at least one has no health score."
                ),
            )

        score_delta = latest.score - previous.score
        if score_delta >= TREND_THRESHOLD:
            direction = TrendDirection.IMPROVING
        elif score_delta <= -TREND_THRESHOLD:
            direction = TrendDirection.DETERIORATING
        else:
            direction = TrendDirection.STABLE

        return HealthTrendSummary(
            direction=direction,
            from_snapshot_id=previous.id,
            to_snapshot_id=latest.id,
            score_delta=score_delta,
            coverage_delta=coverage_delta,
            factor_deltas=factor_deltas,
            new_drivers=sorted(latest_drivers - previous_drivers),
            resolved_drivers=sorted(previous_drivers - latest_drivers),
            elapsed_hours=round(elapsed.total_seconds() / 3600, 2),
            explanation=cls._trend_explanation(
                direction,
                score_delta,
                coverage_delta,
            ),
        )

    @staticmethod
    def _trend_explanation(
        direction: TrendDirection,
        score_delta: int,
        coverage_delta: int,
    ) -> str:
        direction_text = {
            TrendDirection.IMPROVING: "improving",
            TrendDirection.STABLE: "stable",
            TrendDirection.DETERIORATING: "deteriorating",
        }[direction]
        score_text = (
            f"+{score_delta}" if score_delta > 0 else str(score_delta)
        )
        coverage_text = (
            f"+{coverage_delta}" if coverage_delta > 0 else str(coverage_delta)
        )
        return (
            f"Project Health is {direction_text}: score delta {score_text} "
            f"and coverage delta {coverage_text} percentage point(s) "
            "between the two latest snapshots."
        )
