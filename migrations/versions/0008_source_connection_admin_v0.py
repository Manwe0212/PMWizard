"""Add Source connection administration test state.

Revision ID: 0008_source_connection_admin_v0
Revises: 0007_source_runtime_v0
Create Date: 2026-10-29
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0008_source_connection_admin_v0"
down_revision: Union[str, None] = "0007_source_runtime_v0"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "source_connections",
        sa.Column("test_requested_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "source_connections",
        sa.Column("test_requested_by", sa.Uuid(), nullable=True),
    )
    op.add_column(
        "source_connections",
        sa.Column("test_lease_owner", sa.String(length=255), nullable=True),
    )
    op.add_column(
        "source_connections",
        sa.Column("test_lease_expires_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "source_connections",
        sa.Column("last_test_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "source_connections",
        sa.Column("last_test_status", sa.String(length=50), nullable=True),
    )
    op.add_column(
        "source_connections",
        sa.Column("last_test_message", sa.Text(), nullable=True),
    )
    op.create_index(
        "ix_source_connections_test_requested_at",
        "source_connections",
        ["test_requested_at"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_source_connections_test_requested_at",
        table_name="source_connections",
    )
    op.drop_column("source_connections", "last_test_message")
    op.drop_column("source_connections", "last_test_status")
    op.drop_column("source_connections", "last_test_at")
    op.drop_column("source_connections", "test_lease_expires_at")
    op.drop_column("source_connections", "test_lease_owner")
    op.drop_column("source_connections", "test_requested_by")
    op.drop_column("source_connections", "test_requested_at")
