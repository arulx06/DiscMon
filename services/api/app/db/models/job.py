from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, UUIDPrimaryKeyMixin
from app.db.models.enums import JobKind, JobState
from app.db.models.types import enum_column


class Job(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "jobs"
    __table_args__ = (
        Index("ix_jobs_state_available", "state", "available_at"),
        Index("ix_jobs_source_state", "source_id", "state"),
        Index("ix_jobs_locked_by", "locked_by"),
    )

    kind: Mapped[JobKind] = mapped_column(enum_column(JobKind), nullable=False)
    source_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("sources.id", ondelete="CASCADE"), nullable=True
    )
    payload_json: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    state: Mapped[JobState] = mapped_column(
        enum_column(JobState), default=JobState.queued, nullable=False
    )
    attempts: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    max_attempts: Mapped[int] = mapped_column(Integer, default=4, nullable=False)
    available_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    locked_by: Mapped[str | None] = mapped_column(String(120), nullable=True)
    lock_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_error_redacted: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )
