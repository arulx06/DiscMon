# DiscMon progress

Date: 2026-10-28
Authority: `docs/specification.md`

## Current status

M0-M4 implementation is present and exercised against real PostgreSQL,
Docker Compose and two real job boards. M5/M6 supporting work is partial:
backup/restore is implemented and drilled; Sheets outbox, changedetection
delivery and discovery-to-source promotion are not complete.

No gate is claimed solely from code inspection. Evidence below is from commands
run on 2026-10-28 in this workspace.

## Verified evidence

### Backend

```text
services/api> python -m pytest -q
41 passed, 1 warning in 22.27s

services/api> ruff check app tests scripts
All checks passed!

services/api> mypy app scripts
Success: no issues found in 56 source files
```

Tests cover fixture adapters, SSRF/NAT64 defenses, two-worker claim contention,
idempotent ingestion, one material revision = one alert, failed/partial scan
safety, three-absence closure, eligibility/time rules, API/review flow, digests,
ICS, CSV and brief idempotency.

Clean database drill:

```text
created discmon_clean
alembic upgrade head -> b76e2a98caca
seed_sources.py -> 17 registry candidates created, 0 skipped
sources=17, opportunities=0
```

### Real ingestion

- GitLab via Greenhouse: `seen 238`, `created 238`, `scan_complete=true`.
- OpenAI via Ashby: `seen 806`, `created 806`, `scan_complete=true`.
- Repeated runs for both sources returned `not_modified` with no duplicate
  opportunities.
- Database: 1,049 opportunities total, including 5 labelled fixtures and 1,044
  real records; 1,049 unique provider keys and official URLs; 1,049 assessments;
  1,049 revisions; 0 alerts.
- India eligibility: 241 `verified_no`, 767 `unknown`, 36 `verified_yes`.
- Professional eligibility: 3 `verified_yes`, 1,041 `unknown`.

### Frontend and E2E

```text
apps/web> npx playwright test
4 passed (7.4s)
```

Projects: `desktop-1440` and `mobile-360`. The review flow uses an explicitly
labelled demo fixture, saves a decision and note, verifies persistence, and
checks core pages for horizontal overflow.

### Live digest

```text
POST /v1/digests/generate?kind=daily
200; created=true
id=fb3a73e8-caac-4700-a6be-48d8e8db752c
sent_status=generated
opportunity_ids=15
```

The generated digest contains no `[Demo]` content. The seeded demo digest for
the previous day (`46ad1616-e1e2-44b6-b564-33a22cada500`, 5 fixtures) is
labelled `Demo digest` in the UI. The real digest detail page is not labelled
demo.

### Backup and restore

```text
bash scripts/backup.sh
Backup written: backups/discmon-20261028T160531Z.dump.gz

bash scripts/restore.sh backups/discmon-20261028T160531Z.dump.gz discmon_restore
opportunities=1049, opportunity_sources=1049, reviews=9, digests=2,
alembic_version=b76e2a98caca
Restore verified in discmon_restore. Live database discmon was not modified.
```

### Runtime

```text
docker compose ps
api        Up (healthy)   127.0.0.1:8000
postgres   Up (healthy)   127.0.0.1:55432
web        Up             127.0.0.1:3000
worker     Up
scheduler  Up

GET /health/live  -> 200
GET /health/ready -> 200
GET /             -> 200
```

## Gate status

| Gate | Status | Evidence / remaining work |
|---|---|---|
| M0 | Partial | Compose build/health, clean database migration/seed, full pytest and Next production build verified. CI workflow has not been executed here; a clean-clone run has not been recorded. |
| M1 | Verified | Two permitted real boards ingested; repeated scans create no duplicates; fixtures cover all adapters. |
| M2 | Verified | Hard gates, unknown handling, date-only deadlines, one-revision/one-alert, failure safety and closure tests pass. |
| M3 | Verified | Playwright 360px/1440px review and overflow journeys pass against the built web app. |
| M4 | Verified | Digest, ICS, CSV and Markdown brief tests pass; one material revision alert dedup tests pass; live digest excludes fixtures. |
| M5 | Partial | Sheets outbox, changedetection shared-secret delivery and discovery promotion remain. |
| M6 | Partial | Backup/restore implemented and drilled. Hardening/deployment review remains. |

## Known gaps

- CI has not been run in this environment. Do not describe it as green.
- A fresh-clone Compose run has not been recorded; clean database migration and
  seeding were verified, but the current Compose volume is not empty.
- Sheets synchronization is not implemented end to end.
- changedetection webhook delivery and discovery promotion are not complete.
- No end-to-end delivery test exists for Telegram/SMTP; in-app alerts are
  implemented and tested.
- The demo registry digest includes fixture records by design and is visibly
  labelled. Real digests exclude fixtures.

## Next

1. Run M5/M6 work only if required after M0-M4 review: Sheets outbox worker,
   changedetection delivery, discovery promotion, and a clean-clone CI run.
2. Record CI output and a clean-checkout drill in this file before claiming M0.
3. Keep real source runs and failure visibility in the acceptance report.
