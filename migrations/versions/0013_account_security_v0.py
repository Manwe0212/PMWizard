"""Add tenant-scoped one-time password resets and session invalidation.

Revision ID: 0013_account_security_v0
Revises: 0012_verified_email_v0
"""

from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = "0013_account_security_v0"
down_revision: Union[str, None] = "0012_verified_email_v0"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "app_users",
        sa.Column(
            "auth_version", sa.Integer(), nullable=False,
            server_default="0",
        ),
    )

    op.create_table(
        "password_resets",
        sa.Column("id", sa.Uuid(), primary_key=True, nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("token_hash", name="uq_password_resets_token_hash"),
    )
    op.create_index("ix_password_resets_tenant_id", "password_resets", ["tenant_id"])
    op.create_index("ix_password_resets_user_id", "password_resets", ["user_id"])

    op.create_table(
        "revoked_sessions",
        sa.Column("id", sa.Uuid(), primary_key=True, nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("jti_hash", sa.String(length=64), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("jti_hash", name="uq_revoked_sessions_jti_hash"),
    )
    op.create_index("ix_revoked_sessions_tenant_id", "revoked_sessions", ["tenant_id"])
    op.create_index("ix_revoked_sessions_user_id", "revoked_sessions", ["user_id"])


def downgrade() -> None:
    op.drop_table("revoked_sessions")
    op.drop_table("password_resets")
    op.drop_column("app_users", "auth_version")
