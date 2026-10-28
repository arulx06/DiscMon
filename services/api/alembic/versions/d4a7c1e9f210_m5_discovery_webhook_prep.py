"""discovery promotion, webhook receipts and preparation fields

Revision ID: d4a7c1e9f210
Revises: b76e2a98caca
Create Date: 2026-10-28 21:10:00.000000
"""
from __future__ import annotations

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "d4a7c1e9f210"
down_revision: str | None = "b76e2a98caca"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "discovery_candidates",
        sa.Column("promoted_source_id", sa.Uuid(), nullable=True),
    )
    op.create_foreign_key(
        "fk_discovery_candidates_promoted_source",
        "discovery_candidates",
        "sources",
        ["promoted_source_id"],
        ["id"],
        ondelete="SET NULL",
    )

    op.add_column("opportunities", sa.Column("next_action", sa.Text(), nullable=True))

    op.create_table(
        "webhook_events",
        sa.Column("provider", sa.String(length=40), nullable=False),
        sa.Column("event_hash", sa.String(length=64), nullable=False),
        sa.Column("watch_uuid", sa.String(length=128), nullable=True),
        sa.Column("watch_url", sa.String(length=2048), nullable=True),
        sa.Column("source_id", sa.Uuid(), nullable=True),
        sa.Column("job_id", sa.Uuid(), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("detail_redacted", sa.Text(), nullable=True),
        sa.Column(
            "received_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.ForeignKeyConstraint(
            ["job_id"],
            ["jobs.id"],
            name=op.f("fk_webhook_events_job_id_jobs"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["source_id"],
            ["sources.id"],
            name=op.f("fk_webhook_events_source_id_sources"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_webhook_events")),
        sa.UniqueConstraint("event_hash", name=op.f("uq_webhook_events_event_hash")),
    )
    op.create_index(
        "ix_webhook_events_received", "webhook_events", ["received_at"], unique=False
    )
    op.create_index(
        "ix_webhook_events_source_received",
        "webhook_events",
        ["source_id", "received_at"],
        unique=False,
    )

    op.create_unique_constraint(
        "uq_sync_state_sheet_tab", "sync_state", ["sheet_id", "tab"]
    )


def downgrade() -> None:
    op.drop_constraint("uq_sync_state_sheet_tab", "sync_state", type_="unique")
    op.drop_index("ix_webhook_events_source_received", table_name="webhook_events")
    op.drop_index("ix_webhook_events_received", table_name="webhook_events")
    op.drop_table("webhook_events")
    op.drop_column("opportunities", "next_action")
    op.drop_constraint(
        "fk_discovery_candidates_promoted_source",
        "discovery_candidates",
        type_="foreignkey",
    )
    op.drop_column("discovery_candidates", "promoted_source_id")
