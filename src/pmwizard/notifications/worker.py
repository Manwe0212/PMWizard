"""Background delivery of Attention Center signals."""

from __future__ import annotations

import os
from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from pmwizard.attention import (
    AttentionCategory,
    AttentionCenterService,
    AttentionSeverity,
    AttentionUserState,
)
from pmwizard.persistence.orm import NotificationPreferenceORM, ProjectORM

from .contracts import (
    EmailNotificationProvider,
    TeamsNotificationProvider,
)
from .repository import NotificationRepository
from .schemas import (
    NotificationChannel,
    NotificationDeliveryStatus,
)


_SEVERITY_RANK = {
    AttentionSeverity.INFO: 1,
    AttentionSeverity.WARNING: 2,
    AttentionSeverity.CRITICAL: 3,
}


class NotificationDeliveryWorker:
    def __init__(
        self,
        session_factory: sessionmaker,
        *,
        worker_id: str,
        email_provider: EmailNotificationProvider | None = None,
        teams_provider: TeamsNotificationProvider | None = None,
        lease_seconds: int = 120,
        batch_size: int = 10,
        public_base_url: str | None = None,
    ) -> None:
        self.session_factory = session_factory
        self.worker_id = worker_id
        self.email_provider = email_provider
        self.teams_provider = teams_provider
        self.lease_seconds = lease_seconds
        self.batch_size = batch_size
        self.public_base_url = (
            public_base_url.strip().rstrip("/")
            if public_base_url and public_base_url.strip()
            else None
        )

    def run_once(self, *, now: datetime | None = None) -> int:
        timestamp = self._aware(now or datetime.now(timezone.utc))
        with self.session_factory() as session:
            claims = NotificationRepository(session).claim_due(
                worker_id=self.worker_id,
                now=timestamp,
                lease_seconds=self.lease_seconds,
                limit=self.batch_size,
            )

        processed = 0
        for claim in claims:
            with self.session_factory() as session:
                repository = NotificationRepository(session)
                try:
                    preference = session.get(
                        NotificationPreferenceORM,
                        claim.preference_id,
                    )
                    if preference is None or not preference.is_enabled:
                        repository.finish_claim(claim=claim, now=timestamp)
                        processed += 1
                        continue

                    user, membership = repository.require_user_project(
                        tenant_id=claim.tenant_id,
                        user_id=claim.user_id,
                        project_id=claim.project_id,
                    )
                    permissions = set(membership.permissions or [])
                    if "project:read" not in permissions:
                        repository.finish_claim(claim=claim, now=timestamp)
                        processed += 1
                        continue

                    snapshot = AttentionCenterService(session).snapshot(
                        tenant_id=claim.tenant_id,
                        user_id=claim.user_id,
                        project_id=claim.project_id,
                        permissions=permissions,
                        now=timestamp,
                    )
                    signals = self._eligible_signals(snapshot.signals, preference)
                    project_name = session.scalar(
                        select(ProjectORM.name).where(
                            ProjectORM.tenant_id == claim.tenant_id,
                            ProjectORM.id == claim.project_id,
                        )
                    ) or "Project"

                    if preference.email_enabled:
                        self._deliver_email(
                            repository=repository,
                            preference=preference,
                            tenant_id=claim.tenant_id,
                            user_id=claim.user_id,
                            project_id=claim.project_id,
                            user_email=user.email,
                            project_name=project_name,
                            signals=signals,
                            now=timestamp,
                        )

                    if preference.teams_enabled:
                        self._deliver_teams(
                            repository=repository,
                            preference=preference,
                            tenant_id=claim.tenant_id,
                            user_id=claim.user_id,
                            project_id=claim.project_id,
                            project_name=project_name,
                            signals=signals,
                            now=timestamp,
                        )

                    repository.finish_claim(claim=claim, now=timestamp)
                    processed += 1
                except Exception:
                    # Let the expiring lease make the preference retryable.
                    # Provider-specific failures are caught and persisted below.
                    continue
        return processed

    def _eligible_signals(self, signals, preference) -> list:
        minimum = AttentionSeverity(preference.minimum_severity)
        categories = {
            AttentionCategory(item)
            for item in (preference.categories or [])
        }
        return [
            signal
            for signal in signals
            if signal.state == AttentionUserState.UNREAD
            and signal.category in categories
            and _SEVERITY_RANK[signal.severity] >= _SEVERITY_RANK[minimum]
        ][:20]

    def _deliver_email(
        self,
        *,
        repository: NotificationRepository,
        preference,
        tenant_id: UUID,
        user_id: UUID,
        project_id: UUID,
        user_email: str,
        project_name: str,
        signals: list,
        now: datetime,
    ) -> None:
        delivered = repository.successful_signal_ids(
            tenant_id=tenant_id,
            user_id=user_id,
            project_id=project_id,
            channel=NotificationChannel.EMAIL,
        )
        pending = [item for item in signals if item.id not in delivered]
        if not pending:
            return

        ids = [item.id for item in pending]
        if self.email_provider is None:
            repository.record_delivery(
                tenant_id=tenant_id,
                preference_id=preference.id,
                user_id=user_id,
                project_id=project_id,
                channel=NotificationChannel.EMAIL,
                status=NotificationDeliveryStatus.FAILED,
                signal_ids=ids,
                attempted_at=now,
                error_message="Email notification transport is not configured.",
            )
            return

        subject = (
            f"[PMWizard] {len(pending)} attention signal"
            f"{'' if len(pending) == 1 else 's'} — {project_name}"
        )
        text = self._message(project_name, pending)
        try:
            self.email_provider.send(
                to_email=user_email,
                subject=subject,
                text=text,
            )
            status = NotificationDeliveryStatus.SUCCESS
            error = None
        except Exception as exc:
            status = NotificationDeliveryStatus.FAILED
            error = self._safe_provider_error(exc, "Email notification delivery failed.")

        repository.record_delivery(
            tenant_id=tenant_id,
            preference_id=preference.id,
            user_id=user_id,
            project_id=project_id,
            channel=NotificationChannel.EMAIL,
            status=status,
            signal_ids=ids,
            attempted_at=now,
            error_message=error,
        )

    def _deliver_teams(
        self,
        *,
        repository: NotificationRepository,
        preference,
        tenant_id: UUID,
        user_id: UUID,
        project_id: UUID,
        project_name: str,
        signals: list,
        now: datetime,
    ) -> None:
        delivered = repository.successful_signal_ids(
            tenant_id=tenant_id,
            user_id=user_id,
            project_id=project_id,
            channel=NotificationChannel.TEAMS,
        )
        pending = [item for item in signals if item.id not in delivered]
        if not pending:
            return

        ids = [item.id for item in pending]
        if self.teams_provider is None or not preference.teams_webhook_ref:
            repository.record_delivery(
                tenant_id=tenant_id,
                preference_id=preference.id,
                user_id=user_id,
                project_id=project_id,
                channel=NotificationChannel.TEAMS,
                status=NotificationDeliveryStatus.FAILED,
                signal_ids=ids,
                attempted_at=now,
                error_message="Microsoft Teams notification transport is not configured.",
            )
            return

        title = (
            f"PMWizard · {project_name} · {len(pending)} attention signal"
            f"{'' if len(pending) == 1 else 's'}"
        )
        text = self._message(project_name, pending)
        try:
            self.teams_provider.send(
                webhook_reference=preference.teams_webhook_ref,
                title=title,
                text=text,
            )
            status = NotificationDeliveryStatus.SUCCESS
            error = None
        except Exception as exc:
            status = NotificationDeliveryStatus.FAILED
            error = self._safe_provider_error(
                exc,
                "Microsoft Teams notification delivery failed.",
            )

        repository.record_delivery(
            tenant_id=tenant_id,
            preference_id=preference.id,
            user_id=user_id,
            project_id=project_id,
            channel=NotificationChannel.TEAMS,
            status=status,
            signal_ids=ids,
            attempted_at=now,
            error_message=error,
        )

    def _message(self, project_name: str, signals: list) -> str:
        lines = [
            f"PMWizard attention summary for {project_name}",
            "",
        ]
        for signal in signals:
            lines.extend(
                [
                    f"[{signal.severity.value.upper()}] {signal.title}",
                    signal.detail,
                    "",
                ]
            )
        if self.public_base_url:
            lines.extend(
                [
                    f"Open PMWizard: {self.public_base_url}",
                    "",
                ]
            )
        lines.append(
            "Delivery does not acknowledge or resolve these signals. "
            "Open PMWizard to review governed project state."
        )
        return "\n".join(lines)

    @staticmethod
    def _safe_provider_error(exc: Exception, fallback: str) -> str:
        message = str(exc).strip()
        if message in {
            "Email notification delivery failed.",
            "Email notification credential provider is unavailable.",
            "Email notification credential is invalid or unavailable.",
            "Microsoft Teams notification delivery failed.",
        }:
            return message
        return fallback

    @staticmethod
    def _aware(value: datetime) -> datetime:
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value


def public_base_url_from_environment() -> str | None:
    return os.getenv("PMWIZARD_PUBLIC_BASE_URL", "").strip() or None
