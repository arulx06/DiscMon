# Acceptance report

Dates: 2026-10-30 (historical) and 2026-11-12 (stabilization checkpoint)
Specification: `docs/specification.md`
Status: The 2026-10-30 section records historical M0-M4 checks. The 2026-11-12
checkpoint re-ran the full backend suite and E2E against isolated test data;
external integrations and M5/M6 acceptance runs remain unverified.

## 2026-11-12 stabilization checkpoint

Verification executed on 2026-11-12 against the isolated `discmon_test`
PostgreSQL database and an isolated local API/web stack:

```text
services/api> pytest -q
101 passed, 1 warning in 14.08s

services/api> ruff check app tests scripts
All checks passed!

services/api> mypy app scripts
Success: no issues found in 61 source files

apps/web> npm run typecheck
apps/web> npm run lint
apps/web> npm run build
apps/web> npx playwright test
4 passed (7.2s)
```

- Playwright ran with `PLAYWRIGHT_BASE_URL=http://127.0.0.1:3100` against a local
  `next start` and a local API on port 8100, both backed by `discmon_test`.
- Live `discmon` retained 1366 opportunities before and after; it was not
  modified. Docker application services were not rebuilt or restarted.
- The October 2026 sections below are historical evidence and were not
  re-executed in this checkpoint.

## Environment (2026-10-30, historical)

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
90 passed, 1 warning in 17.69s
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
| FOSS United Job Board | RSS | 7 seen, 7 created | 7 skipped |
| Hasjob | Atom | 15 seen, 15 created | 2 updated, 13 skipped |

Source records:

- GitLab: `ca3917d4-7995-4eca-b2f3-241e7233281c`
- OpenAI: `cc8f7c3b-36ae-43d8-a616-60276b05a441`
- FOSS United: `a08c620f-83df-4ad9-9266-79c95cd72bc4`
- Hasjob: `a59b9a54-0a6d-46dd-bba2-5f6f3be018f9`

Both feeds report `scan_complete=false`, so they are never treated as complete
scans and cannot close records. FOSS United discovery inspected 22 links and
created 8 candidates; Hasjob discovery inspected 15 links and created 15
candidates. All 23 were rejected
because they are board pages already covered by the approved feeds and are not
independent sources.

Pinaca SDE-1 and SDE-2 are real `prepare_early` records at score 84 with
`professional_eligibility=verified_yes`, `india_eligibility=verified_yes`,
type `job`, and location `Gurugram`. They are the only real `prepare_early`
records. The two `act_now` records are labelled fixtures.

Verification scans created four real opportunities and one legitimate material
update. Ashby compensation component IDs/order vary between responses; two
false revisions were removed and their prior revisions restored. Ingestion now
ignores `monetary_value_json.raw` when deciding materiality, with a regression
test. Post-fix scans created no false updates.

Database totals:

```text
opportunities            1075  (1070 real + 5 fixtures)
sources                    24  (4 enabled)
assessments              4143
reviews                    14
alerts                      0
```

Every rescan appends assessment rows. This has not been deduplicated; no
duplicate opportunities or provider identities were created. Coverage checks
found 0 opportunities without a source link, 0 enabled sources with a
non-approved/legal-pending status, and 0 duplicate provider keys.

Latest-assessment eligibility distribution:

```text
India:        verified_no=242, unknown=776, verified_yes=57
Professional: verified_no=1,   unknown=1065, verified_yes=9
Buckets:      needs_verification=828, excluded=243, prepare_early=2, act_now=2
```

This confirms no mass inference of India eligibility from remote location
alone. The new aggregator records vary: Pinaca is verified for both India and
professional eligibility from explicit source text, while Hasjob roles retain
`unknown` professional eligibility. Hasjob locations such as Bangalore and
Gurugram are explicit location evidence, not remote-location inference.

## Field-quality repair (2026-10-29)

After backup `backups/discmon-20261029T091622Z.dump.gz`, the corrected parser
was applied to live FOSS United and Hasjob records through three host-side
re-ingestion passes: 6 FOSS and 4 Hasjob updates, 1 Hasjob update, then 7 FOSS
employment/workplace updates. The passes created 18 revisions across 11
opportunities, created 0 alerts, and kept the live total at 1,075. Both feeds
remain `scan_complete=false`.

Confirmed corrections:

- Pinaca SDE-1: `Compensation: INR 20-30 LPA + benefits`.
- Mango Giraffe: `paid internship, starting at ₹10,000 a month`.
- Build for Bharat in both feeds: exact deadline `2026-10-18 18:29:00+00`,
  `Asia/Kolkata`, India `verified_yes`, professional `unknown`,
  `student_only=false`; `life_state=closed`.
- FOSS Graphic Design: date-only deadline `2026-09-10`, no invented cutoff
  time; `life_state=closed`.
- 0 open records have a past exact or date-only deadline.
- 658 records have compensation summaries; only one exceeds 120 characters
  (Project Tech4Dev at 151 characters with a genuine experience caveat).
- FOSS employment is `FullTime` for all 7; workplace is `remote=2`,
  `hybrid=1`, `unknown=4`. GitLab and Hasjob lack employment metadata in their
  source responses, so they remain `unknown` rather than inferred.

The Ashby adapter now separates salary cash, equity, currency and period from
structured components, with fixture coverage. Existing live Ashby `cash`
values still include the old combined summary until an authorized rebuild and
re-ingestion; opportunity summaries are unaffected.

The live containers still run the pre-repair parser, so a scheduled scan can
reintroduce the corrected RSS fields until the new code is rebuilt and
restarted. No restart was performed.

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
- `/discover` rendered the live FOSS United candidates with approve/reject
  controls. Decisions were applied through the API rather than by clicking
  those buttons.
- Source detail renders JSON configuration editing. “Scan for links” is
  disabled for an API-backed source without discovery configuration.
- `Communications Lead, Cyber` (`47387b89-124b-4dcd-adec-f15866a8f187`,
  OpenAI) was saved as `research`, with next action
  “Verify India and professional eligibility from the source” and follow-up
  `2026-11-02`.
- `/watchlist` renders that record under Research with the next action and
  follow-up date.
- `/opportunities` showed 1,070 real records with Pinaca first;
  `/opportunities?bucket=prepare_early` showed exactly the two Pinaca records,
  each attributed to `FOSS United Job Board`.

Live discovery scans ran for FOSS United and Hasjob. Candidate promotion and
Sheets mirroring were not exercised; all 23 candidates were rejected.

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

Post-ingestion snapshot:

```text
backups/discmon-20261029T065708Z.dump
pg_restore -l: 118 TOC entries, custom format, gzip, PostgreSQL 18.6
```

Restore drill:

```text
discmon_restore_20261029
opportunities=1075 (5 fixtures), sources=24, reviews=14,
alembic_version=d4a7c1e9f210
```

The disposable database was dropped after verification; live `discmon` was not
modified.

Latest pre-repair snapshot:

```text
backups/discmon-20261029T091622Z.dump.gz
live opportunities=1075, 658 with compensation summaries, 1 long summary,
0 alerts
```

This backup has not yet been restore-drilled.

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
- Non-ATS candidate promotion through approval, verification, scoring and
  Sheets mirroring. Discovery scans and rejection were exercised.
- An immediate alert triggered by a newly eligible record.
- Seven-day soak, worker-crash recovery, load test or memory profile.
- Source coverage audit and `raw_evidence` retention audit.
- Latest backup `backups/discmon-20261029T091622Z.dump.gz` restore drill.
- Authorized rebuild/restart to activate the corrected parser, and re-ingestion
  of Ashby structured compensation fields.

These are recorded as open items in `docs/PROGRESS.md`; they are not claimed as
passing.
