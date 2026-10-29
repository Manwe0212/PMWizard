"""Tests for grounded AI Status Report Generator V0."""

from datetime import date, datetime, timedelta, timezone
import json
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from pmwizard.api import create_app
from pmwizard.models import (
    AISuggestion,
    ActionItem,
    Decision,
    Evidence,
    Project,
    Risk,
)
from pmwizard.models.enums import (
    ActionItemStatus,
    DecisionStatus,
    RiskStatus,
    SuggestionType,
)
from pmwizard.persistence import Base, ProjectMemoryService
from pmwizard.reports import (
    ReportStatement,
    StatusReportAudience,
    StatusReportContent,
    StatusReportGeneratorService,
    StatusReportGroundingService,
    StatusReportRequest,
    UngroundedStatusReportError,
)


NOW = datetime(2026, 10, 29, 15, 30, tzinfo=timezone.utc)


class FakeProvider:
    provider_name = "fake"
    model_name = "fake-status-v0"

    def __init__(self, content: StatusReportContent) -> None:
        self.content = content
        self.last_input: str | None = None
        self.last_instructions: str | None = None

    def generate(self, *, instructions, input_text, output_type):
        self.last_input = input_text
        self.last_instructions = instructions
        assert output_type is StatusReportContent
        return self.content


@pytest.fixture()
def report_env():
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    factory = sessionmaker(
        bind=engine,
        class_=Session,
        expire_on_commit=False,
    )
    yield factory


def _headers(
    tenant_id: UUID,
    user_id: UUID,
    *permissions: str,
) -> dict[str, str]:
    return {
        "X-PMWizard-Tenant-ID": str(tenant_id),
        "X-PMWizard-User-ID": str(user_id),
        "X-PMWizard-Permissions": ",".join(permissions),
    }


def _seed(factory):
    tenant_id = uuid4()
    user_id = uuid4()

    with factory() as session:
        memory = ProjectMemoryService(session)
        project = memory.create_project(
            tenant_id,
            Project(
                name="Status Report Demo",
                status="active",
                lifecycle_phase="delivery",
                planned_end_date=date(2026, 12, 15),
                forecast_end_date=date(2026, 12, 15),
            ),
        )

        completed = memory.add_action_item(
            tenant_id,
            ActionItem(
                project_id=project.id,
                title="Complete API integration",
                status=ActionItemStatus.COMPLETED,
                completed_at=NOW - timedelta(days=2),
                due_date=date(2026, 10, 28),
            ),
        )
        memory.add_action_item(
            tenant_id,
            ActionItem(
                project_id=project.id,
                title="Finalize rollout checklist",
                status=ActionItemStatus.IN_PROGRESS,
                due_date=date(2026, 11, 2),
                progress_summary="Checklist is under review.",
            ),
        )
        memory.add_risk(
            tenant_id,
            Risk(
                project_id=project.id,
                title="Vendor capacity",
                status=RiskStatus.MITIGATING,
                impact="high",
                mitigation="Confirm secondary implementation window.",
            ),
        )
        memory.add_decision(
            tenant_id,
            Decision(
                project_id=project.id,
                title="Approve rollout date",
                status=DecisionStatus.PENDING,
                review_date=date(2026, 10, 31),
                expected_impact="Controls production launch timing.",
            ),
        )

        evidence = memory.add_evidence(
            tenant_id,
            Evidence(
                project_id=project.id,
                source_type="email",
                source_system="synthetic",
                captured_at=NOW,
                content_excerpt="Unreviewed claim from an email.",
                permission_scope=["project:read"],
            ),
        )
        memory.add_ai_suggestion(
            tenant_id,
            AISuggestion(
                project_id=project.id,
                suggestion_type=SuggestionType.NEW_ISSUE,
                reason="UNREVIEWED-SUGGESTION-MUST-NOT-BE-REPORTABLE",
                evidence_ids=[evidence.id],
                confidence=0.95,
            ),
        )

    return tenant_id, user_id, project, completed


def test_grounding_packet_uses_governed_state_not_pending_suggestions(
    report_env,
) -> None:
    tenant_id, _, project, _ = _seed(report_env)

    with report_env() as session:
        packet = StatusReportGroundingService(session).build(
            tenant_id=tenant_id,
            project_id=project.id,
            lookback_days=7,
            as_of=NOW,
        )

    serialized = packet.model_dump_json()
    assert packet.project_name == "Status Report Demo"
    assert packet.period_start == date(2026, 10, 23)
    assert packet.period_end == date(2026, 10, 29)
    assert any(fact.fact_id == "HEALTH-001" for fact in packet.facts)
    assert any(
        fact.category == "accomplishment"
        and "Complete API integration" in fact.text
        for fact in packet.facts
    )
    assert any(
        fact.category == "risk" and "Vendor capacity" in fact.text
        for fact in packet.facts
    )
    assert any(
        fact.category == "decision" and "Approve rollout date" in fact.text
        for fact in packet.facts
    )
    assert "UNREVIEWED-SUGGESTION-MUST-NOT-BE-REPORTABLE" not in serialized


def test_generator_accepts_structured_grounded_draft(report_env) -> None:
    tenant_id, _, project, _ = _seed(report_env)
    provider = FakeProvider(
        StatusReportContent(
            executive_summary=[
                ReportStatement(
                    text="Project Health is currently assessed from governed project data.",
                    fact_ids=["HEALTH-001"],
                )
            ],
            accomplishments=[
                ReportStatement(
                    text="API integration was completed during the reporting period.",
                    fact_ids=["ACCOMPLISHMENT-001"],
                )
            ],
            risks_and_issues=[
                ReportStatement(
                    text="Vendor capacity remains an active high-impact risk.",
                    fact_ids=["RISK-001"],
                )
            ],
            decisions_needed=[
                ReportStatement(
                    text="The rollout-date decision remains pending.",
                    fact_ids=["DECISION-001"],
                )
            ],
            next_steps=[
                ReportStatement(
                    text="Finalize the rollout checklist.",
                    fact_ids=["NEXT-ACTION-001"],
                )
            ],
        )
    )

    with report_env() as session:
        draft = StatusReportGeneratorService(session, provider).generate(
            tenant_id=tenant_id,
            project_id=project.id,
            command=StatusReportRequest(
                lookback_days=7,
                audience=StatusReportAudience.EXECUTIVE,
            ),
            as_of=NOW,
        )

    assert draft.provider == "fake"
    assert draft.model == "fake-status-v0"
    assert draft.validation.grounded is True
    assert draft.validation.statement_count == 5
    assert draft.validation.cited_fact_count == 5
    assert draft.title == "Status Report Demo — 7-Day Status Report"
    assert provider.last_input is not None
    assert "Grounding Packet" in provider.last_input
    assert provider.last_instructions is not None
    assert "Use ONLY facts" in provider.last_instructions


def test_generator_rejects_unknown_fact_id(report_env) -> None:
    tenant_id, _, project, _ = _seed(report_env)
    provider = FakeProvider(
        StatusReportContent(
            executive_summary=[
                ReportStatement(
                    text="Everything is on track.",
                    fact_ids=["MADE-UP-001"],
                )
            ]
        )
    )

    with report_env() as session:
        with pytest.raises(
            UngroundedStatusReportError,
            match="unknown fact IDs",
        ):
            StatusReportGeneratorService(session, provider).generate(
                tenant_id=tenant_id,
                project_id=project.id,
                command=StatusReportRequest(),
                as_of=NOW,
            )


def test_generator_rejects_numeric_claim_not_in_cited_facts(report_env) -> None:
    tenant_id, _, project, _ = _seed(report_env)
    provider = FakeProvider(
        StatusReportContent(
            accomplishments=[
                ReportStatement(
                    text="API integration improved delivery by 47%.",
                    fact_ids=["ACCOMPLISHMENT-001"],
                )
            ]
        )
    )

    with report_env() as session:
        with pytest.raises(
            UngroundedStatusReportError,
            match="numeric values",
        ):
            StatusReportGeneratorService(session, provider).generate(
                tenant_id=tenant_id,
                project_id=project.id,
                command=StatusReportRequest(),
                as_of=NOW,
            )


def test_status_report_api_requires_review_permission(report_env) -> None:
    tenant_id, user_id, project, _ = _seed(report_env)
    provider = FakeProvider(StatusReportContent())
    app = create_app(
        report_env,
        allow_trusted_headers=True,
        status_report_provider=provider,
    )

    with TestClient(app) as client:
        response = client.post(
            f"/v1/projects/{project.id}/status-report/draft",
            json={"lookback_days": 7, "audience": "executive"},
            headers=_headers(tenant_id, user_id, "project:read"),
        )

    assert response.status_code == 403
    assert "project:review" in response.json()["detail"]


def test_status_report_api_returns_503_without_provider(report_env) -> None:
    tenant_id, user_id, project, _ = _seed(report_env)
    app = create_app(report_env, allow_trusted_headers=True)

    with TestClient(app) as client:
        response = client.post(
            f"/v1/projects/{project.id}/status-report/draft",
            json={"lookback_days": 7, "audience": "executive"},
            headers=_headers(
                tenant_id,
                user_id,
                "project:read",
                "project:review",
            ),
        )

    assert response.status_code == 503
    assert "provider is not configured" in response.json()["detail"]


def test_status_report_api_returns_valid_grounded_draft(report_env) -> None:
    tenant_id, user_id, project, _ = _seed(report_env)
    provider = FakeProvider(
        StatusReportContent(
            executive_summary=[
                ReportStatement(
                    text="Project Health is currently assessed from governed project data.",
                    fact_ids=["HEALTH-001"],
                )
            ]
        )
    )
    app = create_app(
        report_env,
        allow_trusted_headers=True,
        status_report_provider=provider,
    )

    with TestClient(app) as client:
        response = client.post(
            f"/v1/projects/{project.id}/status-report/draft",
            json={"lookback_days": 7, "audience": "executive"},
            headers=_headers(
                tenant_id,
                user_id,
                "project:read",
                "project:review",
            ),
        )

    assert response.status_code == 200
    payload = response.json()
    assert payload["project_name"] == "Status Report Demo"
    assert payload["validation"]["grounded"] is True
    assert payload["content"]["executive_summary"][0]["fact_ids"] == [
        "HEALTH-001"
    ]


def test_status_report_api_rejects_ungrounded_provider_output(report_env) -> None:
    tenant_id, user_id, project, _ = _seed(report_env)
    provider = FakeProvider(
        StatusReportContent(
            executive_summary=[
                ReportStatement(
                    text="The project is 99% complete.",
                    fact_ids=["PROJECT-001"],
                )
            ]
        )
    )
    app = create_app(
        report_env,
        allow_trusted_headers=True,
        status_report_provider=provider,
    )

    with TestClient(app) as client:
        response = client.post(
            f"/v1/projects/{project.id}/status-report/draft",
            json={"lookback_days": 7, "audience": "executive"},
            headers=_headers(
                tenant_id,
                user_id,
                "project:read",
                "project:review",
            ),
        )

    assert response.status_code == 502
    assert "failed grounding validation" in response.json()["detail"]
