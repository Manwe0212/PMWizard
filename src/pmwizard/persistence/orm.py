"""SQLAlchemy persistence models for PMWizard Project Memory.

Domain models remain in pmwizard.models. These ORM classes are storage-specific.
"""

from datetime import date, datetime, timezone
from uuid import UUID, uuid4

from sqlalchemy import JSON, Boolean, Date, DateTime, Float, String, Text, UniqueConstraint, Uuid
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


class ProjectHealthSnapshotORM(Base, TenantMixin):
    __tablename__ = "project_health_snapshots"

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    project_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), index=True, nullable=False)
    captured_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), index=True, nullable=False
    )
    captured_by: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True))
    capture_source: Mapped[str] = mapped_column(String(50), nullable=False)
    model_version: Mapped[str] = mapped_column(String(50), nullable=False)
    score: Mapped[int | None] = mapped_column(nullable=True)
    band: Mapped[str] = mapped_column(String(50), nullable=False)
    coverage_percent: Mapped[int] = mapped_column(nullable=False)
    coverage_band: Mapped[str] = mapped_column(String(50), nullable=False)
    available_weight: Mapped[int] = mapped_column(nullable=False)
    factor_scores: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    key_drivers: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    snapshot_payload: Mapped[dict] = mapped_column(JSON, nullable=False)
    state_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )


class SourceConnectionORM(Base, TimestampMixin, TenantMixin):
    __tablename__ = "source_connections"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id",
            "project_id",
            "connector_key",
            name="uq_source_connections_project_connector",
        ),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    project_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), index=True, nullable=False)
    connector_key: Mapped[str] = mapped_column(String(500), nullable=False)
    source_type: Mapped[str] = mapped_column(String(100), nullable=False)
    source_system: Mapped[str] = mapped_column(String(100), nullable=False)
    display_name: Mapped[str] = mapped_column(String(255), nullable=False)
    permission_scope: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    safe_config: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    is_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)


class ConnectorCheckpointORM(Base, TimestampMixin, TenantMixin):
    __tablename__ = "connector_checkpoints"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id",
            "project_id",
            "connector_key",
            name="uq_connector_checkpoints_project_connector",
        ),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    project_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), index=True, nullable=False)
    connector_key: Mapped[str] = mapped_column(String(500), nullable=False)
    cursor: Mapped[str] = mapped_column(Text, nullable=False)
    fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)


class ConnectorRunORM(Base, TenantMixin):
    __tablename__ = "connector_runs"

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    project_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), index=True, nullable=False)
    source_connection_id: Mapped[UUID | None] = mapped_column(
        Uuid(as_uuid=True), index=True
    )
    connector_key: Mapped[str] = mapped_column(String(500), index=True, nullable=False)
    status: Mapped[str] = mapped_column(String(50), nullable=False)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    finished_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    pages_processed: Mapped[int] = mapped_column(default=0, nullable=False)
    fetched: Mapped[int] = mapped_column(default=0, nullable=False)
    ingested: Mapped[int] = mapped_column(default=0, nullable=False)
    duplicates: Mapped[int] = mapped_column(default=0, nullable=False)
    source_changed: Mapped[int] = mapped_column(default=0, nullable=False)
    empty_content: Mapped[int] = mapped_column(default=0, nullable=False)
    skipped: Mapped[int] = mapped_column(default=0, nullable=False)
    skips: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    errors: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    start_checkpoint_present: Mapped[bool] = mapped_column(Boolean, nullable=False)
    end_checkpoint_present: Mapped[bool] = mapped_column(Boolean, nullable=False)
    checkpoint_fingerprint: Mapped[str | None] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )


class AppUserORM(Base, TimestampMixin, TenantMixin):
    __tablename__ = "app_users"
    __table_args__ = (
        UniqueConstraint("tenant_id", "email", name="uq_app_users_tenant_email"),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    email: Mapped[str] = mapped_column(String(320), nullable=False, index=True)
    display_name: Mapped[str] = mapped_column(String(255), nullable=False)
    password_hash: Mapped[str] = mapped_column(Text, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)


class ProjectMembershipORM(Base, TimestampMixin, TenantMixin):
    __tablename__ = "project_memberships"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id",
            "user_id",
            "project_id",
            name="uq_project_memberships_user_project",
        ),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    user_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), index=True, nullable=False)
    project_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), index=True, nullable=False)
    role: Mapped[str] = mapped_column(String(100), nullable=False, default="member")
    permissions: Mapped[list] = mapped_column(JSON, default=list, nullable=False)


class PortfolioORM(Base, TimestampMixin, TenantMixin, ProvenanceMixin):
    __tablename__ = "portfolios"

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    owner_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True))
    status: Mapped[str | None] = mapped_column(String(100))
    start_date: Mapped[date | None] = mapped_column(Date)
    end_date: Mapped[date | None] = mapped_column(Date)
    strategic_objectives: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    source_system: Mapped[str | None] = mapped_column(String(100))
    external_id: Mapped[str | None] = mapped_column(String(255))


class ProgramORM(Base, TimestampMixin, TenantMixin, ProvenanceMixin):
    __tablename__ = "programs"

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    portfolio_id: Mapped[UUID | None] = mapped_column(
        Uuid(as_uuid=True), index=True
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    program_manager_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True))
    status: Mapped[str | None] = mapped_column(String(100))
    start_date: Mapped[date | None] = mapped_column(Date)
    end_date: Mapped[date | None] = mapped_column(Date)
    objectives: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    source_system: Mapped[str | None] = mapped_column(String(100))
    external_id: Mapped[str | None] = mapped_column(String(255))


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


class HumanReviewORM(Base, TimestampMixin, TenantMixin, ProvenanceMixin):
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
