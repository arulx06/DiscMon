"""persist the singleton runtime schedule and host application status

Revision ID: e5b8f19c2a70
Revises: d4a7c1e9f210
Create Date: 2026-11-13 00:00:00.000000
"""
from __future__ import annotations

from collections.abc import Sequence
from datetime import time

from alembic import op
import sqlalchemy as sa


revision: str = "e5b8f19c2a70"
down_revision: str | None = "d4a7c1e9f210"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "runtime_schedule",
        sa.Column("id", sa.SmallInteger(), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("start_time", sa.Time(), nullable=False),
        sa.Column("shutdown_time", sa.Time(), nullable=False),
        sa.Column("timezone", sa.String(length=64), nullable=False),
        sa.Column("applied_revision", sa.Integer(), nullable=True),
        sa.Column("applied_start_time", sa.Time(), nullable=True),
        sa.Column("applied_shutdown_time", sa.Time(), nullable=True),
        sa.Column("last_sync_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("sync_error", sa.String(length=40), nullable=True),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint("id = 1", name="ck_runtime_schedule_singleton"),
        sa.CheckConstraint("revision > 0", name="ck_runtime_schedule_revision_positive"),
        sa.CheckConstraint(
            "start_time < shutdown_time", name="ck_runtime_schedule_same_day_window"
        ),
        sa.CheckConstraint(
            "shutdown_time >= start_time + INTERVAL '60 minutes'",
            name="ck_runtime_schedule_duration_minimum",
        ),
        sa.CheckConstraint(
            "start_time <= TIME '20:00'", name="ck_runtime_schedule_backup_start_compatible"
        ),
        sa.CheckConstraint(
            "shutdown_time >= TIME '21:00'",
            name="ck_runtime_schedule_backup_shutdown_compatible",
        ),
        sa.CheckConstraint(
            "(applied_revision IS NULL) = (applied_start_time IS NULL) "
            "AND (applied_revision IS NULL) = (applied_shutdown_time IS NULL)",
            name="ck_runtime_schedule_applied_fields_consistent",
        ),
        sa.CheckConstraint(
            "sync_error IS NULL OR sync_error IN "
            "('snapshot_write_failed', 'snapshot_invalid', 'controller_apply_failed', "
            "'database_unavailable')",
            name="ck_runtime_schedule_sync_error_known",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_runtime_schedule"),
    )
    op.bulk_insert(
        sa.table(
            "runtime_schedule",
            sa.column("id", sa.SmallInteger()),
            sa.column("revision", sa.Integer()),
            sa.column("start_time", sa.Time()),
            sa.column("shutdown_time", sa.Time()),
            sa.column("timezone", sa.String(length=64)),
        ),
        [
            {
                "id": 1,
                "revision": 1,
                "start_time": time(9, 0),
                "shutdown_time": time(21, 0),
                "timezone": "Asia/Kolkata",
            }
        ],
    )


def downgrade() -> None:
    op.drop_table("runtime_schedule")
