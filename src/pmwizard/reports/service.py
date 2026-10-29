"""Grounded AI Status Report generation and validation."""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy.orm import Session

from pmwizard.ai import AIProviderError, StructuredGenerationProvider

from .grounding import StatusReportGroundingService
from .schemas import (
    ReportStatement,
    StatusReportAudience,
    StatusReportContent,
    StatusReportDraft,
    StatusReportRequest,
    StatusReportValidation,
)


class UngroundedStatusReportError(ValueError):
    """Raised when generated report content is not supported by its citations."""


class StatusReportGeneratorService:
    def __init__(
        self,
        session: Session,
        provider: StructuredGenerationProvider,
    ) -> None:
        self.session = session
        self.provider = provider

    def generate(
        self,
        *,
        tenant_id: UUID,
        project_id: UUID,
        command: StatusReportRequest,
        permissions: set[str],
        as_of: datetime | None = None,
    ) -> StatusReportDraft:
        timestamp = as_of or datetime.now(timezone.utc)
        packet = StatusReportGroundingService(self.session).build(
            tenant_id=tenant_id,
            project_id=project_id,
            lookback_days=command.lookback_days,
            permissions=permissions,
            as_of=timestamp,
        )

        content = self.provider.generate(
            instructions=self._instructions(command.audience),
            input_text=self._input(packet.model_dump(mode="json")),
            output_type=StatusReportContent,
        )
        validation = self._validate(content, packet.facts)

        return StatusReportDraft(
            project_id=packet.project_id,
            project_name=packet.project_name,
            title=(
                f"{packet.project_name} — "
                f"{command.lookback_days}-Day Status Report"
            ),
            audience=command.audience,
            period_start=packet.period_start,
            period_end=packet.period_end,
            generated_at=timestamp,
            provider=self.provider.provider_name,
            model=self.provider.model_name,
            health_score=packet.health_score,
            health_band=packet.health_band,
            health_coverage_percent=packet.health_coverage_percent,
            trend_direction=packet.trend_direction,
            trend_score_delta=packet.trend_score_delta,
            content=content,
            facts=packet.facts,
            validation=validation,
        )

    @staticmethod
    def _instructions(audience: StatusReportAudience) -> str:
        audience_text = (
            "senior executives and sponsors"
            if audience == StatusReportAudience.EXECUTIVE
            else "the project delivery team"
        )
        return (
            "You are PMWizard's grounded status-report drafting layer. "
            f"Write for {audience_text}. "
            "Use ONLY facts from the provided Grounding Packet. "
            "Do not invent dates, metrics, causes, owners, commitments, "
            "recommendations, accomplishments, risks, or decisions. "
            "Every statement MUST cite one or more exact fact_id values that "
            "directly support the wording. If the packet does not support a "
            "section, return an empty list for that section. "
            "Do not treat pending AI suggestions as project truth. "
            "Do not change the meaning of Health or Trend values. "
            "Keep language concise, professional, and decision-oriented. "
            "Do not write markdown; return only the requested structured output."
        )

    @staticmethod
    def _input(packet: dict) -> str:
        return (
            "Create a status-report draft from this Grounding Packet. "
            "The packet is authoritative for reportable facts:\n"
            + json.dumps(packet, sort_keys=True, indent=2, default=str)
        )

    @classmethod
    def _validate(
        cls,
        content: StatusReportContent,
        facts,
    ) -> StatusReportValidation:
        fact_map = {fact.fact_id: fact for fact in facts}
        statements = cls._statements(content)
        cited: set[str] = set()

        for statement in statements:
            if not statement.fact_ids:
                raise UngroundedStatusReportError(
                    "Every report statement must cite at least one fact"
                )
            unknown = [
                fact_id
                for fact_id in statement.fact_ids
                if fact_id not in fact_map
            ]
            if unknown:
                raise UngroundedStatusReportError(
                    "Generated report cited unknown fact IDs: "
                    + ", ".join(sorted(unknown))
                )

            cited.update(statement.fact_ids)
            cited_text = " ".join(
                fact_map[fact_id].text
                for fact_id in statement.fact_ids
            )
            cls._validate_numbers(statement, cited_text)

        return StatusReportValidation(
            grounded=True,
            statement_count=len(statements),
            cited_fact_count=len(cited),
            available_fact_count=len(facts),
        )

    @staticmethod
    def _statements(content: StatusReportContent) -> list[ReportStatement]:
        return [
            *content.executive_summary,
            *content.accomplishments,
            *content.risks_and_issues,
            *content.decisions_needed,
            *content.next_steps,
            *content.data_quality_notes,
        ]

    @staticmethod
    def _validate_numbers(
        statement: ReportStatement,
        cited_text: str,
    ) -> None:
        numbers = set(
            re.findall(r"(?<![A-Za-z])\d+(?:\.\d+)?%?", statement.text)
        )
        cited_numbers = set(
            re.findall(r"(?<![A-Za-z])\d+(?:\.\d+)?%?", cited_text)
        )
        invented = sorted(numbers - cited_numbers)
        if invented:
            raise UngroundedStatusReportError(
                "Generated statement contains numeric values not present in "
                "its cited facts: " + ", ".join(invented)
            )


__all__ = [
    "AIProviderError",
    "StatusReportGeneratorService",
    "UngroundedStatusReportError",
]
