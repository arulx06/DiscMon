# Acceptance report

Date: 2026-10-28
Specification: `docs/specification.md`
Status: exercised checks pass; M5/M6 and CI remain outside this report.

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
41 passed, 1 warning in 22.27s
All checks passed!
Success: no issues found in 56 source files
```

The warning is a `feedparser` deprecation warning, not a test failure.

## Clean database migration

A disposable `discmon_clean` database was created to exercise the documented
migration and registry seed path without touching live data.

```text
alembic upgrade head -> b76e2a98caca
seed_sources.py -> 17 registry candidates created, 0 skipped
sources=17, opportunities=0
```

The database was dropped after verification.

## Real ingestion

| Source | Adapter | First run | Repeated run |
|---|---|---|---|
| GitLab | Greenhouse | 238 seen, 238 created, complete | `not_modified`, no duplicates |
| OpenAI | Ashby | 806 seen, 806 created, complete | `not_modified`, no duplicates |

Source records:

- GitLab: `ca3917d4-7995-4eca-b2f3-241e7233281c`
- OpenAI: `cc8f7c3b-36ae-43d8-a616-60276b05a441`

Database totals after ingestion:

```text
opportunities            1049  (1044 real + 5 fixtures)
unique provider_key      1049
unique official_url      1049
assessments              1049
opportunity_revisions    1049
alerts                      0
```

Eligibility distribution:

```text
India:        verified_no=241, unknown=767, verified_yes=36
Professional: verified_no=0,   unknown=1041, verified_yes=3
```

This confirms no mass inference of India eligibility from remote location
alone.

## Digest and fixture exclusion

Command:

```powershell
POST http://127.0.0.1:8000/v1/digests/generate?kind=daily
```

Result:

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
npx playwright test
```

Result:

```text
4 passed (7.4s)
```

Coverage:

- 1440px and 360px review flow.
- Demo fixtures visibly labelled before and after opening detail.
- Decision and note persist and appear in the filtered list.
- `/`, `/opportunities?include_fixtures=1`, `/sources` and `/health` return 200
  with no horizontal overflow.

## Service health

```text
docker compose ps:
api        Up (healthy)   127.0.0.1:8000
postgres   Up (healthy)   127.0.0.1:55432
web        Up             127.0.0.1:3000
worker     Up
scheduler  Up

GET /health/live  -> 200
GET /health/ready -> 200
GET /             -> 200
```

## Backup and restore

```powershell
bash scripts/backup.sh
bash scripts/restore.sh backups/discmon-20261028T160531Z.dump.gz discmon_restore
```

Result:

```text
Backup written: backups/discmon-20261028T160531Z.dump.gz

opportunities | opportunity_sources | reviews | digests | alembic_version
1049          | 1049                | 9       | 2       | b76e2a98caca

Restore verified in discmon_restore. Live database discmon was not modified.
```

## Safety checks covered by tests

- `isRemote=true` alone remains `unknown` for India eligibility.
- Student-only/2027 restrictions are detected and excluded.
- Date-only deadlines keep cutoff time unknown; ICS uses all-day events.
- Failed and partial scans never close records.
- Three complete absences create a closure candidate; confirmation closes.
- One material revision creates one alert with a unique dedup key.
- SSRF blocks loopback, private, link-local metadata and redirects to them.
- NAT64 public addresses are allowed only after validating the embedded IPv4.

## Not verified in this run

- CI workflow execution.
- Clean-clone Compose installation from an empty volume.
- Sheets outbox, changedetection and discovery-promotion end-to-end flows.
- Telegram/SMTP external delivery.
- External CI execution and clean-volume install.

These are recorded as open items in `docs/PROGRESS.md`; they are not claimed as
passing.
