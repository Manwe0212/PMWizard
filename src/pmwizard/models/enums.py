"""Shared canonical enums for PMWizard domain models."""

from enum import StrEnum


class OriginType(StrEnum):
    HUMAN = "human"
    INTEGRATION = "integration"
    AI = "ai"


class ReviewStatus(StrEnum):
    PENDING = "pending"
    ACCEPTED = "accepted"
    EDITED = "edited"
    REJECTED = "rejected"
    DEFERRED = "deferred"


class ActionItemStatus(StrEnum):
    NOT_STARTED = "not_started"
    IN_PROGRESS = "in_progress"
    BLOCKED = "blocked"
    PENDING_EXTERNAL = "pending_external"
    READY_FOR_REVIEW = "ready_for_review"
    COMPLETED = "completed"
    CANCELLED = "cancelled"


class RiskStatus(StrEnum):
    OPEN = "open"
    MITIGATING = "mitigating"
    MATERIALIZED = "materialized"
    CLOSED = "closed"


class AssumptionStatus(StrEnum):
    OPEN = "open"
    VALIDATED = "validated"
    INVALIDATED = "invalidated"
    CONVERTED = "converted"
    CLOSED = "closed"


class IssueStatus(StrEnum):
    OPEN = "open"
    IN_PROGRESS = "in_progress"
    BLOCKED = "blocked"
    RESOLVED = "resolved"
    CLOSED = "closed"


class DependencyStatus(StrEnum):
    OPEN = "open"
    SATISFIED = "satisfied"
    BLOCKED = "blocked"
    WAIVED = "waived"
    CLOSED = "closed"


class DecisionStatus(StrEnum):
    PROPOSED = "proposed"
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    SUPERSEDED = "superseded"
    REVERSED = "reversed"


class SuggestionType(StrEnum):
    NEW_ACTION_ITEM = "new_action_item"
    ACTION_PROGRESS = "action_progress"
    NEW_RISK = "new_risk"
    NEW_ASSUMPTION = "new_assumption"
    NEW_ISSUE = "new_issue"
    NEW_DEPENDENCY = "new_dependency"
    NEW_DECISION = "new_decision"
    RAID_UPDATE = "raid_update"
    CONTRADICTION = "contradiction"
    RELATIONSHIP = "relationship"
