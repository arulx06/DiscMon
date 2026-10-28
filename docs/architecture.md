# DiscMon architecture

## One-way authority

```text
approved source -> fetch -> parse (no DB writes) -> normalize -> canonicalize
-> transactional ingest -> revisions -> assessment -> alerts/digests -> UI/exports
```

PostgreSQL is the canonical store. The Next.js UI, Telegram/SMTP, ICS, Markdown
and the optional Sheets mirror are all downstream. Human decisions are written
through the owner API and audited; no external assistant can mutate records
implicitly.

## Processes

| Process | Responsibility |
|---|---|
| `api` | REST API, validation, transactional writes, SSE-free JSON |
| `worker` | Claims queued jobs, executes adapters and durable post-processing |
| `scheduler` | Elected by Postgres advisory lock; enqueues stable due-source jobs |
| `web` | Next.js server components and same-origin API proxy |
| `postgres` | Data, queue and advisory locks |
| `changedetection` | Optional trusted watch service, profile only |

## Ingestion transaction

1. Adapter fetches with conditional headers, SSRF defense and host limits.
2. Parser returns Pydantic `NormalizedCandidate` values; it never writes.
3. Pipeline writes `raw_evidence` and `source_runs` metadata.
4. Canonicalization selects provider identity or a normalized official URL.
5. One transaction upserts organizations/opportunities/source links.
6. Material-field hash comparison creates revisions only when justified.
7. Deterministic assessment records rule/profile versions and evidence refs.
8. Alert orchestration inserts a unique dedup key before delivery attempts.

A successful scan records completeness. Absence only advances a per-link
counter when the whole board was fetched. Three consecutive complete absences
produce `closed_candidate`; confirmation or a fourth complete absence produces
`closed_confirmed`. Failed or partial scans cannot advance closure.

## Queue

`jobs.idempotency_key` is unique. Workers claim with:

```sql
SELECT id FROM jobs
WHERE state = 'queued' AND available_at <= now()
ORDER BY available_at
FOR UPDATE SKIP LOCKED
LIMIT 1;
```

The claim and state transition happen in one transaction. Leases expire, are
recovered, and poison jobs become `dead` after bounded attempts. Retries use
stored idempotency and never duplicate alerts.

## Time

All instants are UTC `TIMESTAMPTZ`. Presentation uses Asia/Kolkata. A deadline
has a calendar date, an optional exact timestamp, a timezone and one precision:
`exact`, `date_only`, `month_only` or `unknown`. `date_only` explicitly means
the cutoff time is unknown.

## Evidence

Every opportunity source link points at a raw evidence record containing the
URL, fetch time, HTTP metadata, content hash, excerpt and optional retention
path. Revisions store normalized snapshots and material diffs. Every alert can
be traced alert -> revision -> evidence -> source run.

## Deployment shape

Docker Compose on one host. Postgres is not published publicly. The web and API
are private (Tailscale Serve or an authenticated reverse proxy). Changedetection
is opt-in through a Compose profile. The core stack needs no AI, Sheets or
Telegram credential.
