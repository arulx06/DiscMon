from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, UUIDPrimaryKeyMixin


class WebhookEvent(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "webhook_events"
    __table_args__ = (
        Index("ix_webhook_events_received", "received_at"),
        Index("ix_webhook_events_source_received", "source_id", "received_at"),
    )

    provider: Mapped[str] = mapped_column(
        String(40), default="changedetection", nullable=False
    )
    event_hash: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    watch_uuid: Mapped[str | None] = mapped_column(String(128), nullable=True)
    watch_url: Mapped[str | None] = mapped_column(String(2048), nullable=True)
    source_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("sources.id", ondelete="SET NULL"), nullable=True
    )
    job_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("jobs.id", ondelete="SET NULL"), nullable=True
    )
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    detail_redacted: Mapped[str | None] = mapped_column(Text, nullable=True)
    received_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
