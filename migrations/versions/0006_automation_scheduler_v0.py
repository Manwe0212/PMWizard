"""Add durable Automation & Scheduler V0 tables.

Revision ID: 0006_automation_scheduler_v0
Revises: 0005_program_portfolio_v0
Create Date: 2026-10-29
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0006_automation_scheduler_v0"
down_revision: Union[str, None] = "0005_program_portfolio_v0"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "automation_schedules",
        sa.Column("id", sa.Uuid(), primary_key=True, nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("project_id", sa.Uuid(), nullable=False),
        sa.Column("task_type", sa.String(length=100), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("interval_minutes", sa.Integer(), nullable=False),
        sa.Column("is_enabled", sa.Boolean(), nullable=False),
        sa.Column("config", sa.JSON(), nullable=False),
        sa.Column("next_run_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("pending_trigger", sa.String(length=50), nullable=False),
        sa.Column("last_run_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_status", sa.String(length=50), nullable=True),
        sa.Column("consecutive_failures", sa.Integer(), nullable=False),
        sa.Column("created_by", sa.Uuid(), nullable=True),
        sa.Column("lease_owner", sa.String(length=255), nullable=True),
        sa.Column("lease_expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index(
        "ix_automation_schedules_tenant_id",
        "automation_schedules",
        ["tenant_id"],
    )
    op.create_index(
        "ix_automation_schedules_project_id",
        "automation_schedules",
        ["project_id"],
    )
    op.create_index(
        "ix_automation_schedules_next_run_at",
        "automation_schedules",
        ["next_run_at"],
    )
    op.create_index(
        "ix_automation_schedules_lease_expires_at",
        "automation_schedules",
        ["lease_expires_at"],
    )

    op.create_table(
        "automation_runs",
        sa.Column("id", sa.Uuid(), primary_key=True, nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("schedule_id", sa.Uuid(), nullable=False),
        sa.Column("project_id", sa.Uuid(), nullable=False),
        sa.Column("task_type", sa.String(length=100), nullable=False),
        sa.Column("trigger", sa.String(length=50), nullable=False),
        sa.Column("status", sa.String(length=50), nullable=False),
        sa.Column("worker_id", sa.String(length=255), nullable=False),
        sa.Column("scheduled_for", sa.DateTime(timezone=True), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("summary", sa.JSON(), nullable=False),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index(
        "ix_automation_runs_tenant_id",
        "automation_runs",
        ["tenant_id"],
    )
    op.create_index(
        "ix_automation_runs_schedule_id",
        "automation_runs",
        ["schedule_id"],
    )
    op.create_index(
        "ix_automation_runs_project_id",
        "automation_runs",
        ["project_id"],
    )


def downgrade() -> None:
    op.drop_table("automation_runs")
    op.drop_table("automation_schedules")
