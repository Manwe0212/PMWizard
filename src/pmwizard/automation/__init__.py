"""Durable Automation & Scheduler V0."""

from .contracts import AutomationClaim, AutomationHandler
from .executor import AutomationExecutor
from .handlers import HealthSnapshotAutomationHandler
from .repository import AutomationRepository
from .schemas import (
    AutomationRunStatus,
    AutomationRunView,
    AutomationScheduleView,
    AutomationsSummary,
    AutomationsWorkspaceSnapshot,
    AutomationTaskType,
    AutomationTrigger,
    CreateAutomationScheduleRequest,
    RunNowResponse,
    UpdateAutomationScheduleRequest,
)
from .service import AutomationScheduleService
from .worker import AutomationWorker

__all__ = [
    "AutomationClaim",
    "AutomationExecutor",
    "AutomationHandler",
    "AutomationRepository",
    "AutomationRunStatus",
    "AutomationRunView",
    "AutomationScheduleService",
    "AutomationScheduleView",
    "AutomationsSummary",
    "AutomationsWorkspaceSnapshot",
    "AutomationTaskType",
    "AutomationTrigger",
    "AutomationWorker",
    "CreateAutomationScheduleRequest",
    "HealthSnapshotAutomationHandler",
    "RunNowResponse",
    "UpdateAutomationScheduleRequest",
]
