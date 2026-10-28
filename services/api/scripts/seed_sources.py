"""Seed the source registry and, optionally, labelled demo fixtures.

Usage:
    python scripts/seed_sources.py            # import registry candidates only
    python scripts/seed_sources.py --demo     # also create clearly labelled demo records

The registry import never enables a source. Approval and legal review stay
pending until a human completes them in the UI.
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import os
import sys
from datetime import timedelta
from pathlib import Path
from typing import Any

import yaml
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.assessment import Assessment
from app.db.models.digest import Digest
from app.db.models.enums import (
    ApprovalStatus,
    CredibilityLevel,
    DeadlinePrecision,
    DigestKind,
    EligibilityStatus,
    HardGateStatus,
    HealthStatus,
    LegalReviewStatus,
    LifeState,
    Officialness,
    OpportunityType,
    RecommendationBucket,
    RevisionType,
    SourceKind,
)
from app.db.models.evidence import RawEvidence
from app.db.models.opportunity import (
    Opportunity,
    OpportunityRevision,
    OpportunitySource,
    Organization,
)
from app.db.models.source import Source
from app.db.models.user import UserProfile
from app.db.session import async_session_factory, dispose_engine
from app.services.digests import digest_window
from app.services.time import now_utc

DEMO_SOURCE_NAME = "DiscMon Demo (fixture data)"
DEMO_ORG_NAME = "DiscMon Demo (fixture)"
DEMO_ORG_DOMAIN = "example.org"


def registry_path(explicit: str | None) -> Path:
    resolved = Path(__file__).resolve()
    repository_candidate = (
        resolved.parents[3] / "source_registry_seed.yaml"
        if len(resolved.parents) > 3
        else None
    )
    candidates = [
        Path(explicit) if explicit else None,
        (
            Path(os.environ["SOURCE_REGISTRY_SEED"])
            if os.environ.get("SOURCE_REGISTRY_SEED")
            else None
        ),
        Path("/app/source_registry_seed.yaml"),
        Path.cwd() / "source_registry_seed.yaml",
        repository_candidate,
    ]
    for candidate in candidates:
        if candidate is not None and candidate.is_file():
            return candidate
    raise FileNotFoundError("source_registry_seed.yaml not found; pass --file")


def load_registry(path: Path) -> list[dict[str, Any]]:
    payload = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict) or not isinstance(payload.get("sources"), list):
        raise ValueError("Registry file must contain a sources list")
    entries: list[dict[str, Any]] = []
    for item in payload["sources"]:
        if isinstance(item, dict):
            entries.append(item)
    return entries


async def seed_registry(session: AsyncSession, entries: list[dict[str, Any]]) -> tuple[int, int]:
    created = 0
    skipped = 0
    for entry in entries:
        root_url = str(entry.get("url") or "").strip()
        name = str(entry.get("name") or "").strip()
        adapter = str(entry.get("preferred_adapter") or "").strip()
        if not root_url or not name:
            continue
        existing = await session.scalar(select(Source.id).where(Source.root_url == root_url))
        if existing is not None:
            skipped += 1
            continue
        try:
            kind = SourceKind(adapter)
        except ValueError:
            kind = SourceKind.manual
        session.add(
            Source(
                name=name,
                source_kind=kind,
                root_url=root_url,
                config_json={
                    "seed_category": entry.get("category"),
                    "seed_notes": entry.get("notes"),
                    "seed_adapter": adapter or None,
                },
                officialness=Officialness.unknown,
                enabled=False,
                approval_status=ApprovalStatus.candidate,
                legal_review_status=LegalReviewStatus.pending,
                health_status=HealthStatus.unknown,
            )
        )
        created += 1
    return created, skipped


DEMO_ROWS: list[dict[str, Any]] = [
    {
        "slug": "senior-backend",
        "title": "[Demo] Senior Backend Engineer",
        "type": OpportunityType.job,
        "description": (
            "Demo fixture only. Build distributed systems, PostgreSQL services and cloud "
            "platform tooling. Open to working professionals based in India."
        ),
        "requirements": "Demo fixture only. 5+ years backend engineering experience.",
        "location": "Bengaluru, India",
        "workplace": "hybrid",
        "countries": ["IN"],
        "remote_countries": [],
        "professional": EligibilityStatus.verified_yes,
        "india": EligibilityStatus.verified_yes,
        "student_only": False,
        "credibility": CredibilityLevel.high,
        "score": 91,
        "bucket": RecommendationBucket.act_now,
        "gate": HardGateStatus.passed,
        "confidence": 0.91,
        "reason": "Strong skill match, verified professional and India eligibility.",
        "deadline_days": 12,
        "deadline_precision": DeadlinePrecision.exact,
        "compensation": "INR 45,00,000 per year",
        "decision": "unreviewed",
    },
    {
        "slug": "maintainer-residency",
        "title": "[Demo] Open Source Maintainer Residency",
        "type": OpportunityType.residency,
        "description": (
            "Demo fixture only. Twelve-week residency for maintainers. India eligibility "
            "has not been verified in the source material."
        ),
        "requirements": "Demo fixture only. Maintained project with public contributions.",
        "location": "Remote",
        "workplace": "remote",
        "countries": [],
        "remote_countries": [],
        "professional": EligibilityStatus.verified_yes,
        "india": EligibilityStatus.unknown,
        "student_only": False,
        "credibility": CredibilityLevel.medium,
        "score": 74,
        "bucket": RecommendationBucket.needs_verification,
        "gate": HardGateStatus.needs_verification,
        "confidence": 0.62,
        "reason": "Remote wording does not establish India eligibility; verify before acting.",
        "deadline_month_offset": 1,
        "deadline_precision": DeadlinePrecision.month_only,
        "compensation": "Stipend not published",
        "decision": "watch",
    },
    {
        "slug": "platform-fellowship",
        "title": "[Demo] Platform Engineering Fellowship",
        "type": OpportunityType.fellowship,
        "description": "Demo fixture only. Students-only fellowship; excluded for this profile.",
        "requirements": "Demo fixture only. Currently enrolled students only.",
        "location": "Pune, India",
        "workplace": "onsite",
        "countries": ["IN"],
        "remote_countries": [],
        "professional": EligibilityStatus.verified_no,
        "india": EligibilityStatus.verified_yes,
        "student_only": True,
        "credibility": CredibilityLevel.high,
        "score": 28,
        "bucket": RecommendationBucket.excluded,
        "gate": HardGateStatus.excluded,
        "confidence": 0.88,
        "reason": "Student-only eligibility conflicts with the saved profile.",
        "deadline_days": 30,
        "deadline_precision": DeadlinePrecision.date_only,
        "compensation": None,
        "decision": "ignored",
    },
    {
        "slug": "staff-sre",
        "title": "[Demo] Staff Site Reliability Engineer",
        "type": OpportunityType.job,
        "description": (
            "Demo fixture only. Fully remote role. The posting does not state which "
            "countries may work remotely."
        ),
        "requirements": "Demo fixture only. Kubernetes, Linux and incident response.",
        "location": "Remote",
        "workplace": "remote",
        "countries": [],
        "remote_countries": [],
        "professional": EligibilityStatus.unknown,
        "india": EligibilityStatus.unknown,
        "student_only": False,
        "credibility": CredibilityLevel.medium,
        "score": 68,
        "bucket": RecommendationBucket.needs_verification,
        "gate": HardGateStatus.needs_verification,
        "confidence": 0.5,
        "reason": "isRemote=true alone is not evidence of India eligibility.",
        "deadline_precision": DeadlinePrecision.unknown,
        "compensation": "USD 150,000 per year (demo)",
        "decision": "research",
    },
    {
        "slug": "cloud-infrastructure",
        "title": "[Demo] Cloud Infrastructure Engineer",
        "type": OpportunityType.job,
        "description": (
            "Demo fixture only. Platform team working on cloud networking and databases. "
            "Verified open to professionals in India."
        ),
        "requirements": "Demo fixture only. Terraform, PostgreSQL, Go or Python.",
        "location": "Gurugram, India",
        "workplace": "hybrid",
        "countries": ["IN"],
        "remote_countries": [],
        "professional": EligibilityStatus.verified_yes,
        "india": EligibilityStatus.verified_yes,
        "student_only": False,
        "credibility": CredibilityLevel.high,
        "score": 82,
        "bucket": RecommendationBucket.prepare_early,
        "gate": HardGateStatus.passed,
        "confidence": 0.84,
        "reason": "Good platform fit; deadline allows preparation time.",
        "deadline_days": 25,
        "deadline_precision": DeadlinePrecision.exact,
        "compensation": "INR 32,00,000 per year",
        "decision": "prepare",
    },
]


async def ensure_demo_source(session: AsyncSession) -> Source:
    source = await session.scalar(select(Source).where(Source.name == DEMO_SOURCE_NAME))
    if source is None:
        source = Source(
            name=DEMO_SOURCE_NAME,
            source_kind=SourceKind.manual,
            root_url="https://example.org/discmon-demo",
            config_json={
                "demo_fixture": True,
                "notice": "Labelled demo data for UI review. Not a real opportunity.",
            },
            officialness=Officialness.unknown,
            enabled=False,
            approval_status=ApprovalStatus.candidate,
            legal_review_status=LegalReviewStatus.pending,
            health_status=HealthStatus.unknown,
        )
        session.add(source)
        await session.flush()
    return source


async def ensure_demo_org(session: AsyncSession) -> Organization:
    organization = await session.scalar(
        select(Organization).where(Organization.canonical_domain == DEMO_ORG_DOMAIN)
    )
    if organization is None:
        organization = Organization(
            canonical_name=DEMO_ORG_NAME,
            canonical_domain=DEMO_ORG_DOMAIN,
            aliases=["DiscMon Demo"],
            industry_tags=["demo"],
        )
        session.add(organization)
        await session.flush()
    return organization


def demo_deadline(row: dict[str, Any], now) -> tuple[Any, Any, Any]:
    precision = row["deadline_precision"]
    if precision is DeadlinePrecision.exact:
        deadline_at = now + timedelta(days=int(row["deadline_days"]))
        deadline_at = deadline_at.replace(minute=30, second=0, microsecond=0)
        return deadline_at.date(), deadline_at, "Asia/Kolkata"
    if precision is DeadlinePrecision.date_only:
        return (now + timedelta(days=int(row["deadline_days"]))).date(), None, None
    if precision is DeadlinePrecision.month_only:
        month = now.month + int(row.get("deadline_month_offset", 1))
        year = now.year + (month - 1) // 12
        month = (month - 1) % 12 + 1
        return now.replace(year=year, month=month, day=1).date(), None, None
    return None, None, None


async def seed_demo(session: AsyncSession) -> int:
    source = await ensure_demo_source(session)
    organization = await ensure_demo_org(session)
    now = now_utc()
    created = 0
    demo_ids: list[str] = []
    for row in DEMO_ROWS:
        provider_key = f"demo:{row['slug']}"
        existing = await session.scalar(
            select(Opportunity.id).where(Opportunity.provider_key == provider_key)
        )
        if existing is not None:
            demo_ids.append(str(existing))
            continue
        deadline_on, deadline_at, deadline_timezone = demo_deadline(row, now)
        opportunity = Opportunity(
            provider_key=provider_key,
            provider_source_kind=SourceKind.manual,
            organization_id=organization.id,
            title=row["title"],
            opportunity_type=row["type"],
            description_summary=row["description"],
            requirements_summary=row["requirements"],
            skills=[],
            country_codes=row["countries"],
            allowed_remote_countries=row["remote_countries"],
            workplace_type=row["workplace"],
            location_text=row["location"],
            official_url=f"https://example.org/discmon-demo/{row['slug']}",
            application_url=f"https://example.org/discmon-demo/{row['slug']}/apply",
            deadline_on=deadline_on,
            deadline_at=deadline_at,
            deadline_timezone=deadline_timezone,
            deadline_precision=row["deadline_precision"],
            compensation_summary=row["compensation"],
            professional_eligibility=row["professional"],
            india_eligibility=row["india"],
            student_only=row["student_only"],
            student_eligibility=(
                EligibilityStatus.verified_yes
                if row["student_only"]
                else EligibilityStatus.verified_no
            ),
            eligibility_reasons_json={
                "demo": "Fixture evidence. Not a real eligibility determination."
            },
            eligibility_checked_at=now,
            credibility_level=row["credibility"],
            life_state=LifeState.open,
            first_seen_at=now - timedelta(days=3),
            last_seen_at=now - timedelta(hours=1),
            last_verified_at=now - timedelta(hours=1),
            last_material_change_at=now - timedelta(days=2),
            user_decision=row["decision"],
            is_fixture=True,
        )
        session.add(opportunity)
        await session.flush()

        snapshot = {
            "title": row["title"],
            "deadline_on": deadline_on.isoformat() if deadline_on else None,
            "deadline_at": deadline_at.isoformat() if deadline_at else None,
            "deadline_precision": row["deadline_precision"].value,
            "demo": True,
        }
        revision = OpportunityRevision(
            opportunity_id=opportunity.id,
            revision_number=1,
            normalized_snapshot_json=snapshot,
            normalized_hash=hashlib.sha256(repr(snapshot).encode()).hexdigest(),
            material_diff_json={},
            observed_at=now - timedelta(days=3),
            evidence_ids=[],
            revision_type=RevisionType.created,
        )
        session.add(revision)
        await session.flush()
        opportunity.current_revision_id = revision.id
        opportunity.current_revision_number = 1

        evidence = RawEvidence(
            source_id=source.id,
            source_url=source.root_url,
            canonical_url=opportunity.official_url,
            fetched_at=now - timedelta(hours=1),
            content_type="text/html",
            content_hash=hashlib.sha256(opportunity.official_url.encode()).hexdigest(),
            extracted_text_excerpt=row["description"][:600],
            source_license_or_terms_note="Demo fixture only; not fetched from a live source.",
        )
        session.add(evidence)
        await session.flush()
        session.add(
            OpportunitySource(
                opportunity_id=opportunity.id,
                source_id=source.id,
                source_external_id=row["slug"],
                source_item_url=opportunity.official_url,
                raw_evidence_id=evidence.id,
                first_seen_at=now - timedelta(days=3),
                last_seen_at=now - timedelta(hours=1),
            )
        )
        session.add(
            Assessment(
                opportunity_id=opportunity.id,
                revision_id=revision.id,
                rules_version="v1",
                profile_version=1,
                score_total=row["score"],
                factor_scores_json={
                    "skills": row["score"] - 5,
                    "seniority": row["score"] - 10,
                    "location": row["score"] - 8,
                    "timeline": 80,
                },
                hard_gate_status=row["gate"],
                professional_eligibility_state=row["professional"],
                india_eligibility_state=row["india"],
                evidence_refs_json=[{"type": "demo_fixture"}],
                confidence=row["confidence"],
                recommended_bucket=row["bucket"],
                recommendation_reason=row["reason"],
            )
        )
        demo_ids.append(str(opportunity.id))
        created += 1

    if demo_ids:
        daily = await session.scalar(
            select(Digest.id).where(
                Digest.digest_kind == DigestKind.daily,
                Digest.sent_status == "demo",
            )
        )
        if daily is None:
            start, end = digest_window(DigestKind.daily, now - timedelta(days=1))
            lines = [
                "# [Demo] Daily digest",
                "",
                "Labelled fixture data, not real opportunities.",
                "",
            ]
            for row in DEMO_ROWS:
                lines.append(f"- {row['title']} — {row['reason']}")
            session.add(
                Digest(
                    period_start=start,
                    period_end=end,
                    digest_kind=DigestKind.daily,
                    content_md="\n".join(lines),
                    content_json={"demo": True},
                    opportunity_ids=demo_ids,
                    sent_status="demo",
                )
            )
    return created


async def run(args: argparse.Namespace) -> None:
    path = registry_path(args.file)
    entries = load_registry(path)
    try:
        async with async_session_factory() as session:
            existing_profile = await session.scalar(select(UserProfile.id).limit(1))
            if existing_profile is None:
                session.add(UserProfile())
                await session.flush()
            created, skipped = await seed_registry(session, entries)
            demo_created = await seed_demo(session) if args.demo else 0
            await session.commit()
    finally:
        await dispose_engine()
    print(
        f"Registry candidates created={created} skipped={skipped}; "
        f"demo fixtures created={demo_created}"
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--file", help="Path to source_registry_seed.yaml")
    parser.add_argument("--demo", action="store_true", help="Create labelled demo fixtures")
    args = parser.parse_args()
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    asyncio.run(run(args))


if __name__ == "__main__":
    main()
