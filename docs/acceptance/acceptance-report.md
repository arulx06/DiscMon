# Acceptance report

Date: 2026-10-28
Specification: `docs/specification.md`
Status: M0-M4 checks exercised here; M5/M6 code paths are fixture-tested only;
external integrations and the M5/M6 acceptance runs remain unverified.

## Environment

- Windows host, Docker Desktop, PostgreSQL 18 container on `127.0.0.1:55432`.
- Python 3.12 virtual environment at `.venv`.
- Next.js 16 production build in the `web` container on `127.0.0.1:3000`.
- API container on `127.0.0.1:8000`; worker and scheduler running.

## Backend verification

Command:

```powershell
Push-Location services\api
& ..\..\.venv\Scripts\python -m pytest -q
& ..\..\.venv\Scripts\python -m ruff check app tests scripts
& ..\..\.venv\Scripts\python -m mypy app scripts
Pop-Location
```

Result:

```text
49 passed, 1 warning in 34.14s
All checks passed!
Success: no issues found in 61 source files
```

The warning is a `feedparser` deprecation warning, not a test failure. The
suite includes discovery extraction/promotion, changedetection signature and
deduplication, Sheets outbox isolation, SMTP delivery, and the compensation
volatility regression.

## Clean database migration

A disposable `discmon_clean` database was created to exercise the documented
migration and registry seed path without touching live data.

```text
alembic upgrade head -> d4a7c1e9f210
seed_sources.py -> 17 registry candidates created, 0 skipped
sources=17, opportunities=0
```

The database was dropped after verification.

## Live schema

```text
live discmon:      d4a7c1e9f210 (head)
alembic check:     no new upgrade operations detected
```

The live migration was applied from `b76e2a98caca` after a fresh backup. The
`sync_state` table had no duplicate `(sheet_id, tab)` rows before the unique
constraint was added.

## Real ingestion

| Source | Adapter | First run | Repeated runs |
|---|---|---|---|
| GitLab | Greenhouse | 238 seen, 238 created, complete | no duplicate provider identities |
| OpenAI | Ashby | 806 seen, 806 created, complete | no duplicate provider identities |

Source records:

- GitLab: `ca3917d4-7995-4eca-b2f3-241e7233281c`
- OpenAI: `cc8f7c3b-36ae-43d8-a616-60276b05a441`

Verification scans created four real opportunities and one legitimate material
update. Ashby compensation component IDs/order vary between responses; two
false revisions were removed and their prior revisions restored. Ingestion now
ignores `monetary_value_json.raw` when deciding materiality, with a regression
test. Post-fix scans created no false updates.

Database totals:

```text
opportunities            1053  (1048 real + 5 fixtures)
unique provider_key      1053
unique official_url      1053
opportunity_sources      1053
assessments              2900
opportunity_revisions    1054
alerts                      0
```

Every rescan appends assessment rows. This has not been deduplicated; no
duplicate opportunities or provider identities were created.

Eligibility distribution:

```text
India:        verified_no=242, unknown=772, verified_yes=39
Professional: verified_no=1,   unknown=1046, verified_yes=6
```

This confirms no mass inference of India eligibility from remote location
alone. The four newly discovered records remain `unknown` for India and
professional eligibility.

## Digest and fixture exclusion

Command:

```powershell
POST http://127.0.0.1:8000/v1/digests/generate?kind=daily
```

Result recorded in the earlier run:

```text
200
id=fb3a73e8-caac-4700-a6be-48d8e8db752c
created=true
sent_status=generated
opportunity_ids=15
```

Checks:

- Real digest content contains no `[Demo]` marker.
- Demo digest `46ad1616-e1e2-44b6-b564-33a22cada500` has 5 fixture records.
- `/digests/46ad1616-e1e2-44b6-b564-33a22cada500` displays `Demo digest`.
- `/digests/fb3a73e8-caac-4700-a6be-48d8e8db752c` does not display the demo
  badge.
- Digest generation for the same window returns the existing real digest and
  does not create a duplicate.

## Frontend and E2E

Command:

```powershell
cd apps\web
npm run typecheck
npm run lint
npm run build
npm run test:e2e
```

Result:

```text
4 passed (6.8s)
```

Coverage:

- 1440px and 360px review flow.
- Demo fixtures visibly labelled before and after opening detail.
- Decision and note persist and appear in the filtered list.
- `/`, `/opportunities?include_fixtures=1`, `/sources` and `/health` return 200
  with no horizontal overflow.

Manual browser checks against the live production build:

- `/health` renders integration status for changedetection, Telegram, Email,
  Google Sheets and optional AI; all are off.
- `/discover` renders the add-candidate form. No candidates existed, so
  approve/reject/promote controls were not exercised live.
- Source detail renders JSON configuration editing. “Scan for links” is
  disabled for an API-backed source without discovery configuration.
- `Communications Lead, Cyber` (`47387b89-124b-4dcd-adec-f15866a8f187`,
  OpenAI) was saved as `research`, with next action
  “Verify India and professional eligibility from the source” and follow-up
  `2026-11-02`.
- `/watchlist` renders that record under Research with the next action and
  follow-up date.

No live discovery candidate was scanned or promoted because no enabled live
source has `config_json.discovery`.

## Service health

```text
docker compose ps:
api        Up (healthy)   127.0.0.1:8000
postgres   Up (healthy)   127.0.0.1:55432
web        Up             127.0.0.1:3000
worker     Up
scheduler  Up

GET /health/live   -> 200
GET /health/ready  -> {"status":"ready","database":"ok"}
GET /              -> 200
```

Integration status at verification:

```text
changedetection: disabled, webhook missing
telegram:        disabled
smtp:            disabled, host missing
sheets:          disabled, credentials missing, tab Opportunities
ai:              disabled, no provider
```

## Backup and restore

```powershell
bash scripts/backup.sh
bash scripts/restore.sh backups/discmon-20261028T173345Z.dump.gz discmon_restore_final
```

Result:

```text
Backup written: backups/discmon-20261028T173345Z.dump.gz

opportunities | opportunity_sources | reviews | digests | alembic_version
1053          | 1053                | 14      | 2       | d4a7c1e9f210

Restore verified in discmon_restore_final. Live database discmon was not modified.
```

## Safety checks covered by tests

- `isRemote=true` alone remains `unknown` for India eligibility.
- Student-only/2027 restrictions are detected and excluded.
- Date-only deadlines keep cutoff time unknown; ICS uses all-day events.
- Failed and partial scans never close records.
- Three complete absences create a closure candidate; confirmation closes.
- One material revision creates one alert with a unique dedup key.
- Volatile compensation metadata does not create a material revision.
- SSRF blocks loopback, private, link-local metadata and redirects to them.
- NAT64 public addresses are allowed only after validating the embedded IPv4.
- changedetection signatures, timestamps, replay dedup and body limits are
  enforced; a signal only enqueues a bounded source re-fetch.
- Sheets failures leave canonical ingestion and UI behavior unaffected.

## Not verified in this run

- CI workflow execution.
- Clean-clone Compose installation from an empty volume.
- Live changedetection, Telegram, SMTP, Sheets or AI integration.
- Non-ATS discovery through approval, verification, scoring and Sheets
  mirroring.
- Live discovery candidate promotion.
- An immediate alert triggered by a newly eligible record.
- Seven-day soak, worker-crash recovery, load test or memory profile.
- Source coverage audit and `raw_evidence` retention audit.

These are recorded as open items in `docs/PROGRESS.md`; they are not claimed as
passing.
