from __future__ import annotations

import uuid
from datetime import date, datetime

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    PrimaryKeyConstraint,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin
from app.db.models.enums import (
    CredibilityLevel,
    DeadlinePrecision,
    EligibilityStatus,
    LifeState,
    OpportunityType,
    RevisionType,
    SourceKind,
    UserDecision,
)
from app.db.models.types import enum_column


class Organization(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "organizations"

    canonical_name: Mapped[str] = mapped_column(String(300), nullable=False)
    canonical_domain: Mapped[str | None] = mapped_column(String(255), unique=True, nullable=True)
    aliases: Mapped[list[str]] = mapped_column(ARRAY(String(200)), default=list, nullable=False)
    industry_tags: Mapped[list[str]] = mapped_column(
        ARRAY(String(64)), default=list, nullable=False
    )
    careers_url: Mapped[str | None] = mapped_column(String(2048), nullable=True)


class Opportunity(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "opportunities"
    __table_args__ = (
        Index(
            "uq_opportunities_provider_key",
            "provider_key",
            unique=True,
            postgresql_where=text("provider_key IS NOT NULL"),
        ),
        Index(
            "uq_opportunities_canonical_url",
            "official_url",
            unique=True,
            postgresql_where=text("provider_key IS NULL AND official_url IS NOT NULL"),
        ),
        Index("ix_opportunities_life_state_verified", "life_state", "last_verified_at"),
        Index("ix_opportunities_deadline", "deadline_on"),
        Index("ix_opportunities_user_decision", "user_decision"),
        Index("ix_opportunities_type", "opportunity_type"),
    )

    provider_key: Mapped[str | None] = mapped_column(String(512), nullable=True)
    provider_source_kind: Mapped[SourceKind | None] = mapped_column(
        enum_column(SourceKind), nullable=True
    )
    organization_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("organizations.id", ondelete="SET NULL"), nullable=True
    )
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    opportunity_type: Mapped[OpportunityType] = mapped_column(
        enum_column(OpportunityType), default=OpportunityType.other, nullable=False
    )
    description_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    scope: Mapped[str | None] = mapped_column(Text, nullable=True)
    requirements_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    skills: Mapped[list[str]] = mapped_column(ARRAY(String(80)), default=list, nullable=False)
    seniority_min_yoe: Mapped[int | None] = mapped_column(Integer, nullable=True)
    seniority_max_yoe: Mapped[int | None] = mapped_column(Integer, nullable=True)
    employment_type: Mapped[str | None] = mapped_column(String(80), nullable=True)
    country_codes: Mapped[list[str]] = mapped_column(ARRAY(String(2)), default=list, nullable=False)
    allowed_remote_countries: Mapped[list[str]] = mapped_column(
        ARRAY(String(2)), default=list, nullable=False
    )
    workplace_type: Mapped[str | None] = mapped_column(String(32), nullable=True)
    location_text: Mapped[str | None] = mapped_column(String(500), nullable=True)
    requires_relocation: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    employment_conflict: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    official_url: Mapped[str] = mapped_column(String(2048), nullable=False)
    application_url: Mapped[str | None] = mapped_column(String(2048), nullable=True)
    opens_on: Mapped[date | None] = mapped_column(Date, nullable=True)
    deadline_on: Mapped[date | None] = mapped_column(Date, nullable=True)
    deadline_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    deadline_timezone: Mapped[str | None] = mapped_column(String(64), nullable=True)
    deadline_precision: Mapped[DeadlinePrecision] = mapped_column(
        enum_column(DeadlinePrecision), default=DeadlinePrecision.unknown, nullable=False
    )
    monetary_value_json: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)
    compensation_summary: Mapped[str | None] = mapped_column(String(500), nullable=True)
    professional_eligibility: Mapped[EligibilityStatus] = mapped_column(
        enum_column(EligibilityStatus), default=EligibilityStatus.unknown, nullable=False
    )
    india_eligibility: Mapped[EligibilityStatus] = mapped_column(
        enum_column(EligibilityStatus), default=EligibilityStatus.unknown, nullable=False
    )
    student_only: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    student_eligibility: Mapped[EligibilityStatus] = mapped_column(
        enum_column(EligibilityStatus), default=EligibilityStatus.unknown, nullable=False
    )
    eligibility_reasons_json: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)
    eligibility_checked_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    credibility_level: Mapped[CredibilityLevel] = mapped_column(
        enum_column(CredibilityLevel), default=CredibilityLevel.unknown, nullable=False
    )
    life_state: Mapped[LifeState] = mapped_column(
        enum_column(LifeState), default=LifeState.new, nullable=False
    )
    first_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    last_verified_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    last_material_change_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    current_revision_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey(
            "opportunity_revisions.id",
            use_alter=True,
            name="fk_opportunities_current_revision",
            ondelete="SET NULL",
        ),
        nullable=True,
    )
    current_revision_number: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    user_decision: Mapped[UserDecision] = mapped_column(
        enum_column(UserDecision), default=UserDecision.unreviewed, nullable=False
    )
    owner_notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    next_action: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_fixture: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)

    organization: Mapped[Organization | None] = relationship()
    source_links: Mapped[list[OpportunitySource]] = relationship(
        back_populates="opportunity", cascade="all, delete-orphan"
    )
    revisions: Mapped[list[OpportunityRevision]] = relationship(
        back_populates="opportunity",
        foreign_keys="OpportunityRevision.opportunity_id",
        cascade="all, delete-orphan",
    )


class OpportunitySource(Base):
    __tablename__ = "opportunity_sources"
    __table_args__ = (PrimaryKeyConstraint("opportunity_id", "source_id", "source_external_id"),)

    opportunity_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("opportunities.id", ondelete="CASCADE"), nullable=False
    )
    source_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("sources.id", ondelete="CASCADE"), nullable=False
    )
    source_external_id: Mapped[str] = mapped_column(String(512), nullable=False)
    source_item_url: Mapped[str | None] = mapped_column(String(2048), nullable=True)
    raw_evidence_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("raw_evidence.id", ondelete="SET NULL"), nullable=True
    )
    first_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    last_seen_run_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("source_runs.id", ondelete="SET NULL"), nullable=True
    )
    absence_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    opportunity: Mapped[Opportunity] = relationship(back_populates="source_links")


class OpportunityRevision(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "opportunity_revisions"
    __table_args__ = (
        UniqueConstraint(
            "opportunity_id", "revision_number", name="uq_opportunity_revision_number"
        ),
        Index("ix_opportunity_revisions_observed", "opportunity_id", "observed_at"),
    )

    opportunity_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("opportunities.id", ondelete="CASCADE"), nullable=False
    )
    revision_number: Mapped[int] = mapped_column(Integer, nullable=False)
    normalized_snapshot_json: Mapped[dict] = mapped_column(JSONB, nullable=False)
    normalized_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    material_diff_json: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    source_run_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("source_runs.id", ondelete="SET NULL"), nullable=True
    )
    evidence_ids: Mapped[list] = mapped_column(JSONB, default=list, nullable=False)
    revision_type: Mapped[RevisionType] = mapped_column(enum_column(RevisionType), nullable=False)

    opportunity: Mapped[Opportunity] = relationship(
        back_populates="revisions", foreign_keys=[opportunity_id]
    )
