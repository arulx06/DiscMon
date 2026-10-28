from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, UUIDPrimaryKeyMixin
from app.db.models.enums import (
    ApprovalStatus,
    LegalReviewStatus,
    Officialness,
    SourceKind,
)
from app.db.models.types import enum_column


class DiscoveryCandidate(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "discovery_candidates"
    __table_args__ = (Index("ix_discovery_candidates_status", "approval_status"),)

    candidate_url: Mapped[str] = mapped_column(String(2048), nullable=False)
    found_via_source_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("sources.id", ondelete="SET NULL"), nullable=True
    )
    discovered_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    candidate_type: Mapped[str | None] = mapped_column(String(64), nullable=True)
    suggested_adapter: Mapped[SourceKind | None] = mapped_column(
        enum_column(SourceKind), nullable=True
    )
    officialness_guess: Mapped[Officialness] = mapped_column(
        enum_column(Officialness), default=Officialness.unknown, nullable=False
    )
    legal_review_status: Mapped[LegalReviewStatus] = mapped_column(
        enum_column(LegalReviewStatus), default=LegalReviewStatus.pending, nullable=False
    )
    approval_status: Mapped[ApprovalStatus] = mapped_column(
        enum_column(ApprovalStatus), default=ApprovalStatus.candidate, nullable=False
    )
    last_checked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    promoted_source_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("sources.id", ondelete="SET NULL"), nullable=True
    )
