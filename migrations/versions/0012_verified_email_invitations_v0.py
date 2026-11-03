"""Track invitation email delivery and verified inbox possession.

Revision ID: 0012_verified_email_v0
Revises: 0011_project_invitations_v0
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0012_verified_email_v0"
down_revision: Union[str, None] = "0011_project_invitations_v0"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "project_invitations",
        sa.Column(
            "delivery_method", sa.String(length=16), nullable=False,
            server_default="manual",
        ),
    )
    op.add_column(
        "project_invitations",
        sa.Column(
            "delivery_status", sa.String(length=20), nullable=False,
            server_default="not_applicable",
        ),
    )
    op.add_column(
        "project_invitations",
        sa.Column("delivered_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "app_users",
        sa.Column("email_verified_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("app_users", "email_verified_at")
    op.drop_column("project_invitations", "delivered_at")
    op.drop_column("project_invitations", "delivery_status")
    op.drop_column("project_invitations", "delivery_method")
