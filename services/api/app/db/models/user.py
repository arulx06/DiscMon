from __future__ import annotations

from sqlalchemy import Boolean, Integer, String
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin
from app.db.models.enums import EmploymentStage
from app.db.models.types import enum_column


class UserProfile(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "user_profile"

    employment_stage: Mapped[EmploymentStage] = mapped_column(
        enum_column(EmploymentStage), default=EmploymentStage.prejoin, nullable=False
    )
    student_status: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    home_country: Mapped[str] = mapped_column(String(2), default="IN", nullable=False)
    preferred_countries: Mapped[list[str]] = mapped_column(
        ARRAY(String(2)), default=lambda: ["IN"], nullable=False
    )
    relocation_allowed: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    categories: Mapped[list[str]] = mapped_column(ARRAY(String(64)), default=list, nullable=False)
    skills: Mapped[list[str]] = mapped_column(ARRAY(String(64)), default=list, nullable=False)
    ignore_terms: Mapped[list[str]] = mapped_column(ARRAY(String(64)), default=list, nullable=False)
    desired_yoe_min: Mapped[int | None] = mapped_column(Integer, nullable=True)
    desired_yoe_max: Mapped[int | None] = mapped_column(Integer, nullable=True)
    quiet_hours_start: Mapped[int] = mapped_column(Integer, default=22, nullable=False)
    quiet_hours_end: Mapped[int] = mapped_column(Integer, default=8, nullable=False)
    timezone: Mapped[str] = mapped_column(String(64), default="Asia/Kolkata", nullable=False)
    alert_channels: Mapped[list[str]] = mapped_column(
        ARRAY(String(32)), default=lambda: ["in_app"], nullable=False
    )
    max_immediate_alerts_per_week: Mapped[int] = mapped_column(Integer, default=5, nullable=False)
    scoring_version: Mapped[str] = mapped_column(String(32), default="v1", nullable=False)
    profile_version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
