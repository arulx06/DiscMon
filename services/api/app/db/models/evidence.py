from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, UUIDPrimaryKeyMixin


class RawEvidence(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "raw_evidence"
    __table_args__ = (
        Index("ix_raw_evidence_canonical_fetched", "canonical_url", "fetched_at"),
        Index("ix_raw_evidence_source_fetched", "source_id", "fetched_at"),
    )

    source_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("sources.id", ondelete="CASCADE"), nullable=False
    )
    source_run_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("source_runs.id", ondelete="SET NULL"), nullable=True
    )
    source_url: Mapped[str] = mapped_column(String(2048), nullable=False)
    canonical_url: Mapped[str | None] = mapped_column(String(2048), nullable=True)
    fetched_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    content_type: Mapped[str | None] = mapped_column(String(120), nullable=True)
    http_etag: Mapped[str | None] = mapped_column(String(255), nullable=True)
    http_last_modified: Mapped[str | None] = mapped_column(String(255), nullable=True)
    content_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    extracted_text_excerpt: Mapped[str | None] = mapped_column(Text, nullable=True)
    raw_body_path: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    content_json: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    retention_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    source_license_or_terms_note: Mapped[str | None] = mapped_column(Text, nullable=True)
