"""Notification Delivery & Preferences V0 schemas."""

from __future__ import annotations

import re
from datetime import datetime
from enum import StrEnum
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from pmwizard.attention import AttentionCategory, AttentionSeverity


_TEAMS_REF = re.compile(r"^env:TEAMS_[A-Z0-9_]{1,58}$")


class NotificationChannel(StrEnum):
    EMAIL = "email"
    TEAMS = "teams"


class NotificationDeliveryStatus(StrEnum):
    SUCCESS = "success"
    FAILED = "failed"


class NotificationPreferenceCommand(BaseModel):
    model_config = ConfigDict(extra="forbid")

    enabled: bool = False
    email_enabled: bool = False
    teams_enabled: bool = False
    teams_webhook_ref: str | None = Field(default=None, max_length=100)
    clear_teams_webhook: bool = False
    minimum_severity: AttentionSeverity = AttentionSeverity.WARNING
    categories: list[AttentionCategory] = Field(
        default_factory=lambda: list(AttentionCategory),
        min_length=1,
    )
    interval_minutes: int = Field(default=60, ge=15, le=10080)

    @field_validator("teams_webhook_ref")
    @classmethod
    def _validate_teams_ref(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = value.strip()
        if not _TEAMS_REF.fullmatch(value):
            raise ValueError(
                "teams_webhook_ref must use env:TEAMS_ALIAS with uppercase "
                "letters, digits, or underscores"
            )
        return value

    @field_validator("categories")
    @classmethod
    def _deduplicate_categories(
        cls,
        values: list[AttentionCategory],
    ) -> list[AttentionCategory]:
        result: list[AttentionCategory] = []
        for item in values:
            if item not in result:
                result.append(item)
        return result

    @model_validator(mode="after")
    def _validate_channel_selection(self):
        if self.enabled and not (self.email_enabled or self.teams_enabled):
            raise ValueError(
                "Enable at least one delivery channel before enabling notifications."
            )
        if self.clear_teams_webhook and self.teams_webhook_ref is not None:
            raise ValueError(
                "teams_webhook_ref and clear_teams_webhook cannot be used together."
            )
        return self


class NotificationPreferenceView(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: UUID | None = None
    project_id: UUID
    enabled: bool
    email_enabled: bool
    email_destination: str
    teams_enabled: bool
    teams_webhook_configured: bool
    minimum_severity: AttentionSeverity
    categories: list[AttentionCategory]
    interval_minutes: int
    next_delivery_at: datetime
    last_delivery_at: datetime | None = None
    created_at: datetime
    updated_at: datetime


class NotificationDeliveryView(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: UUID
    project_id: UUID
    channel: NotificationChannel
    status: NotificationDeliveryStatus
    signal_count: int
    signal_ids: list[str]
    attempted_at: datetime
    delivered_at: datetime | None = None
    error_message: str | None = None


class NotificationWorkspaceSnapshot(BaseModel):
    model_config = ConfigDict(extra="forbid")

    project_id: UUID
    generated_at: datetime
    preference: NotificationPreferenceView
    recent_deliveries: list[NotificationDeliveryView] = Field(default_factory=list)
