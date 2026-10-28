# DiscMon implementation plan

Date: 2026-10-28. Authority: `docs/specification.md` (copy of
`OPPORTUNITY_RADAR_IMPLEMENTATION_SPEC.md`).

## Mandatory P0 requirements

### Authentication, preferences and operations
- FR-001 private single-user access; disabled auth only on localhost.
- FR-002/003 editable, versioned profile with non-student status, location,
  employment stage, categories, alert limits, quiet hours and channels.
- FR-004 integration tests for source access and notification credentials
  without exposing secrets.
- FR-070/071/072/073 source health, retry/resume/dead-letter, backup and
  restore, CSV/JSON portability.

### Sources and ingestion
- FR-010 source registry CRUD and lifecycle.
- FR-011 Greenhouse, Lever, Ashby, RSS and GitHub adapters.
- FR-012 run due/one/retry with no overlapping duplicate jobs.
- FR-013 persistent fetch results, candidates and evidence.
- FR-014 per-host limits, retries, Retry-After, legal exclusion.
- FR-015 material revisions with notification deduplication.

### Opportunities and lifecycle
- FR-030 canonical opportunity detail and provenance.
- FR-031 opportunity life states and orthogonal user decisions.
- FR-032 provider-ID dedup plus cautious fuzzy review.
- FR-033 deadline precision/timezone; date-only never becomes a timestamp.
- FR-034 four-state eligibility per dimension with evidence.
- FR-035 history, verification freshness and closure confidence.

### Filtering, scoring and notification
- FR-040/041 deterministic hard gates; unknown never becomes yes.
- FR-042/043/044 versioned 100-point score and recommendation buckets.
- FR-045 explicit or planning-labelled lead time.
- FR-050/051/052/053/054/055 digests, immediate-alert gates, unique keys,
  Asia/Kolkata quiet hours, in-app plus Telegram/SMTP, digest contents.

### ChatGPT boundary
- FR-060/061/062 copy brief, Markdown/JSON export, no implicit DB mutation.

## Milestones

| Milestone | Scope in this repository | Exit evidence |
|---|---|---|
| M0 | Skeleton, Compose, migrations, health, CI, docs, fixtures | Compose health, pytest smoke, web build |
| M1 | Schema, adapters, queue, scheduler, source controls, dedup | Repeated fixture ingestion test, two real boards when network permits |
| M2 | Gates, scoring, revisions, evidence, closure | Negative eligibility tests, 3-scan closure test |
| M3 | Responsive UI journeys | Playwright 360/1440 flows |
| M4 | Alerts, digests, ICS, Markdown/ChatGPT brief | One revision = one alert test |
| M5 | GitHub/changedetection/candidates/Sheets outbox | Fixture programme discovery + sync failure isolation |
| M6 | Backups, hardening, deployment runbook | Restore drill and failure tests |
| M7 | Optional AI/search | Not required; disabled by default |

## Architecture summary

Modular monolith. FastAPI serves the owner API. A separate worker claims jobs
from PostgreSQL with `FOR UPDATE SKIP LOCKED`. A single elected scheduler owns
an advisory lock and enqueues stable source-check jobs. Next.js server
components and a server-side proxy call FastAPI; the browser never holds the
owner token. PostgreSQL is authoritative; Sheets is an outbox mirror.

## ERD (logical)

```text
user_profile 1---* assessments

sources 1---* source_runs
sources 1---* jobs
sources 1---* raw_evidence
sources 1---* opportunity_sources *---1 opportunities
organizations 1---* opportunities
opportunities 1---* opportunity_revisions
opportunities 1---* assessments
opportunities 1---* reviews
opportunities 1---* alerts
digests 1---* alerts
opportunities 1---* sync_outbox (logical entity)
discovery_candidates independent review queue
audit_events independent append-only log
```

## Endpoint map

Implemented under `/v1`: dashboard, profile, sources CRUD/test/run/runs,
discovery candidates/decision/inspect-url, opportunities list/detail/
revisions/review/rescore, deadlines and ICS, digests list/detail/generate,
alerts, health/sources, changedetection webhook, CSV/brief exports, Sheets
sync/status, admin jobs/retry and run-due. `/health/live` and `/health/ready`
are unauthenticated only for private/local operation.

## Phase order

1. M0 skeleton, settings, DB models and migration, health, CI.
2. M1 fetch safety, adapters, normalization, idempotent upsert, queue.
3. M2 rules, scoring, revisions, evidence, closure.
4. M3 API completion and responsive UI.
5. M4 digests, alerts, ICS and exports.
6. M5/M6 only after M0â€“M4 tests pass.

## Risks and mitigations

| Risk | Mitigation |
|---|---|
| Over-eager eligibility inference | Conservative deterministic parser, unknown default, negative tests |
| Duplicate alerts | DB unique dedup key; revisions only alert once |
| False closure | Scan completeness flag, 3 successful absences, confirmation |
| SSRF | HTTPS-only, DNS/IP validation, redirect revalidation, allowlist per source |
| ATS schema drift | Typed fixture parsers, diagnostics, source health status |
| Failed Sheets sync blocking ingest | Transactional outbox, worker isolation, DB authoritative |
| UI timezone/deadline ambiguity | Store date and timestamp separately with precision string |
| Source text prompt injection | Treat as data, sanitize rendering, no LLM execution path in MVP |
| Windows development friction | Docker Compose for Postgres; Python 3.12; documented commands |

## Acceptance checklist

- [ ] Fresh checkout runs with documented steps.
- [x] Repeated Greenhouse/Lever/Ashby fixture ingestion creates zero duplicates.
- [x] Student-only/2027-only roles never recommended.
- [x] `isRemote=true` without an India allowlist remains `unknown`.
- [x] Date-only deadline stores no fabricated cutoff.
- [x] Material revision creates one alert per channel; unchanged does not.
- [x] Failed/partial scans never close records; 3 successful absences do.
- [x] Two workers cannot claim the same job; alert keys are unique.
- [ ] Sheet failure cannot block ingestion.
- [x] 360px and 1440px owner journeys pass.
- [x] AI disabled leaves all core workflows working. All verification ran without AI credentials.
- [ ] Stale sources, failed jobs and backups are visible.
- [x] Backup restores into a clean database with ownership data intact.
