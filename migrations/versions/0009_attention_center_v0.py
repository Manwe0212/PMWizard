"""Add per-user Attention Center receipts.

Revision ID: 0009_attention_center_v0
Revises: 0008_source_connection_admin_v0
Create Date: 2026-10-30
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0009_attention_center_v0"
down_revision: Union[str, None] = "0008_source_connection_admin_v0"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "attention_receipts",
        sa.Column("id", sa.Uuid(), primary_key=True, nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("project_id", sa.Uuid(), nullable=False),
        sa.Column("signal_key", sa.String(length=500), nullable=False),
        sa.Column("signal_fingerprint", sa.String(length=64), nullable=False),
        sa.Column("seen_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("acknowledged_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("snoozed_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint(
            "tenant_id",
            "user_id",
            "project_id",
            "signal_key",
            name="uq_attention_receipts_user_signal",
        ),
    )
    op.create_index(
        "ix_attention_receipts_tenant_id",
        "attention_receipts",
        ["tenant_id"],
    )
    op.create_index(
        "ix_attention_receipts_user_id",
        "attention_receipts",
        ["user_id"],
    )
    op.create_index(
        "ix_attention_receipts_project_id",
        "attention_receipts",
        ["project_id"],
    )


def downgrade() -> None:
    op.drop_table("attention_receipts")
