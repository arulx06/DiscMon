from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, Index, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, UUIDPrimaryKeyMixin
from app.db.models.enums import SyncStatus
from app.db.models.types import enum_column


class SyncOutbox(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "sync_outbox"
    __table_args__ = (Index("ix_sync_outbox_status_created", "status", "created_at"),)

    entity_type: Mapped[str] = mapped_column(String(64), nullable=False)
    entity_id: Mapped[uuid.UUID] = mapped_column(nullable=False)
    revision_id: Mapped[uuid.UUID | None] = mapped_column(nullable=True)
    operation: Mapped[str] = mapped_column(String(32), default="upsert", nullable=False)
    payload_json: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)
    status: Mapped[SyncStatus] = mapped_column(
        enum_column(SyncStatus), default=SyncStatus.pending, nullable=False
    )
    retries: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    last_attempt_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class SyncState(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "sync_state"

    sheet_id: Mapped[str] = mapped_column(String(255), nullable=False)
    tab: Mapped[str] = mapped_column(String(120), nullable=False)
    remote_row_key: Mapped[str | None] = mapped_column(String(512), nullable=True)
    last_success_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
