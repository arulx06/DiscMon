# DiscMon progress

Date: 2026-10-28
Authority: `docs/specification.md`

## Current status

M0-M4 implementation is present and exercised against real PostgreSQL,
Docker Compose and two real job boards. M5/M6 supporting code is implemented
and fixture-tested, but not yet proven by the milestone acceptance runs:
external integrations are unconfigured, no live non-ATS programme has been
discovered and mirrored, and no seven-day reliability run or worker-crash drill
has been recorded.

No gate is claimed solely from code inspection. Evidence below is from commands
run on 2026-10-28 in this workspace.

## Verified evidence

### Backend

```text
services/api> python -m pytest -q
49 passed, 1 warning in 34.14s

services/api> ruff check app tests scripts
All checks passed!

services/api> mypy app scripts
Success: no issues found in 61 source files
```

The warning is a `feedparser` deprecation warning, not a failure. Tests cover
fixture adapters, SSRF/NAT64 defenses, two-worker claim contention, idempotent
ingestion, volatile compensation stability, one material revision = one alert,
failed/partial scan safety, three-absence closure, eligibility/time rules,
API/review/watchlist flow, discovery extraction/promotion, changedetection
signature/idempotency, Sheets outbox isolation, SMTP delivery, digests, ICS,
CSV and brief idempotency.

Clean database drill:

```text
alembic upgrade head -> d4a7c1e9f210
seed_sources.py -> 17 registry candidates created, 0 skipped
sources=17, opportunities=0
```

The disposable database was dropped after verification.

### Live schema and service health

```text
live discmon:             d4a7c1e9f210 (head)
alembic check:            no new upgrade operations detected
GET /health/ready:        {"status":"ready","database":"ok"}
GET /v1/integrations/status:
changedetection=off, telegram=off, smtp=off, sheets=off, ai=off
```

`web` returns HTTP 200. The changedetection, Telegram, SMTP, Sheets and AI
integrations have no live credentials or services in this environment.

### Real ingestion

- GitLab via Greenhouse: `seen 238`, `created 238`, `scan_complete=true`.
- OpenAI via Ashby: `seen 806`, `created 806`, `scan_complete=true`.
- Repeated runs for both sources retained the same provider identities; they
  did not duplicate opportunities.
- Verification scans after the first ingestion created four real opportunities
  and one legitimate material update (`Support Operations Manager`, title and
  requirements changed).
- Ashby compensation component IDs/order vary between responses. Two false
  material revisions were removed and their current revisions restored. The
  ingestion path now ignores `monetary_value_json.raw` order/IDs when deciding
  materiality; a regression test covers this.
- Post-fix scans created no additional false revisions.
- Current database: 1,053 opportunities total, including 5 labelled fixtures
  and 1,048 real records; 1,053 unique provider keys and official URLs; 1,053
  source links; 1,054 revisions; 2,900 assessments; 14 reviews; 0 alerts.
- Rescans append assessment history rows. This has not been deduplicated, but
  no duplicate opportunities or provider identities were created.
- India eligibility: 242 `verified_no`, 772 `unknown`, 39 `verified_yes`.
- Professional eligibility: 1 `verified_no`, 1,046 `unknown`, 6 `verified_yes`.
- The new records remain `unknown` for India/professional eligibility and did
  not trigger alerts. The remote location was not treated as India evidence.

### Frontend and E2E

```text
apps/web> npm run typecheck
apps/web> npm run lint
apps/web> npm run build
apps/web> npm run test:e2e
4 passed (6.8s)

Projects: desktop-1440 and mobile-360.
```

Playwright verifies the labelled demo review flow and core-page overflow. A
manual browser pass also verified:

- `/health` integration status cards and job visibility.
- `/discover` renders the add-candidate form; no candidates existed, so
  approve/reject/promote controls were not exercised.
- Source detail shows JSON config editing and a disabled “Scan for links”
  control for an API-backed source without discovery config.
- A real new record, `Communications Lead, Cyber` (OpenAI), was reviewed as
  `research` with an honest eligibility-verification next action and a
  follow-up date. `/watchlist` rendered it under Research with the action and
  follow-up.

The live discovery candidate scan/promotion path was not exercised because no
enabled live source has `config_json.discovery`.

### Backup and restore

```text
bash scripts/backup.sh
Backup written: backups/discmon-20261028T173345Z.dump.gz

bash scripts/restore.sh backups/discmon-20261028T173345Z.dump.gz discmon_restore_final
opportunities=1053, opportunity_sources=1053, reviews=14, digests=2,
alembic_version=d4a7c1e9f210
Restore verified in discmon_restore_final. Live database discmon was not modified.
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
| M1 | Verified | Two permitted real boards ingested; repeated scans create no duplicate opportunities; fixtures cover all adapters. |
| M2 | Verified | Hard gates, unknown handling, date-only deadlines, one-revision/one-alert, failure safety and closure tests pass. |
| M3 | Verified | Playwright 360px/1440px review and overflow journeys pass against the built web app. |
| M4 | Verified | Digest, ICS, CSV and Markdown brief tests pass; one material revision alert dedup tests pass; live digest excludes fixtures. |
| M5 | Partial | Discovery UI/API, changedetection webhook, Sheets outbox, SMTP and GitHub watch paths are fixture-tested. Live non-ATS discovery, verified promotion, Sheets mirroring and external delivery are not verified. |
| M6 | Partial | Backup/restore implemented and drilled at the current migration. CI, seven-day operation, worker-crash recovery, load/memory checks and the source coverage audit remain. |

## Known gaps

- CI has not been run in this environment. Do not describe it as green.
- A fresh-clone Compose run has not been recorded; clean database migration and
  seeding were verified, but the current Compose volume is not empty.
- changedetection, Telegram, SMTP and Google Sheets have no live credentials or
  services here. Their code paths are fixture-tested only.
- No live non-ATS programme has completed discovery, approval, verification,
  scoring and mirroring.
- Discovery candidate scan/promotion was not exercised against a live source.
- Alerts table is empty because no newly eligible record triggered immediate
  delivery during verification.
- No seven-day run, simulated worker-crash recovery, load test or memory
  profile is recorded.
- Repeated scans append assessment rows; storage growth needs a retention or
  deduplication decision.
- The source coverage audit and `raw_evidence` retention audit remain.
- The demo registry digest includes fixture records by design and is visibly
  labelled. Real digests exclude fixtures.

## Next

1. Run the CI workflow, then record a clean-checkout Compose drill with an empty
   volume.
2. Configure changedetection and Sheets in a disposable environment and execute
   the M5 non-ATS discovery-to-mirror acceptance path.
3. Run the M6 seven-day soak, worker-crash recovery, load/memory checks and
   source coverage audit before claiming M5/M6.
