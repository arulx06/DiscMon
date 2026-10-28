from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, Index, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, UUIDPrimaryKeyMixin
from app.db.models.enums import DigestKind
from app.db.models.types import enum_column


class Digest(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "digests"
    __table_args__ = (
        UniqueConstraint("period_start", "period_end", "digest_kind", name="uq_digest_window_kind"),
        Index("ix_digests_generated", "generated_at"),
    )

    period_start: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    period_end: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    digest_kind: Mapped[DigestKind] = mapped_column(enum_column(DigestKind), nullable=False)
    generated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    content_md: Mapped[str] = mapped_column(Text, nullable=False)
    content_json: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)
    opportunity_ids: Mapped[list] = mapped_column(JSONB, default=list, nullable=False)
    sent_status: Mapped[str] = mapped_column(Text, default="generated", nullable=False)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
