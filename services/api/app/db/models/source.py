from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin
from app.db.models.enums import (
    ApprovalStatus,
    HealthStatus,
    LegalReviewStatus,
    Officialness,
    SourceKind,
)
from app.db.models.types import enum_column


class Source(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "sources"
    __table_args__ = (
        Index("ix_sources_enabled_next_due", "enabled", "next_due_at"),
        Index("ix_sources_health_status", "health_status"),
    )

    name: Mapped[str] = mapped_column(String(200), nullable=False)
    source_kind: Mapped[SourceKind] = mapped_column(enum_column(SourceKind), nullable=False)
    root_url: Mapped[str] = mapped_column(String(2048), nullable=False)
    config_json: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)
    officialness: Mapped[Officialness] = mapped_column(
        enum_column(Officialness), default=Officialness.unknown, nullable=False
    )
    enabled: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    approval_status: Mapped[ApprovalStatus] = mapped_column(
        enum_column(ApprovalStatus), default=ApprovalStatus.candidate, nullable=False
    )
    legal_review_status: Mapped[LegalReviewStatus] = mapped_column(
        enum_column(LegalReviewStatus), default=LegalReviewStatus.pending, nullable=False
    )
    robots_last_checked_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    rate_limit_json: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)
    schedule_cron: Mapped[str | None] = mapped_column(String(64), nullable=True)
    interval_hours: Mapped[float] = mapped_column(Numeric(6, 2), default=24, nullable=False)
    next_due_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_attempt_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_success_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_error_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_error_category: Mapped[str | None] = mapped_column(String(80), nullable=True)
    last_error_redacted: Mapped[str | None] = mapped_column(Text, nullable=True)
    consecutive_failures: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    health_status: Mapped[HealthStatus] = mapped_column(
        enum_column(HealthStatus), default=HealthStatus.unknown, nullable=False
    )

    runs: Mapped[list[SourceRun]] = relationship(back_populates="source")


class SourceRun(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "source_runs"
    __table_args__ = (Index("ix_source_runs_source_started", "source_id", "started_at"),)

    source_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("sources.id", ondelete="CASCADE"), nullable=False
    )
    job_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("jobs.id", ondelete="SET NULL"), nullable=True
    )
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    scan_complete: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    http_status: Mapped[int | None] = mapped_column(Integer, nullable=True)
    records_seen: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    records_created: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    records_updated: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    records_skipped: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    bytes_received: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    fetch_duration_ms: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    error_category: Mapped[str | None] = mapped_column(String(80), nullable=True)
    error_message_redacted: Mapped[str | None] = mapped_column(Text, nullable=True)
    cursor_before: Mapped[str | None] = mapped_column(Text, nullable=True)
    cursor_after: Mapped[str | None] = mapped_column(Text, nullable=True)
    snapshot_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)

    source: Mapped[Source] = relationship(back_populates="runs")
