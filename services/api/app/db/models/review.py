from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, UUIDPrimaryKeyMixin
from app.db.models.enums import UserDecision
from app.db.models.types import enum_column


class Review(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "reviews"
    __table_args__ = (Index("ix_reviews_opportunity_created", "opportunity_id", "created_at"),)

    opportunity_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("opportunities.id", ondelete="CASCADE"), nullable=False
    )
    decision: Mapped[UserDecision] = mapped_column(enum_column(UserDecision), nullable=False)
    previous_decision: Mapped[UserDecision | None] = mapped_column(
        enum_column(UserDecision), nullable=True
    )
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    followup_due_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    actor: Mapped[str] = mapped_column(String(120), default="owner", nullable=False)
