"""Add durable source connections, checkpoints, and sync run history.

Revision ID: 0003_sources_workspace_v0
Revises: 0002_auth_project_selection_v0
Create Date: 2026-10-22
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0003_sources_workspace_v0"
down_revision: Union[str, None] = "0002_auth_project_selection_v0"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "source_connections",
        sa.Column("id", sa.Uuid(), primary_key=True, nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("project_id", sa.Uuid(), nullable=False),
        sa.Column("connector_key", sa.String(length=500), nullable=False),
        sa.Column("source_type", sa.String(length=100), nullable=False),
        sa.Column("source_system", sa.String(length=100), nullable=False),
        sa.Column("display_name", sa.String(length=255), nullable=False),
        sa.Column("permission_scope", sa.JSON(), nullable=False),
        sa.Column("safe_config", sa.JSON(), nullable=False),
        sa.Column("is_enabled", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint(
            "tenant_id",
            "project_id",
            "connector_key",
            name="uq_source_connections_project_connector",
        ),
    )
    op.create_index(
        "ix_source_connections_tenant_id",
        "source_connections",
        ["tenant_id"],
    )
    op.create_index(
        "ix_source_connections_project_id",
        "source_connections",
        ["project_id"],
    )

    op.create_table(
        "connector_checkpoints",
        sa.Column("id", sa.Uuid(), primary_key=True, nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("project_id", sa.Uuid(), nullable=False),
        sa.Column("connector_key", sa.String(length=500), nullable=False),
        sa.Column("cursor", sa.Text(), nullable=False),
        sa.Column("fingerprint", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint(
            "tenant_id",
            "project_id",
            "connector_key",
            name="uq_connector_checkpoints_project_connector",
        ),
    )
    op.create_index(
        "ix_connector_checkpoints_tenant_id",
        "connector_checkpoints",
        ["tenant_id"],
    )
    op.create_index(
        "ix_connector_checkpoints_project_id",
        "connector_checkpoints",
        ["project_id"],
    )

    op.create_table(
        "connector_runs",
        sa.Column("id", sa.Uuid(), primary_key=True, nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("project_id", sa.Uuid(), nullable=False),
        sa.Column("source_connection_id", sa.Uuid(), nullable=True),
        sa.Column("connector_key", sa.String(length=500), nullable=False),
        sa.Column("status", sa.String(length=50), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("pages_processed", sa.Integer(), nullable=False),
        sa.Column("fetched", sa.Integer(), nullable=False),
        sa.Column("ingested", sa.Integer(), nullable=False),
        sa.Column("duplicates", sa.Integer(), nullable=False),
        sa.Column("source_changed", sa.Integer(), nullable=False),
        sa.Column("empty_content", sa.Integer(), nullable=False),
        sa.Column("skipped", sa.Integer(), nullable=False),
        sa.Column("skips", sa.JSON(), nullable=False),
        sa.Column("errors", sa.JSON(), nullable=False),
        sa.Column("start_checkpoint_present", sa.Boolean(), nullable=False),
        sa.Column("end_checkpoint_present", sa.Boolean(), nullable=False),
        sa.Column("checkpoint_fingerprint", sa.String(length=64), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index(
        "ix_connector_runs_tenant_id",
        "connector_runs",
        ["tenant_id"],
    )
    op.create_index(
        "ix_connector_runs_project_id",
        "connector_runs",
        ["project_id"],
    )
    op.create_index(
        "ix_connector_runs_connector_key",
        "connector_runs",
        ["connector_key"],
    )
    op.create_index(
        "ix_connector_runs_source_connection_id",
        "connector_runs",
        ["source_connection_id"],
    )


def downgrade() -> None:
    op.drop_table("connector_runs")
    op.drop_table("connector_checkpoints")
    op.drop_table("source_connections")
