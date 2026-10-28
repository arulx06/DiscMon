from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, UUIDPrimaryKeyMixin
from app.db.models.enums import AlertKind, AlertStatus
from app.db.models.types import enum_column


class Alert(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "alerts"
    __table_args__ = (
        Index("ix_alerts_status_scheduled", "status", "scheduled_for"),
        Index("ix_alerts_opportunity", "opportunity_id"),
    )

    opportunity_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("opportunities.id", ondelete="CASCADE"), nullable=True
    )
    revision_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("opportunity_revisions.id", ondelete="SET NULL"), nullable=True
    )
    digest_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("digests.id", ondelete="SET NULL"), nullable=True
    )
    channel: Mapped[str] = mapped_column(String(32), nullable=False)
    alert_kind: Mapped[AlertKind] = mapped_column(enum_column(AlertKind), nullable=False)
    dedup_key: Mapped[str] = mapped_column(String(512), unique=True, nullable=False)
    status: Mapped[AlertStatus] = mapped_column(
        enum_column(AlertStatus), default=AlertStatus.pending, nullable=False
    )
    payload_json: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)
    scheduled_for: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    retry_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    provider_message_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    last_error_redacted: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
