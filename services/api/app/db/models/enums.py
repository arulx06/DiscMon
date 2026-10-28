from __future__ import annotations

import enum


class StrEnum(enum.StrEnum):
    pass


class EmploymentStage(StrEnum):
    prejoin = "prejoin"
    employed = "employed"


class EligibilityStatus(StrEnum):
    verified_yes = "verified_yes"
    verified_no = "verified_no"
    unknown = "unknown"
    not_applicable = "not_applicable"


class LifeState(StrEnum):
    new = "new"
    open = "open"
    upcoming = "upcoming"
    closed = "closed"
    expired_unverified = "expired_unverified"
    archived = "archived"


class UserDecision(StrEnum):
    unreviewed = "unreviewed"
    watch = "watch"
    prepare = "prepare"
    research = "research"
    apply = "apply"
    applied = "applied"
    interviewing = "interviewing"
    rejected = "rejected"
    ignored = "ignored"
    completed = "completed"


class RecommendationBucket(StrEnum):
    act_now = "act_now"
    prepare_early = "prepare_early"
    keep_on_radar = "keep_on_radar"
    needs_verification = "needs_verification"
    archive = "archive"
    excluded = "excluded"


class SourceKind(StrEnum):
    ats_greenhouse = "ats_greenhouse"
    ats_lever = "ats_lever"
    ats_ashby = "ats_ashby"
    rss = "rss"
    github = "github"
    static_html = "static_html"
    changedetection = "changedetection"
    manual = "manual"
    newsletter = "newsletter"
    discovery_search = "discovery_search"


class Officialness(StrEnum):
    official = "official"
    credible_aggregator = "credible_aggregator"
    unknown = "unknown"


class ApprovalStatus(StrEnum):
    candidate = "candidate"
    approved = "approved"
    rejected = "rejected"
    retired = "retired"


class LegalReviewStatus(StrEnum):
    pending = "pending"
    approved = "approved"
    rejected = "rejected"


class HealthStatus(StrEnum):
    healthy = "healthy"
    stale = "stale"
    failing = "failing"
    paused = "paused"
    unknown = "unknown"


class JobState(StrEnum):
    queued = "queued"
    running = "running"
    succeeded = "succeeded"
    retry_wait = "retry_wait"
    dead = "dead"


class JobKind(StrEnum):
    ingest_source = "ingest_source"
    source_test = "source_test"
    generate_digest = "generate_digest"
    deliver_alert = "deliver_alert"
    sheets_sync = "sheets_sync"
    inspect_url = "inspect_url"
    rescore = "rescore"


class RevisionType(StrEnum):
    created = "created"
    updated = "updated"
    reopened = "reopened"
    closed_candidate = "closed_candidate"
    closed_confirmed = "closed_confirmed"


class DeadlinePrecision(StrEnum):
    exact = "exact"
    date_only = "date_only"
    month_only = "month_only"
    unknown = "unknown"


class CredibilityLevel(StrEnum):
    high = "high"
    medium = "medium"
    low = "low"
    unknown = "unknown"


class OpportunityType(StrEnum):
    job = "job"
    fellowship = "fellowship"
    residency = "residency"
    mentorship = "mentorship"
    grant = "grant"
    hackathon = "hackathon"
    competition = "competition"
    programme = "programme"
    founder_programme = "founder_programme"
    other = "other"


class AlertStatus(StrEnum):
    pending = "pending"
    sent = "sent"
    failed = "failed"
    suppressed = "suppressed"


class AlertKind(StrEnum):
    immediate = "immediate"
    deadline = "deadline"
    digest = "digest"


class DigestKind(StrEnum):
    daily = "daily"
    weekly = "weekly"


class SyncStatus(StrEnum):
    pending = "pending"
    in_progress = "in_progress"
    synced = "synced"
    failed = "failed"
    retired = "retired"


class HardGateStatus(StrEnum):
    passed = "passed"
    excluded = "excluded"
    needs_verification = "needs_verification"
