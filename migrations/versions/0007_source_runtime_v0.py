"""Add opaque credential references to source connections.

Revision ID: 0007_source_runtime_v0
Revises: 0006_automation_scheduler_v0
Create Date: 2026-10-29
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0007_source_runtime_v0"
down_revision: Union[str, None] = "0006_automation_scheduler_v0"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "source_connections",
        sa.Column("credential_ref", sa.String(length=255), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("source_connections", "credential_ref")
