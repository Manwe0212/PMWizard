"""Runtime contracts for notification delivery."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol
from uuid import UUID


@dataclass(frozen=True)
class NotificationPreferenceClaim:
    preference_id: UUID
    tenant_id: UUID
    user_id: UUID
    project_id: UUID
    lease_token: str


class EmailNotificationProvider(Protocol):
    def send(
        self,
        *,
        to_email: str,
        subject: str,
        text: str,
    ) -> None: ...


class TeamsNotificationProvider(Protocol):
    def send(
        self,
        *,
        webhook_reference: str,
        title: str,
        text: str,
    ) -> None: ...
