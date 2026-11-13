from __future__ import annotations

from datetime import datetime, time

from sqlalchemy import CheckConstraint, DateTime, Integer, SmallInteger, String, Time, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class RuntimeSchedule(Base):
    __tablename__ = "runtime_schedule"
    __table_args__ = (
        CheckConstraint("id = 1", name="singleton"),
        CheckConstraint("revision > 0", name="revision_positive"),
        CheckConstraint("start_time < shutdown_time", name="same_day_window"),
        CheckConstraint("timezone = 'Asia/Kolkata'", name="fixed_timezone"),
        CheckConstraint(
            "shutdown_time >= start_time + INTERVAL '60 minutes'", name="duration_minimum"
        ),
        CheckConstraint("start_time <= TIME '20:00'", name="backup_start_compatible"),
        CheckConstraint("shutdown_time >= TIME '21:00'", name="backup_shutdown_compatible"),
        CheckConstraint(
            "(applied_revision IS NULL) = (applied_start_time IS NULL) "
            "AND (applied_revision IS NULL) = (applied_shutdown_time IS NULL)",
            name="applied_fields_consistent",
        ),
        CheckConstraint(
            "sync_error IS NULL OR sync_error IN "
            "('snapshot_write_failed', 'snapshot_invalid', 'controller_apply_failed', "
            "'database_unavailable')",
            name="sync_error_known",
        ),
    )

    id: Mapped[int] = mapped_column(SmallInteger, primary_key=True, autoincrement=False)
    revision: Mapped[int] = mapped_column(Integer, nullable=False)
    start_time: Mapped[time] = mapped_column(Time, nullable=False)
    shutdown_time: Mapped[time] = mapped_column(Time, nullable=False)
    timezone: Mapped[str] = mapped_column(String(64), nullable=False)
    applied_revision: Mapped[int | None] = mapped_column(Integer)
    applied_start_time: Mapped[time | None] = mapped_column(Time)
    applied_shutdown_time: Mapped[time | None] = mapped_column(Time)
    last_sync_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    sync_error: Mapped[str | None] = mapped_column(String(40))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )
