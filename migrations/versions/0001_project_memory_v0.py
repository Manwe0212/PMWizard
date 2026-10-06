"""Create Project Memory V0 schema.

Revision ID: 0001_project_memory_v0
Revises:
Create Date: 2026-10-06
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0001_project_memory_v0"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _identity_columns() -> list[sa.Column]:
    return [
        sa.Column("id", sa.Uuid(), primary_key=True, nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
    ]


def _timestamps() -> list[sa.Column]:
    return [
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    ]


def _provenance() -> sa.Column:
    return sa.Column("provenance", sa.JSON(), nullable=False)


def _project_scoped_indexes(table: str) -> None:
    op.create_index(f"ix_{table}_tenant_id", table, ["tenant_id"])
    op.create_index(f"ix_{table}_project_id", table, ["project_id"])


def upgrade() -> None:
    op.create_table(
        "projects",
        *_identity_columns(),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text()),
        sa.Column("objective", sa.Text()),
        sa.Column("portfolio_id", sa.Uuid()),
        sa.Column("program_id", sa.Uuid()),
        sa.Column("project_manager_id", sa.Uuid()),
        sa.Column("sponsor_id", sa.Uuid()),
        sa.Column("methodology", sa.String(length=100)),
        sa.Column("industry", sa.String(length=100)),
        sa.Column("lifecycle_phase", sa.String(length=100)),
        sa.Column("status", sa.String(length=100)),
        sa.Column("priority", sa.String(length=100)),
        sa.Column("start_date", sa.Date()),
        sa.Column("planned_end_date", sa.Date()),
        sa.Column("forecast_end_date", sa.Date()),
        sa.Column("actual_end_date", sa.Date()),
        sa.Column("business_value", sa.Text()),
        sa.Column("source_system", sa.String(length=100)),
        sa.Column("external_id", sa.String(length=255)),
        *_timestamps(),
        _provenance(),
    )
    op.create_index("ix_projects_tenant_id", "projects", ["tenant_id"])

    op.create_table(
        "action_items",
        *_identity_columns(),
        sa.Column("project_id", sa.Uuid(), nullable=False),
        sa.Column("title", sa.String(length=500), nullable=False),
        sa.Column("description", sa.Text()),
        sa.Column("owner_id", sa.Uuid()),
        sa.Column("due_date", sa.Date()),
        sa.Column("completed_at", sa.DateTime(timezone=True)),
        sa.Column("status", sa.String(length=50), nullable=False),
        sa.Column("priority", sa.String(length=50)),
        sa.Column("progress_summary", sa.Text()),
        sa.Column("last_progress_date", sa.DateTime(timezone=True)),
        sa.Column("latest_evidence_id", sa.Uuid()),
        *_timestamps(),
        _provenance(),
    )
    _project_scoped_indexes("action_items")

    op.create_table(
        "risks",
        *_identity_columns(),
        sa.Column("project_id", sa.Uuid(), nullable=False),
        sa.Column("title", sa.String(length=500), nullable=False),
        sa.Column("description", sa.Text()),
        sa.Column("category", sa.String(length=100)),
        sa.Column("probability", sa.Float()),
        sa.Column("impact", sa.String(length=100)),
        sa.Column("exposure", sa.Float()),
        sa.Column("impact_type", sa.String(length=100)),
        sa.Column("trigger", sa.Text()),
        sa.Column("mitigation", sa.Text()),
        sa.Column("contingency", sa.Text()),
        sa.Column("owner_id", sa.Uuid()),
        sa.Column("status", sa.String(length=50), nullable=False),
        sa.Column("due_date", sa.Date()),
        sa.Column("identified_at", sa.DateTime(timezone=True)),
        sa.Column("closed_at", sa.DateTime(timezone=True)),
        *_timestamps(),
        _provenance(),
    )
    _project_scoped_indexes("risks")

    op.create_table(
        "assumptions",
        *_identity_columns(),
        sa.Column("project_id", sa.Uuid(), nullable=False),
        sa.Column("title", sa.String(length=500), nullable=False),
        sa.Column("description", sa.Text()),
        sa.Column("category", sa.String(length=100)),
        sa.Column("owner_id", sa.Uuid()),
        sa.Column("status", sa.String(length=50), nullable=False),
        sa.Column("validation_date", sa.Date()),
        sa.Column("identified_at", sa.DateTime(timezone=True)),
        sa.Column("validated_at", sa.DateTime(timezone=True)),
        sa.Column("outcome", sa.Text()),
        *_timestamps(),
        _provenance(),
    )
    _project_scoped_indexes("assumptions")

    op.create_table(
        "issues",
        *_identity_columns(),
        sa.Column("project_id", sa.Uuid(), nullable=False),
        sa.Column("title", sa.String(length=500), nullable=False),
        sa.Column("description", sa.Text()),
        sa.Column("category", sa.String(length=100)),
        sa.Column("severity", sa.String(length=100)),
        sa.Column("impact_type", sa.String(length=100)),
        sa.Column("owner_id", sa.Uuid()),
        sa.Column("status", sa.String(length=50), nullable=False),
        sa.Column("due_date", sa.Date()),
        sa.Column("identified_at", sa.DateTime(timezone=True)),
        sa.Column("resolved_at", sa.DateTime(timezone=True)),
        sa.Column("resolution", sa.Text()),
        *_timestamps(),
        _provenance(),
    )
    _project_scoped_indexes("issues")

    op.create_table(
        "dependencies",
        *_identity_columns(),
        sa.Column("project_id", sa.Uuid(), nullable=False),
        sa.Column("title", sa.String(length=500), nullable=False),
        sa.Column("description", sa.Text()),
        sa.Column("dependency_type", sa.String(length=100)),
        sa.Column("owner_id", sa.Uuid()),
        sa.Column("provider", sa.String(length=255)),
        sa.Column("required_by", sa.Date()),
        sa.Column("status", sa.String(length=50), nullable=False),
        sa.Column("criticality", sa.String(length=100)),
        *_timestamps(),
        _provenance(),
    )
    _project_scoped_indexes("dependencies")

    op.create_table(
        "decisions",
        *_identity_columns(),
        sa.Column("project_id", sa.Uuid(), nullable=False),
        sa.Column("title", sa.String(length=500), nullable=False),
        sa.Column("description", sa.Text()),
        sa.Column("status", sa.String(length=50), nullable=False),
        sa.Column("decision_date", sa.DateTime(timezone=True)),
        sa.Column("decision_maker_id", sa.Uuid()),
        sa.Column("context", sa.Text()),
        sa.Column("alternatives_considered", sa.JSON(), nullable=False),
        sa.Column("rationale", sa.Text()),
        sa.Column("expected_impact", sa.Text()),
        sa.Column("review_date", sa.Date()),
        *_timestamps(),
        _provenance(),
    )
    _project_scoped_indexes("decisions")

    op.create_table(
        "evidence",
        *_identity_columns(),
        sa.Column("project_id", sa.Uuid(), nullable=False),
        sa.Column("source_type", sa.String(length=100), nullable=False),
        sa.Column("source_system", sa.String(length=100)),
        sa.Column("source_reference", sa.Text()),
        sa.Column("external_id", sa.String(length=255)),
        sa.Column("author", sa.String(length=255)),
        sa.Column("captured_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("effective_at", sa.DateTime(timezone=True)),
        sa.Column("content_excerpt", sa.Text()),
        sa.Column("content_hash", sa.String(length=128)),
        sa.Column("permission_scope", sa.JSON(), nullable=False),
        *_timestamps(),
        _provenance(),
    )
    _project_scoped_indexes("evidence")

    op.create_table(
        "events",
        *_identity_columns(),
        sa.Column("project_id", sa.Uuid(), nullable=False),
        sa.Column("event_type", sa.String(length=100), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("actor_id", sa.Uuid()),
        sa.Column("entity_type", sa.String(length=100)),
        sa.Column("entity_id", sa.Uuid()),
        sa.Column("previous_value", sa.JSON()),
        sa.Column("new_value", sa.JSON()),
        sa.Column("source_evidence_id", sa.Uuid()),
        *_timestamps(),
        _provenance(),
    )
    _project_scoped_indexes("events")

    op.create_table(
        "relationships",
        *_identity_columns(),
        sa.Column("project_id", sa.Uuid(), nullable=False),
        sa.Column("source_entity_type", sa.String(length=100), nullable=False),
        sa.Column("source_entity_id", sa.Uuid(), nullable=False),
        sa.Column("relationship_type", sa.String(length=100), nullable=False),
        sa.Column("target_entity_type", sa.String(length=100), nullable=False),
        sa.Column("target_entity_id", sa.Uuid(), nullable=False),
        sa.Column("valid_from", sa.DateTime(timezone=True)),
        sa.Column("valid_to", sa.DateTime(timezone=True)),
        sa.Column("confidence", sa.Float()),
        sa.Column("origin", sa.String(length=50), nullable=False),
        sa.Column("source_evidence_id", sa.Uuid()),
        *_timestamps(),
        _provenance(),
    )
    _project_scoped_indexes("relationships")

    op.create_table(
        "ai_suggestions",
        *_identity_columns(),
        sa.Column("project_id", sa.Uuid(), nullable=False),
        sa.Column("suggestion_type", sa.String(length=100), nullable=False),
        sa.Column("target_entity_type", sa.String(length=100)),
        sa.Column("target_entity_id", sa.Uuid()),
        sa.Column("proposed_changes", sa.JSON(), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("evidence_ids", sa.JSON(), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.Column("review_status", sa.String(length=50), nullable=False),
        sa.Column("model_provider", sa.String(length=100)),
        sa.Column("model_name", sa.String(length=100)),
        *_timestamps(),
        _provenance(),
    )
    _project_scoped_indexes("ai_suggestions")

    op.create_table(
        "human_reviews",
        *_identity_columns(),
        sa.Column("project_id", sa.Uuid(), nullable=False),
        sa.Column("suggestion_id", sa.Uuid(), nullable=False),
        sa.Column("reviewer_id", sa.Uuid(), nullable=False),
        sa.Column("status", sa.String(length=50), nullable=False),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("reviewer_note", sa.Text()),
        sa.Column("final_changes", sa.JSON(), nullable=False),
        *_timestamps(),
        _provenance(),
    )
    _project_scoped_indexes("human_reviews")
    op.create_index("ix_human_reviews_suggestion_id", "human_reviews", ["suggestion_id"])

    op.create_table(
        "audit_log",
        *_identity_columns(),
        sa.Column("project_id", sa.Uuid()),
        sa.Column("actor_id", sa.Uuid()),
        sa.Column("action", sa.String(length=100), nullable=False),
        sa.Column("entity_type", sa.String(length=100), nullable=False),
        sa.Column("entity_id", sa.Uuid(), nullable=False),
        sa.Column("previous_state", sa.JSON()),
        sa.Column("proposed_state", sa.JSON()),
        sa.Column("final_state", sa.JSON()),
        sa.Column("evidence_ids", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_audit_log_tenant_id", "audit_log", ["tenant_id"])
    op.create_index("ix_audit_log_project_id", "audit_log", ["project_id"])


def downgrade() -> None:
    for table in [
        "audit_log",
        "human_reviews",
        "ai_suggestions",
        "relationships",
        "events",
        "evidence",
        "decisions",
        "dependencies",
        "issues",
        "assumptions",
        "risks",
        "action_items",
        "projects",
    ]:
        op.drop_table(table)
