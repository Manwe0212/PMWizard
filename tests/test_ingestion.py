"""Tests for Ingestion V0."""

from datetime import datetime, timezone
from uuid import uuid4

import pytest
from pydantic import ValidationError
from sqlalchemy import func, select

from pmwizard.ingestion import (
    EvidenceContentNormalizer,
    EvidenceIngestionService,
    IngestionOutcome,
    SourceRecord,
)
from pmwizard.intelligence import ProgressIntelligenceService, ProgressPipelineOutcome
from pmwizard.models import ActionItem, Project
from pmwizard.models.enums import ActionItemStatus, OriginType
from pmwizard.persistence import (
    Base,
    ProjectMemoryService,
    create_engine_from_url,
    create_session_factory,
)
from pmwizard.persistence.orm import EvidenceORM


NOW = datetime(2026, 10, 21, 20, 0, tzinfo=timezone.utc)


@pytest.fixture()
def session():
    engine = create_engine_from_url("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    factory = create_session_factory(engine)
    with factory() as session:
        yield session


def _record(project_id, content: str, *, external_id: str | None = "msg-1") -> SourceRecord:
    return SourceRecord(
        project_id=project_id,
        source_type="email",
        source_system="synthetic-mail",
        external_id=external_id,
        source_reference="synthetic://mail/msg-1",
        author="pm@example.test",
        captured_at=NOW,
        content=content,
        permission_scope=["project:read"],
    )


def test_normalizer_cleans_whitespace_deterministically() -> None:
    normalized = EvidenceContentNormalizer().normalize(
        "  Hello   team\r\n\r\n\r\nNext\tline  "
    )

    assert normalized.full_text == "Hello team\n\nNext line"
    assert len(normalized.content_hash) == 64


def test_ingestion_persists_canonical_evidence_with_provenance(session) -> None:
    tenant_id = uuid4()
    memory = ProjectMemoryService(session)
    project = memory.create_project(tenant_id, Project(name="Ingestion Demo"))

    result = EvidenceIngestionService(session).ingest(
        tenant_id,
        _record(project.id, "Verify API access was completed today."),
    )

    assert result.outcome == IngestionOutcome.INGESTED
    assert result.evidence is not None
    assert result.evidence.content_hash
    assert result.evidence.provenance.origin == OriginType.INTEGRATION
    assert result.evidence.provenance.source_system == "synthetic-mail"
    assert result.evidence.provenance.source_id == "msg-1"


def test_same_external_id_and_content_is_idempotent(session) -> None:
    tenant_id = uuid4()
    memory = ProjectMemoryService(session)
    project = memory.create_project(tenant_id, Project(name="Idempotency"))

    service = EvidenceIngestionService(session)
    first = service.ingest(tenant_id, _record(project.id, "Same content"))
    second = service.ingest(tenant_id, _record(project.id, "Same content"))

    assert first.outcome == IngestionOutcome.INGESTED
    assert second.outcome == IngestionOutcome.DUPLICATE
    assert second.duplicate_of == first.evidence.id
    count = session.scalar(select(func.count()).select_from(EvidenceORM))
    assert count == 1


def test_same_external_id_with_changed_content_is_not_overwritten(session) -> None:
    tenant_id = uuid4()
    memory = ProjectMemoryService(session)
    project = memory.create_project(tenant_id, Project(name="Changed Source"))

    service = EvidenceIngestionService(session)
    first = service.ingest(tenant_id, _record(project.id, "Original content"))
    changed = service.ingest(tenant_id, _record(project.id, "Updated content"))

    assert first.outcome == IngestionOutcome.INGESTED
    assert changed.outcome == IngestionOutcome.SOURCE_CHANGED
    assert changed.duplicate_of == first.evidence.id
    count = session.scalar(select(func.count()).select_from(EvidenceORM))
    assert count == 1


def test_equivalent_content_with_different_external_id_is_deduplicated(session) -> None:
    tenant_id = uuid4()
    memory = ProjectMemoryService(session)
    project = memory.create_project(tenant_id, Project(name="Hash Deduplication"))

    service = EvidenceIngestionService(session)
    first = service.ingest(
        tenant_id,
        _record(project.id, "Hello   team", external_id="msg-1"),
    )
    second = service.ingest(
        tenant_id,
        _record(project.id, "Hello team", external_id="msg-2"),
    )

    assert first.outcome == IngestionOutcome.INGESTED
    assert second.outcome == IngestionOutcome.DUPLICATE
    assert second.duplicate_of == first.evidence.id


def test_same_content_can_exist_in_different_projects(session) -> None:
    tenant_id = uuid4()
    memory = ProjectMemoryService(session)
    project_a = memory.create_project(tenant_id, Project(name="Project A"))
    project_b = memory.create_project(tenant_id, Project(name="Project B"))

    service = EvidenceIngestionService(session)
    first = service.ingest(
        tenant_id,
        _record(project_a.id, "Same project update", external_id=None),
    )
    second = service.ingest(
        tenant_id,
        _record(project_b.id, "Same project update", external_id=None),
    )

    assert first.outcome == IngestionOutcome.INGESTED
    assert second.outcome == IngestionOutcome.INGESTED


def test_cross_tenant_project_ingestion_is_blocked(session) -> None:
    tenant_a = uuid4()
    tenant_b = uuid4()
    memory = ProjectMemoryService(session)
    project = memory.create_project(tenant_a, Project(name="Private Project"))

    with pytest.raises(LookupError):
        EvidenceIngestionService(session).ingest(
            tenant_b,
            _record(project.id, "Private update"),
        )


def test_empty_normalized_content_is_skipped(session) -> None:
    tenant_id = uuid4()
    memory = ProjectMemoryService(session)
    project = memory.create_project(tenant_id, Project(name="Empty Source"))

    result = EvidenceIngestionService(session).ingest(
        tenant_id,
        _record(project.id, "  \r\n\t  "),
    )

    assert result.outcome == IngestionOutcome.EMPTY_CONTENT
    assert result.evidence is None
    count = session.scalar(select(func.count()).select_from(EvidenceORM))
    assert count == 0


def test_permission_scope_is_required() -> None:
    with pytest.raises(ValidationError):
        SourceRecord(
            project_id=uuid4(),
            source_type="email",
            source_system="synthetic-mail",
            captured_at=NOW,
            content="Hello",
            permission_scope=[],
        )


def test_excerpt_can_be_truncated_without_changing_full_content_hash(session) -> None:
    tenant_id = uuid4()
    memory = ProjectMemoryService(session)
    project = memory.create_project(tenant_id, Project(name="Long Source"))
    normalizer = EvidenceContentNormalizer(max_excerpt_chars=10)
    service = EvidenceIngestionService(session, normalizer=normalizer)

    result = service.ingest(
        tenant_id,
        _record(project.id, "abcdefghijklmnopqrstuvwxyz"),
    )

    assert result.evidence.content_excerpt == "abcdefghij"
    assert result.evidence.content_hash == normalizer.normalize(
        "abcdefghijklmnopqrstuvwxyz"
    ).content_hash


def test_ingested_evidence_can_feed_progress_intelligence(session) -> None:
    tenant_id = uuid4()
    memory = ProjectMemoryService(session)
    project = memory.create_project(tenant_id, Project(name="End-to-End Ingestion"))
    action = memory.add_action_item(
        tenant_id,
        ActionItem(
            project_id=project.id,
            title="Verify API access",
            status=ActionItemStatus.IN_PROGRESS,
            created_at=NOW,
        ),
    )

    ingestion = EvidenceIngestionService(session).ingest(
        tenant_id,
        _record(project.id, "Verify API access was completed today."),
    )
    assert ingestion.evidence is not None

    result = ProgressIntelligenceService(session).analyze_evidence(
        tenant_id,
        ingestion.evidence,
    )

    assert result.outcome == ProgressPipelineOutcome.SUGGESTION_CREATED
    assert result.suggestion is not None
    assert result.suggestion.target_entity_id == action.id
    assert result.suggestion.proposed_changes["status"] == "completed"
