"""Deterministic Action Item progress classification for PMWizard V0.

V0 deliberately uses explicit lexical signals. It does not use an LLM and it
never mutates governed project state.
"""

from __future__ import annotations

import re
import unicodedata
from enum import StrEnum
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from pmwizard.models import ActionItem, Evidence
from pmwizard.models.enums import ActionItemStatus


class ProgressOutcome(StrEnum):
    NO_SIGNAL = "no_signal"
    PROGRESS_UPDATE = "progress_update"
    STATUS_CHANGE = "status_change"
    AMBIGUOUS = "ambiguous"


class ProgressSignal(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: ActionItemStatus
    phrase: str
    confidence: float = Field(ge=0.0, le=1.0)


class ProgressAssessment(BaseModel):
    model_config = ConfigDict(extra="forbid")

    outcome: ProgressOutcome
    action_item_id: UUID
    current_status: ActionItemStatus
    suggested_status: ActionItemStatus | None = None
    confidence: float = Field(ge=0.0, le=1.0)
    signals: list[ProgressSignal] = Field(default_factory=list)
    reason: str
    progress_summary: str | None = None


def _normalize(value: str) -> str:
    value = unicodedata.normalize("NFKD", value)
    value = "".join(char for char in value if not unicodedata.combining(char))
    value = value.lower()
    value = re.sub(r"\s+", " ", value)
    return value.strip()


_SIGNAL_PATTERNS: dict[ActionItemStatus, tuple[tuple[str, float], ...]] = {
    ActionItemStatus.COMPLETED: (
        ("completed", 0.95),
        ("is complete", 0.95),
        ("done", 0.94),
        ("finished", 0.94),
        ("resolved", 0.92),
        ("successfully verified", 0.94),
        ("verified and working", 0.95),
        ("validated and working", 0.95),
        ("completado", 0.95),
        ("finalizado", 0.94),
        ("terminado", 0.94),
        ("resuelto", 0.92),
        ("verificado y funcionando", 0.95),
        ("validado y funcionando", 0.95),
    ),
    ActionItemStatus.BLOCKED: (
        ("blocked", 0.96),
        ("cannot proceed", 0.96),
        ("can't proceed", 0.96),
        ("unable to proceed", 0.95),
        ("stuck", 0.91),
        ("bloqueado", 0.96),
        ("no podemos avanzar", 0.96),
        ("no puede avanzar", 0.96),
        ("sin poder avanzar", 0.94),
    ),
    ActionItemStatus.PENDING_EXTERNAL: (
        ("waiting for", 0.92),
        ("waiting on", 0.92),
        ("awaiting", 0.92),
        ("pending from", 0.90),
        ("pending with", 0.90),
        ("esperando", 0.91),
        ("pendiente de", 0.91),
        ("a la espera de", 0.92),
    ),
    ActionItemStatus.READY_FOR_REVIEW: (
        ("ready for review", 0.94),
        ("submitted for review", 0.93),
        ("ready to review", 0.91),
        ("listo para revision", 0.94),
        ("enviado para revision", 0.93),
    ),
    ActionItemStatus.IN_PROGRESS: (
        ("in progress", 0.86),
        ("working on", 0.86),
        ("underway", 0.84),
        ("started", 0.80),
        ("progressing", 0.82),
        ("en progreso", 0.86),
        ("trabajando en", 0.86),
        ("en curso", 0.84),
        ("iniciado", 0.80),
        ("avanzando", 0.82),
    ),
}

_NEGATED_COMPLETION_PATTERNS: tuple[str, ...] = (
    "not complete",
    "not completed",
    "not done",
    "not finished",
    "isn't complete",
    "is not complete",
    "no esta completado",
    "no esta completo",
    "no completado",
    "sin completar",
    "aun no termina",
    "todavia no termina",
)


class ActionItemProgressClassifier:
    """Classify explicit progress signals in Evidence."""

    def assess(self, action: ActionItem, evidence: Evidence) -> ProgressAssessment:
        if action.project_id != evidence.project_id:
            raise ValueError("Action Item and Evidence must belong to the same project")

        text = _normalize(evidence.content_excerpt or "")
        if not text:
            return ProgressAssessment(
                outcome=ProgressOutcome.NO_SIGNAL,
                action_item_id=action.id,
                current_status=action.status,
                confidence=0.0,
                reason="Evidence contains no text to classify.",
            )

        signals: list[ProgressSignal] = []

        completion_negated = any(
            phrase in text for phrase in _NEGATED_COMPLETION_PATTERNS
        )

        for status, patterns in _SIGNAL_PATTERNS.items():
            if status == ActionItemStatus.COMPLETED and completion_negated:
                continue
            for phrase, confidence in patterns:
                if phrase in text:
                    signals.append(
                        ProgressSignal(
                            status=status,
                            phrase=phrase,
                            confidence=confidence,
                        )
                    )

        if completion_negated:
            signals.append(
                ProgressSignal(
                    status=ActionItemStatus.IN_PROGRESS,
                    phrase="completion explicitly negated",
                    confidence=0.88,
                )
            )

        if not signals:
            return ProgressAssessment(
                outcome=ProgressOutcome.NO_SIGNAL,
                action_item_id=action.id,
                current_status=action.status,
                confidence=0.0,
                reason=(
                    "No explicit V0 progress-status signal was found. "
                    "PMWizard should not invent a status update."
                ),
                progress_summary=evidence.content_excerpt,
            )

        by_status: dict[ActionItemStatus, list[ProgressSignal]] = {}
        for signal in signals:
            by_status.setdefault(signal.status, []).append(signal)

        if len(by_status) > 1:
            ordered = sorted(
                by_status.items(),
                key=lambda item: max(signal.confidence for signal in item[1]),
                reverse=True,
            )
            statuses = ", ".join(status.value for status, _ in ordered)
            return ProgressAssessment(
                outcome=ProgressOutcome.AMBIGUOUS,
                action_item_id=action.id,
                current_status=action.status,
                confidence=max(signal.confidence for signal in signals),
                signals=signals,
                reason=(
                    "Evidence contains conflicting explicit status signals "
                    f"({statuses}); human interpretation is required."
                ),
                progress_summary=evidence.content_excerpt,
            )

        suggested_status, status_signals = next(iter(by_status.items()))
        confidence = max(signal.confidence for signal in status_signals)

        if suggested_status == action.status:
            outcome = ProgressOutcome.PROGRESS_UPDATE
            reason = (
                f"Evidence reinforces the current '{action.status.value}' state "
                "and can be used as a new progress update."
            )
        else:
            outcome = ProgressOutcome.STATUS_CHANGE
            reason = (
                f"Evidence explicitly suggests changing Action Item status from "
                f"'{action.status.value}' to '{suggested_status.value}'."
            )

        return ProgressAssessment(
            outcome=outcome,
            action_item_id=action.id,
            current_status=action.status,
            suggested_status=suggested_status,
            confidence=confidence,
            signals=status_signals,
            reason=reason,
            progress_summary=evidence.content_excerpt,
        )
