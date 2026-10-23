"""Add persisted Project Health snapshots for history and trends.

Revision ID: 0004_health_history_trends_v0
Revises: 0003_sources_workspace_v0
Create Date: 2026-10-23
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0004_health_history_trends_v0"
down_revision: Union[str, None] = "0003_sources_workspace_v0"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "project_health_snapshots",
        sa.Column("id", sa.Uuid(), primary_key=True, nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("project_id", sa.Uuid(), nullable=False),
        sa.Column("captured_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("captured_by", sa.Uuid(), nullable=True),
        sa.Column("capture_source", sa.String(length=50), nullable=False),
        sa.Column("model_version", sa.String(length=50), nullable=False),
        sa.Column("score", sa.Integer(), nullable=True),
        sa.Column("band", sa.String(length=50), nullable=False),
        sa.Column("coverage_percent", sa.Integer(), nullable=False),
        sa.Column("coverage_band", sa.String(length=50), nullable=False),
        sa.Column("available_weight", sa.Integer(), nullable=False),
        sa.Column("factor_scores", sa.JSON(), nullable=False),
        sa.Column("key_drivers", sa.JSON(), nullable=False),
        sa.Column("snapshot_payload", sa.JSON(), nullable=False),
        sa.Column("state_fingerprint", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index(
        "ix_project_health_snapshots_tenant_id",
        "project_health_snapshots",
        ["tenant_id"],
    )
    op.create_index(
        "ix_project_health_snapshots_project_id",
        "project_health_snapshots",
        ["project_id"],
    )
    op.create_index(
        "ix_project_health_snapshots_captured_at",
        "project_health_snapshots",
        ["captured_at"],
    )
    op.create_index(
        "ix_project_health_snapshots_project_captured",
        "project_health_snapshots",
        ["tenant_id", "project_id", "captured_at"],
    )


def downgrade() -> None:
    op.drop_table("project_health_snapshots")
