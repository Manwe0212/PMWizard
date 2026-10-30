"""Outbound notification delivery built on Attention Center signals."""

from .contracts import (
    EmailNotificationProvider,
    NotificationPreferenceClaim,
    TeamsNotificationProvider,
)
from .providers import (
    NotificationDeliveryError,
    SmtpEmailNotificationProvider,
    TeamsWebhookNotificationProvider,
)
from .repository import NotificationRepository
from .schemas import (
    NotificationChannel,
    NotificationDeliveryStatus,
    NotificationDeliveryView,
    NotificationPreferenceCommand,
    NotificationPreferenceView,
    NotificationWorkspaceSnapshot,
)
from .service import NotificationPreferenceService
from .worker import NotificationDeliveryWorker, public_base_url_from_environment

__all__ = [
    "EmailNotificationProvider",
    "NotificationChannel",
    "NotificationDeliveryError",
    "NotificationDeliveryStatus",
    "NotificationDeliveryView",
    "NotificationDeliveryWorker",
    "NotificationPreferenceClaim",
    "NotificationPreferenceCommand",
    "NotificationPreferenceService",
    "NotificationPreferenceView",
    "NotificationRepository",
    "NotificationWorkspaceSnapshot",
    "SmtpEmailNotificationProvider",
    "TeamsNotificationProvider",
    "TeamsWebhookNotificationProvider",
    "public_base_url_from_environment",
]
