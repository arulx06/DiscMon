from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Index, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, UUIDPrimaryKeyMixin
from app.db.models.enums import EligibilityStatus, HardGateStatus, RecommendationBucket
from app.db.models.types import enum_column


class Assessment(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "assessments"
    __table_args__ = (
        Index("ix_assessments_opportunity_created", "opportunity_id", "created_at"),
        Index("ix_assessments_bucket_score", "recommended_bucket", "score_total"),
    )

    opportunity_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("opportunities.id", ondelete="CASCADE"), nullable=False
    )
    revision_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("opportunity_revisions.id", ondelete="SET NULL"), nullable=True
    )
    rules_version: Mapped[str] = mapped_column(String(32), nullable=False)
    profile_version: Mapped[int] = mapped_column(Integer, nullable=False)
    score_total: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    factor_scores_json: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)
    hard_gate_status: Mapped[HardGateStatus] = mapped_column(
        enum_column(HardGateStatus), default=HardGateStatus.needs_verification, nullable=False
    )
    professional_eligibility_state: Mapped[EligibilityStatus] = mapped_column(
        enum_column(EligibilityStatus), nullable=False
    )
    india_eligibility_state: Mapped[EligibilityStatus] = mapped_column(
        enum_column(EligibilityStatus), nullable=False
    )
    evidence_refs_json: Mapped[list] = mapped_column(JSONB, default=list, nullable=False)
    confidence: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    recommended_bucket: Mapped[RecommendationBucket] = mapped_column(
        enum_column(RecommendationBucket), nullable=False
    )
    recommendation_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_ai_assisted: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    model_info_json: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
