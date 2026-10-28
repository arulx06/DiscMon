from __future__ import annotations

import hashlib
import json
from datetime import date, datetime
from enum import Enum
from typing import Any

from app.db.models.opportunity import Opportunity

MATERIAL_FIELDS = [
    "title",
    "organization",
    "opportunity_type",
    "official_url",
    "application_url",
    "location_text",
    "country_codes",
    "allowed_remote_countries",
    "workplace_type",
    "requires_relocation",
    "employment_conflict",
    "employment_type",
    "professional_eligibility",
    "india_eligibility",
    "student_only",
    "student_eligibility",
    "opens_on",
    "deadline_on",
    "deadline_at",
    "deadline_timezone",
    "deadline_precision",
    "monetary_value_json",
    "requirements_summary",
    "seniority_min_yoe",
    "seniority_max_yoe",
    "skills",
]


def _jsonable(value: Any) -> Any:
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, dict):
        return {str(key): _jsonable(item) for key, item in sorted(value.items())}
    if isinstance(value, (list, tuple)):
        return [_jsonable(item) for item in value]
    return value


def material_snapshot(opportunity: Opportunity, organization_name: str | None = None) -> dict:
    snapshot = {}
    for field in MATERIAL_FIELDS:
        if field == "organization":
            snapshot[field] = organization_name
        else:
            snapshot[field] = _jsonable(getattr(opportunity, field, None))
    return snapshot


def snapshot_hash(snapshot: dict) -> str:
    serialized = json.dumps(snapshot, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


def diff_snapshots(previous: dict | None, current: dict) -> dict:
    if not previous:
        return {}
    diff = {}
    for key, value in current.items():
        old = previous.get(key)
        if old != value:
            diff[key] = {"old": old, "new": value}
    return diff
