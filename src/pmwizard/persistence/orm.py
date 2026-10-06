"""SQLAlchemy persistence models for PMWizard Project Memory.

Domain models remain in pmwizard.models. These ORM classes are storage-specific.
"""

from datetime import date, datetime, timezone
from uuid import UUID, uuid4

from sqlalchemy import JSON, Date, DateTime, Float, String, Text, Uuid
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class Base(DeclarativeBase):
    pass


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False
    )


class TenantMixin:
    tenant_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), index=True, nullable=False)


class ProvenanceMixin:
    provenance: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)


class ProjectORM(Base, TimestampMixin, TenantMixin, ProvenanceMixin):
    __tablename__ = "projects"

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    objective: Mapped[str | None] = mapped_column(Text)

    portfolio_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True))
    program_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True))
    project_manager_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True))
    sponsor_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True))

    methodology: Mapped[str | None] = mapped_column(String(100))
    industry: Mapped[str | None] = mapped_column(String(100))
    lifecycle_phase: Mapped[str | None] = mapped_column(String(100))
    status: Mapped[str | None] = mapped_column(String(100))
    priority: Mapped[str | None] = mapped_column(String(100))

    start_date: Mapped[date | None] = mapped_column(Date)
    planned_end_date: Mapped[date | None] = mapped_column(Date)
    forecast_end_date: Mapped[date | None] = mapped_column(Date)
    actual_end_date: Mapped[date | None] = mapped_column(Date)

    business_value: Mapped[str | None] = mapped_column(Text)
    source_system: Mapped[str | None] = mapped_column(String(100))
    external_id: Mapped[str | None] = mapped_column(String(255))


class ActionItemORM(Base, TimestampMixin, TenantMixin, ProvenanceMixin):
    __tablename__ = "action_items"

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    project_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), index=True, nullable=False)
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    owner_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True))
    due_date: Mapped[date | None] = mapped_column(Date)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    status: Mapped[str] = mapped_column(String(50), nullable=False)
    priority: Mapped[str | None] = mapped_column(String(50))
    progress_summary: Mapped[str | None] = mapped_column(Text)
    last_progress_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    latest_evidence_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True))


class RiskORM(Base, TimestampMixin, TenantMixin, ProvenanceMixin):
    __tablename__ = "risks"

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    project_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), index=True, nullable=False)
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    category: Mapped[str | None] = mapped_column(String(100))
    probability: Mapped[float | None] = mapped_column(Float)
    impact: Mapped[str | None] = mapped_column(String(100))
    exposure: Mapped[float | None] = mapped_column(Float)
    impact_type: Mapped[str | None] = mapped_column(String(100))
    trigger: Mapped[str | None] = mapped_column(Text)
    mitigation: Mapped[str | None] = mapped_column(Text)
    contingency: Mapped[str | None] = mapped_column(Text)
    owner_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True))
    status: Mapped[str] = mapped_column(String(50), nullable=False)
    due_date: Mapped[date | None] = mapped_column(Date)
    identified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class AssumptionORM(Base, TimestampMixin, TenantMixin, ProvenanceMixin):
    __tablename__ = "assumptions"

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    project_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), index=True, nullable=False)
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    category: Mapped[str | None] = mapped_column(String(100))
    owner_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True))
    status: Mapped[str] = mapped_column(String(50), nullable=False)
    validation_date: Mapped[date | None] = mapped_column(Date)
    identified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    validated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    outcome: Mapped[str | None] = mapped_column(Text)


class IssueORM(Base, TimestampMixin, TenantMixin, ProvenanceMixin):
    __tablename__ = "issues"

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    project_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), index=True, nullable=False)
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    category: Mapped[str | None] = mapped_column(String(100))
    severity: Mapped[str | None] = mapped_column(String(100))
    impact_type: Mapped[str | None] = mapped_column(String(100))
    owner_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True))
    status: Mapped[str] = mapped_column(String(50), nullable=False)
    due_date: Mapped[date | None] = mapped_column(Date)
    identified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    resolution: Mapped[str | None] = mapped_column(Text)


class DependencyORM(Base, TimestampMixin, TenantMixin, ProvenanceMixin):
    __tablename__ = "dependencies"

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    project_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), index=True, nullable=False)
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    dependency_type: Mapped[str | None] = mapped_column(String(100))
    owner_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True))
    provider: Mapped[str | None] = mapped_column(String(255))
    required_by: Mapped[date | None] = mapped_column(Date)
    status: Mapped[str] = mapped_column(String(50), nullable=False)
    criticality: Mapped[str | None] = mapped_column(String(100))


class DecisionORM(Base, TimestampMixin, TenantMixin, ProvenanceMixin):
    __tablename__ = "decisions"

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    project_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), index=True, nullable=False)
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(50), nullable=False)
    decision_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    decision_maker_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True))
    context: Mapped[str | None] = mapped_column(Text)
    alternatives_considered: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    rationale: Mapped[str | None] = mapped_column(Text)
    expected_impact: Mapped[str | None] = mapped_column(Text)
    review_date: Mapped[date | None] = mapped_column(Date)


class EvidenceORM(Base, TimestampMixin, TenantMixin, ProvenanceMixin):
    __tablename__ = "evidence"

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    project_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), index=True, nullable=False)
    source_type: Mapped[str] = mapped_column(String(100), nullable=False)
    source_system: Mapped[str | None] = mapped_column(String(100))
    source_reference: Mapped[str | None] = mapped_column(Text)
    external_id: Mapped[str | None] = mapped_column(String(255))
    author: Mapped[str | None] = mapped_column(String(255))
    captured_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    effective_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    content_excerpt: Mapped[str | None] = mapped_column(Text)
    content_hash: Mapped[str | None] = mapped_column(String(128))
    permission_scope: Mapped[list] = mapped_column(JSON, default=list, nullable=False)


class EventORM(Base, TimestampMixin, TenantMixin, ProvenanceMixin):
    __tablename__ = "events"

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    project_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), index=True, nullable=False)
    event_type: Mapped[str] = mapped_column(String(100), nullable=False)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    actor_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True))
    entity_type: Mapped[str | None] = mapped_column(String(100))
    entity_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True))
    previous_value: Mapped[dict | None] = mapped_column(JSON)
    new_value: Mapped[dict | None] = mapped_column(JSON)
    source_evidence_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True))


class RelationshipORM(Base, TimestampMixin, TenantMixin, ProvenanceMixin):
    __tablename__ = "relationships"

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    project_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), index=True, nullable=False)
    source_entity_type: Mapped[str] = mapped_column(String(100), nullable=False)
    source_entity_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    relationship_type: Mapped[str] = mapped_column(String(100), nullable=False)
    target_entity_type: Mapped[str] = mapped_column(String(100), nullable=False)
    target_entity_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    valid_from: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    valid_to: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    confidence: Mapped[float | None] = mapped_column(Float)
    origin: Mapped[str] = mapped_column(String(50), nullable=False)
    source_evidence_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True))


class AISuggestionORM(Base, TimestampMixin, TenantMixin, ProvenanceMixin):
    __tablename__ = "ai_suggestions"

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    project_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), index=True, nullable=False)
    suggestion_type: Mapped[str] = mapped_column(String(100), nullable=False)
    target_entity_type: Mapped[str | None] = mapped_column(String(100))
    target_entity_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True))
    proposed_changes: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    evidence_ids: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    confidence: Mapped[float] = mapped_column(Float, nullable=False)
    review_status: Mapped[str] = mapped_column(String(50), nullable=False)
    model_provider: Mapped[str | None] = mapped_column(String(100))
    model_name: Mapped[str | None] = mapped_column(String(100))


class HumanReviewORM(Base, TimestampMixin, TenantMixin):
    __tablename__ = "human_reviews"

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    project_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), index=True, nullable=False)
    suggestion_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), index=True, nullable=False)
    reviewer_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    status: Mapped[str] = mapped_column(String(50), nullable=False)
    reviewed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    reviewer_note: Mapped[str | None] = mapped_column(Text)
    final_changes: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)


class AuditLogORM(Base, TenantMixin):
    __tablename__ = "audit_log"

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    project_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True), index=True)
    actor_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True))
    action: Mapped[str] = mapped_column(String(100), nullable=False)
    entity_type: Mapped[str] = mapped_column(String(100), nullable=False)
    entity_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    previous_state: Mapped[dict | None] = mapped_column(JSON)
    proposed_state: Mapped[dict | None] = mapped_column(JSON)
    final_state: Mapped[dict | None] = mapped_column(JSON)
    evidence_ids: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )
