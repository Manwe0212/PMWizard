"""Persistent hashed auth request limits, shared across API replicas.

Revision ID: 0014_auth_rate_limits_v0
Revises: 0013_account_security_v0
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0014_auth_rate_limits_v0"
down_revision: Union[str, None] = "0013_account_security_v0"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "auth_rate_limits",
        sa.Column("key_hash", sa.String(length=64), primary_key=True, nullable=False),
        sa.Column("hits", sa.Integer(), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_auth_rate_limits_expires_at", "auth_rate_limits", ["expires_at"])


def downgrade() -> None:
    op.drop_table("auth_rate_limits")
