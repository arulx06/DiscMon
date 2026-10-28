from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from app.db.models.enums import DeadlinePrecision, OpportunityType, SourceKind


class SourceConfig(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    source_kind: SourceKind
    root_url: str
    config_json: dict[str, Any] = Field(default_factory=dict)
    officialness: str = "unknown"
    rate_limit_json: dict[str, Any] = Field(default_factory=dict)


class DiscoveredURL(BaseModel):
    url: str
    source_external_id: str | None = None
    published_at: datetime | None = None


class FetchResult(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)

    source_id: uuid.UUID
    fetched_at: datetime
    http_status: int | None = None
    content_type: str | None = None
    etag: str | None = None
    last_modified: str | None = None
    raw_hash: str | None = None
    raw_reference: str | None = None
    cursor: str | None = None
    error_class: str | None = None
    error_message: str | None = None
    raw_bytes: bytes = b""
    content_json: dict[str, Any] | None = None
    scan_complete: bool = False
    not_modified: bool = False
    source_url: str | None = None

    @property
    def ok(self) -> bool:
        return (
            self.error_class is None
            and self.http_status is not None
            and 200 <= self.http_status < 300
        )


class CompensationDTO(BaseModel):
    cash: str | None = None
    equity: str | None = None
    credits: str | None = None
    currency: str | None = None
    period: str | None = None
    summary: str | None = None
    raw: str | None = None


class NormalizedCandidate(BaseModel):
    source_external_id: str
    provider_key: str | None = None
    title: str
    organization_name: str
    organization_domain: str | None = None
    opportunity_type: OpportunityType = OpportunityType.other
    description_summary: str | None = None
    requirements_summary: str | None = None
    scope: str | None = None
    skills: list[str] = Field(default_factory=list)
    official_url: str
    application_url: str | None = None
    location_text: str | None = None
    country_codes: list[str] = Field(default_factory=list)
    allowed_remote_countries: list[str] = Field(default_factory=list)
    workplace_type: str = "unknown"
    is_remote: bool = False
    requires_relocation: bool = False
    employment_type: str | None = None
    seniority_min_yoe: int | None = None
    seniority_max_yoe: int | None = None
    compensation: CompensationDTO = Field(default_factory=CompensationDTO)
    opens_on: date | None = None
    deadline_on: date | None = None
    deadline_at: datetime | None = None
    deadline_timezone: str | None = None
    deadline_precision: DeadlinePrecision = DeadlinePrecision.unknown
    published_at: datetime | None = None
    employment_conflict: bool = False
    source_payload: dict[str, Any] = Field(default_factory=dict)
    evidence_excerpt: str | None = None
    is_fixture: bool = False
