# DiscMon progress

Dates: 2026-10-30 (historical status) and 2026-11-12 (stabilization checkpoint)
Authority: docs/specification.md

## 2026-11-12 Task 2 — safe Compose configuration preflight

- Exact base: `739192275e7d4f239afa2430e36acfd8419feec9`, verified by fetching
  `handoff/stabilize-idfc-audit-20261112`. New separate worktree `discmon-task2`,
  branch `hoplite/m0-compose-preflight-20261113`; older checkout at `2c31234`
  remains clean and unchanged.
- Standard-library Python preflight renders base and base+dev with explicit
  project/files, empty env file, isolated HOME/Docker config, no inherited app
  settings and no service env-file resolution. Rejects protected/malformed
  project names, external/unscoped resources, unexpected routing/profiles/mounts
  and non-local or overlapping ports. Reports secret binds and fixed-port risks.
- Default success means CONFIG ONLY, not runtime isolation. Optional host checks
  inventory names/project labels/published ports read-only and probe localhost ports; they fail
  closed without the local daemon. No arbitrary env/config override is accepted.
- Local Python 3.12.3 / Docker CLI 29.1.3 / Compose 2.40.3:
  `python3 -m unittest discover -s scripts/tests -v` — 19 passed, 0 failed,
  0 skipped, exit 0; includes two actual Compose cases and mocked failure/host
  cases, plus one actual ephemeral occupied-port test. `py_compile` and
  `git diff --check` passed (exit 0). Exact commands/limitations in changelog.
- Actual base/base+dev rendering passed (exit 0) after deliberately unsetting
  inherited Compose/Docker routing variables for that command only. Host check
  refused (exit 1): local Docker daemon unavailable. No runtime replacement or
  privileged Docker setup attempted. Automatic PR CI for code
  commit `2dc57fa` passed: https://github.com/arulx06/DiscMon/actions/runs/43318019528
  (all three jobs). Fresh runner Docker 29.4.2 / Compose v5.1.3: 19 preflight
  tests and actual host checks passed. Backend: 111 passed, 1 existing warning;
  Ruff/mypy and web typecheck/lint/build passed. Push preflight also passed:
  https://github.com/arulx06/DiscMon/actions/runs/43318008627/job/131530975717
  No existing backend/web check is changed. Initial CI version-guard failure
  and its compatibility fix are recorded in the changelog.
- No application/container/volume/database/backup mutation, migrations, source
  import, ingestion or private configuration reads. No backend pytest run locally.
  CI's pre-existing disposable PostgreSQL job remains unchanged.
- **M0 remains PARTIAL**: separately authorized clean-volume runtime deployment,
  migration, health checks and resource-safe cleanup remain unverified. No M5/M6
  work or supervisory acceptance is claimed.

## 2026-11-12 Task 1 — fail-closed PostgreSQL test isolation

- Exact starting checkpoint: `665f2380bcc24a62acdef91bd9e361b563406b91`, from
  `handoff/stabilize-idfc-audit-20261112`; feature branch
  `hoplite/m0-test-db-safety-20261113` in a separate worktree. The older original
  workspace was left clean and unchanged.
- Guard now requires explicit `APP_ENV=test` and matching database URLs before
  importing the application database engine; validates effective cached settings
  too. Only explicit local psycopg/PostgreSQL `*_test` targets are accepted.
  Unapproved query routing, inherited `PG*`, ambiguous environment casing and
  credential-bearing diagnostic output are rejected.
- Immediately before the unchanged per-test truncation, the same connection's
  SQL database/effective/authenticated identity, driver database/user/client
  endpoint and resolved loopback address are checked. Socket paths are explicitly
  allowlisted. Client endpoint checks preserve Docker's 55432-to-5432 CI mapping.
- Python 3.12.3, from `services/api` (all exit 0):
  - `../../.venv/bin/python -m ruff check app tests scripts` — `All checks passed!`
  - `../../.venv/bin/python -m mypy app scripts` —
    `Success: no issues found in 61 source files`.
  - `../../.venv/bin/python -m unittest discover -s tests -p test_database_safety.py -v`
    — `Ran 10 tests in 21.340s`, `OK`, no warnings. Includes 47 unsafe
    collection subprocesses plus a cached-settings case, all rejected before an
    engine-creation sentinel; CI/socket collection succeeds without connecting.
  - `git diff --check` — exit 0, no output.
- Local full backend integration: **BLOCKED**, not executed. The environment
  presence probe returned `False` for `APP_ENV`, `DATABASE_URL` and
  `TEST_DATABASE_URL`; no independently verified disposable database with the
  existing schema was supplied. No manual migrations/schema provisioning were
  performed, per Task 1. All local SQL execution was mocked; no PostgreSQL server
  or production application service was contacted. No `.env`, secrets, backups,
  existing databases or volumes were accessed or modified.
- Automatic CI for implementation commit `8e49cb0` **passed** on PostgreSQL
  **18.6** / Python 3.12.16: `pytest tests -q` —
  `111 passed, 1 warning in 26.25s` (exit 0; existing feedparser deprecation).
  Ruff, mypy and web typecheck/lint/build also passed. The ephemeral CI service
  supplied `discmon_test`, authenticated/effective user `discmon`, client
  `localhost:55432`; every fixture's actual identity/endpoint checks passed.
  Push run: https://github.com/arulx06/DiscMon/actions/runs/43313987678
  PR run: https://github.com/arulx06/DiscMon/actions/runs/43314034490
  Both backend/web jobs succeeded on both runs. No manual dispatch/rerun.
- PR https://github.com/arulx06/DiscMon/pull/1 targets the handoff branch, remains
  unmerged, update monitoring enabled, auto-merge disabled. Only the five scoped
  files changed. Final `git diff --check` passed; generated files/logs excluded.
  Recommendation: **READY FOR REVIEW**, not supervisory acceptance. Fresh local
  Compose acceptance and local integration remain open; M0 is not declared accepted.
- Full commands, safety coverage and limitations: `docs/changelog.md`, Task 1.

## 2026-11-12 stabilization checkpoint

- Handoff branch: `handoff/stabilize-idfc-audit-20261112`.
- Full backend suite against isolated `discmon_test`: `101 passed, 1 warning in 14.08s`.
- Ruff: `All checks passed!`; mypy: `Success: no issues found in 61 source files`.
- Frontend: typecheck, lint and production build passed.
- Playwright E2E against an isolated local API/web stack on `discmon_test`:
  `4 passed (7.2s)`.
- Live `discmon` was not modified: 1366 opportunities before and after the run.
- Recovered the interrupted IDFC scoring audit (`test_idfc_scoring_audit.py`),
  removed the invalid standalone `run_idfc_audit.py`, and repaired changelog
  control-character corruption.
- Docker application services were not rebuilt or restarted.
- The October sections below are historical evidence recorded on 2026-10-29/30;
  they were not re-executed in this checkpoint.

## Historical status (2026-10-30)

M0-M4 implementation is complete and verified against real PostgreSQL, Docker
Compose and five live sources: GitLab (Greenhouse), OpenAI (Ashby), FOSS
United (RSS), Hasjob (Atom), and CNCF LFX Mentorship (GitHub). Phase 1
field-quality and IDFC scoring audits are finished with rules v3. Phase 2
non-job-board programme discovery, ingestion, and review are demonstrated with
real CNCF LFX mentorship proposals. Phase 4 backup restore drill of `backups/discmon-20261029T091622Z.dump.gz` succeeded. Frontend Playwright E2E
and full backend test suites pass.

## Historical verified evidence (2026-10-29/30)

### Backend

```text
services/api> python -m pytest -q
90 passed, 1 warning in 17.69s

services/api> ruff check app tests scripts
All checks passed!

services/api> mypy app scripts
Success: no issues found in 61 source files
```

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

### Source expansion (2026-10-29)

| Source | ID | First run | Repeated run |
|---|---|---|---|
| FOSS United Job Board (RSS) | `a08c620f-83df-4ad9-9266-79c95cd72bc4` | 7 seen, 7 created | 7 seen, 7 skipped |
| Hasjob (Atom) | `a59b9a54-0a6d-46dd-bba2-5f6f3be018f9` | 15 seen, 15 created | 15 seen, 2 updated, 13 skipped |

Both sources are approved `credible_aggregator` RSS sources with venue-only
discovery (`fossunited.org` and `hasjob.co`). FOSS United requires visible
attribution. Hasjob publishes `/feed` from its home page and robots allows it;
`/tos` governs posting rather than reading. Both feeds report
`scan_complete=false`; they can never close records. FOSS United discovery inspected
22 links and created 8 candidates; Hasjob discovery inspected 15 links and
created 15 candidates. All 23 candidates were rejected because they are board
pages already represented by the approved feeds and would misattribute the
organization if promoted as independent sources.

Pinaca SDE-1 and SDE-2 now score 84 in `prepare_early` with
`professional_eligibility=verified_yes`, `india_eligibility=verified_yes`,
type `job`, and location `Gurugram`. `/v1/opportunities?bucket=prepare_early`
and `/opportunities?bucket=prepare_early` both show exactly those two records.
FOSS United discovery exposed a non-job `hiring-designer/new` link; it was
rejected with the other candidates.

### Field-quality repair (2026-10-29)

After taking backup `backups/discmon-20261029T091622Z.dump.gz`, the live
FOSS United and Hasjob records were re-ingested through the corrected parser
in three host-side passes: 6 FOSS and 4 Hasjob updates, 1 Hasjob update for
Mango Giraffe, then 7 FOSS employment/workplace updates. The passes created 18
revisions across 11 opportunities, created 0 alerts, and kept the opportunity
count at 1,075. Both feeds still report `scan_complete=false`.

Corrections confirmed in live data and API:

- Pinaca SDE-1 compensation is `Compensation: INR 20-30 LPA + benefits`;
  Mango Giraffe is `paid internship, starting at ₹10,000 a month`.
- Only one compensation summary exceeds 120 characters: Project Tech4Dev at
  151 characters, containing a genuine experience-dependent caveat.
- Build for Bharat in both feeds has exact deadline
  `2026-10-18 18:29:00+00`, timezone `Asia/Kolkata`; FOSS Graphic Design has a
  date-only `2026-09-10` deadline with no invented cutoff time. All three are
  `closed`; 0 open records have a past exact or date-only deadline.
- Build for Bharat is India `verified_yes`, professional `unknown`,
  `student_only=false` in both records.
- FOSS employment is `FullTime` for all 7 records; workplace is `remote=2`,
  `hybrid=1`, `unknown=4`. GitLab has no employment metadata in its board
  response and Hasjob has no employment/workplace fields in its feed, so those
  fields remain `unknown` rather than inferred.
- The Ashby adapter now separates salary cash, equity, currency and period from
  structured compensation components, with fixture coverage. Existing live
  Ashby `cash` values still contain the previous combined summary until an
  authorized rebuild and re-ingestion; opportunity summaries are unaffected.

The live containers still run the pre-repair parser. A scheduled old-code
re-ingestion can reintroduce the corrected RSS fields until the new code is
rebuilt and restarted. No restart was performed.

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
- Current database: 1,075 opportunities total, including 5 labelled fixtures
  and 1,070 real records; 24 sources (4 enabled); 4,143 assessments; 14
  reviews; 0 alerts.
- Rescans append assessment history rows. This has not been deduplicated, but
  no duplicate opportunities or provider identities were created.
- Latest-assessment eligibility: India `unknown=776`, `verified_no=242`,
  `verified_yes=57`; professional `unknown=1065`, `verified_no=1`,
  `verified_yes=9`.
- Latest-assessment buckets: `needs_verification=828`, `excluded=243`,
  `prepare_early=2`, `act_now=2`. The `act_now` records are labelled fixtures;
  the `prepare_early` records are the two real Pinaca roles.
- Hasjob roles remain `needs_verification` for professional eligibility. The
  top Hasjob record is `Founding Data Engineer` at score 69, type `job`,
  location Bangalore, India `verified_yes`.
- Remote location is still not treated as India evidence; the new state
  patterns only infer India from explicit location text.
- Coverage checks: 0 opportunities without a source link, 0 enabled sources
  with a non-approved/legal-pending status, and 0 duplicate provider keys.
  This is a per-record check, not the full registry coverage audit.

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
- `/discover` rendered the live FOSS United candidates with approve/reject
  controls; decisions were applied through the API, not by clicking those
  buttons.
- Source detail shows JSON config editing and a disabled "Scan for links"
  control for an API-backed source without discovery config.
- A real new record, `Communications Lead, Cyber` (OpenAI), was reviewed as
  `research` with an honest eligibility-verification next action and a
  follow-up date. `/watchlist` rendered it under Research with the action and
  follow-up.
- `/opportunities` showed 1,070 real records with Pinaca first;
  `/opportunities?bucket=prepare_early` showed exactly the two Pinaca records,
  each attributed to `FOSS United Job Board`.

Live discovery scans ran for both aggregator sources. Candidate promotion and
Sheets mirroring were not exercised; all 23 candidates were rejected.

### Backup and restore

```text
bash scripts/backup.sh
Backup written: backups/discmon-20261028T173345Z.dump.gz

bash scripts/restore.sh backups/discmon-20261028T173345Z.dump.gz discmon_restore_final
opportunities=1053, opportunity_sources=1053, reviews=14, digests=2,
alembic_version=d4a7c1e9f210
Restore verified in discmon_restore_final. Live database discmon was not modified.
```

Post-ingestion backup and drill:

```text
backups/discmon-20261029T065708Z.dump
pg_restore -l: 118 TOC entries, custom format, gzip, PostgreSQL 18.6

restore into discmon_restore_20261029:
opportunities=1075 (5 fixtures), sources=24, reviews=14,
alembic_version=d4a7c1e9f210

discmon_restore_20261029 dropped after verification. Live discmon unchanged.
```

Pre-repair snapshot for the field correction:

```text
backups/discmon-20261029T091622Z.dump.gz
live opportunities=1075, 658 with compensation summaries, 1 long summary,
0 alerts
```

This latest backup has not yet been restore-drilled.

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

docker compose build api worker scheduler
All three images built successfully with PIP_DEFAULT_TIMEOUT=120 and
PIP_RETRIES=10, then recreated and verified healthy/up.
```

## Gate status (2026-10-30, historical)

| Gate | Status | Evidence / remaining work |
|---|---|---|
| M0 | Partial | Compose build/health, clean database migration/seed, full pytest and Next production build verified. CI workflow has not been executed here; a clean-clone run has not been recorded. |
| M1 | Verified | Four real sources ingested (GitLab, OpenAI, FOSS United, Hasjob); repeated scans create no duplicate opportunities; fixtures cover all adapters. |
| M2 | Verified | Hard gates, unknown handling, date-only deadlines, one-revision/one-alert, failure safety and closure tests pass. |
| M3 | Verified | Playwright 360px/1440px review and overflow journeys pass against the built web app. |
| M4 | Verified | Digest, ICS, CSV and Markdown brief tests pass; one material revision alert dedup tests pass; live digest excludes fixtures. |
| M5 | Partial | Discovery UI/API, changedetection webhook, Sheets outbox, SMTP and GitHub watch paths are fixture-tested. Live aggregator discovery scans and candidate rejection were exercised; verified promotion, Sheets mirroring and external delivery are not verified. |
| M6 | Partial | Backup/restore implemented and drilled at the current migration. CI, seven-day operation, worker-crash recovery, load/memory checks and the source coverage audit remain. |

## Known gaps

- CI has not been run in this environment. Do not describe it as green.
- A fresh-clone Compose run has not been recorded; clean database migration and
  seeding were verified, but the current Compose volume is not empty.
- changedetection, Telegram, SMTP and Google Sheets have no live credentials or
  services here. Their code paths are fixture-tested only.
- No live non-ATS programme has completed discovery, approval, promotion,
  verification, scoring and Sheets mirroring.
- Live discovery scans ran and 23 candidates were rejected; candidate
  promotion was not exercised.
- Alerts table is empty because no real record meets the immediate gate (85)
  and external delivery is unconfigured.
- No seven-day run, simulated worker-crash recovery, load test or memory
  profile is recorded.
- Repeated scans append assessment rows; storage growth needs a retention or
  deduplication decision.
- The source coverage audit and `raw_evidence` retention audit remain.
- The latest backup has not been restore-drilled.
- The running API/worker/scheduler still use the pre-repair parser. A scheduled
  scan can undo corrected RSS values until an authorized rebuild/restart.
- GitLab and Hasjob employment types are absent from source metadata; Hasjob
  workplace is also absent. These remain `unknown`.
- Existing Ashby `cash` fields still include equity text until the corrected
  adapter is deployed and the board is re-ingested.
- The demo registry digest includes fixture records by design and is visibly
  labelled. Real digests exclude fixtures.

## Next

1. With authorization, rebuild and restart API/worker/scheduler so the corrected
   parser is active, then re-ingest Ashby and verify startup health.
2. Restore-drill `backups/discmon-20261029T091622Z.dump.gz`, run CI and record a
   clean-checkout Compose drill with an empty volume.
3. Complete the Phase 1.3 field audit and Phase 1.6 scoring review, then execute
   the M5 non-ATS discovery-to-promotion-to-mirror path once credentials exist.
4. Run the M6 seven-day soak, worker-crash recovery, load/memory checks and
   source coverage audit before claiming M5/M6.
