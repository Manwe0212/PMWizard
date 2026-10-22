"""Source-to-Evidence ingestion pipeline for PMWizard V0."""

from __future__ import annotations

from uuid import UUID

from sqlalchemy.orm import Session

from pmwizard.models import Evidence, Provenance
from pmwizard.models.enums import OriginType
from pmwizard.persistence.repositories import ProjectMemoryRepository

from .models import IngestionOutcome, IngestionResult, SourceRecord
from .normalizer import EvidenceContentNormalizer


class EvidenceIngestionService:
    """Normalize, deduplicate, and persist authorized source records."""

    def __init__(
        self,
        session: Session,
        *,
        normalizer: EvidenceContentNormalizer | None = None,
    ) -> None:
        self.session = session
        self.repository = ProjectMemoryRepository(session)
        self.normalizer = normalizer or EvidenceContentNormalizer()

    def ingest(
        self,
        tenant_id: UUID,
        record: SourceRecord,
    ) -> IngestionResult:
        project = self.repository.get_project(tenant_id, record.project_id)
        if project is None:
            raise LookupError("Project not found for tenant")

        normalized = self.normalizer.normalize(record.content)
        if not normalized.full_text:
            return IngestionResult(
                outcome=IngestionOutcome.EMPTY_CONTENT,
                reason="Source content is empty after deterministic normalization.",
            )

        if record.external_id is not None:
            existing = self.repository.get_evidence_by_source_identity(
                tenant_id,
                record.project_id,
                record.source_system,
                record.external_id,
            )
            if existing is not None:
                if existing.content_hash == normalized.content_hash:
                    return IngestionResult(
                        outcome=IngestionOutcome.DUPLICATE,
                        evidence=existing,
                        duplicate_of=existing.id,
                        reason=(
                            "The same source-system/external-id record with identical "
                            "normalized content is already stored."
                        ),
                    )
                return IngestionResult(
                    outcome=IngestionOutcome.SOURCE_CHANGED,
                    evidence=existing,
                    duplicate_of=existing.id,
                    reason=(
                        "The source-system/external-id already exists with different "
                        "content. V0 does not overwrite historical Evidence."
                    ),
                )

        existing_hash = self.repository.get_evidence_by_hash(
            tenant_id,
            record.project_id,
            normalized.content_hash,
            record.source_system,
            record.source_type,
        )
        if existing_hash is not None:
            return IngestionResult(
                outcome=IngestionOutcome.DUPLICATE,
                evidence=existing_hash,
                duplicate_of=existing_hash.id,
                reason=(
                    "Equivalent normalized content from the same source type/system "
                    "already exists in this Project."
                ),
            )

        evidence = Evidence(
            project_id=record.project_id,
            source_type=record.source_type,
            source_system=record.source_system,
            source_reference=record.source_reference,
            external_id=record.external_id,
            author=record.author,
            captured_at=record.captured_at,
            effective_at=record.effective_at,
            content_excerpt=normalized.excerpt,
            content_hash=normalized.content_hash,
            permission_scope=record.permission_scope,
            provenance=Provenance(
                origin=OriginType.INTEGRATION,
                source_system=record.source_system,
                source_type=record.source_type,
                source_id=record.external_id,
            ),
        )

        self.repository.add_evidence(tenant_id, evidence)
        self.session.commit()

        return IngestionResult(
            outcome=IngestionOutcome.INGESTED,
            evidence=evidence,
            reason="Source record normalized and persisted as canonical Evidence.",
        )
