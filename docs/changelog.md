# Changelog

## 2026-11-12 — Task 1: fail-closed PostgreSQL test isolation

### Bounded change

- `services/api/tests/conftest.py`: remove fallback test configuration; parse
  explicit matching URLs with SQLAlchemy; require exact test environment,
  PostgreSQL/psycopg, explicit user, valid port, `*_test` database and loopback or
  approved local socket. Reject routing/options query parameters (except an
  approved socket `host`), duplicate socket hosts, inherited libpq `PG*` variables
  and ambiguous environment casing. Validate effective settings before importing
  the engine, including stale cached configuration.
- Before each existing `TRUNCATE ... RESTART IDENTITY CASCADE`, validate
  `current_database()`, `current_user`, `session_user` and the same raw psycopg
  connection's database, user, client host/port and resolved address. Do not
  compare a container's server-side address/port to the host's mapped CI port.
  No fixture scope, cleanup semantics, schema, migration, application or frontend
  changes. No bypass flag.
- `services/api/tests/test_database_safety.py`: standalone unittest/pure guard,
  collection-only subprocess and mocked cleanup-order tests; no live database
  needed. `README.md`: explicit destructive-fixture warning, Bash/Ubuntu and
  retained PowerShell instructions with placeholders and both required URLs.

### Execution evidence

Baseline `665f2380bcc24a62acdef91bd9e361b563406b91`, new branch
`hoplite/m0-test-db-safety-20261113`; separate worktree preserves the older clean
Hoplite checkout. Python 3.12.3. Dependency installation used a worktree-local
ignored virtualenv (`uv venv .venv --python 3.12` and
`uv pip install --python .venv/bin/python -e 'services/api[dev]'`, exit 0).

From `services/api`, final checks:

```text
../../.venv/bin/python -m ruff check app tests scripts
All checks passed!
exit 0

../../.venv/bin/python -m mypy app scripts
Success: no issues found in 61 source files
exit 0

../../.venv/bin/python -m unittest discover -s tests -p test_database_safety.py -v
Ran 10 tests in 21.340s
OK
exit 0; no warnings

git diff --check
(no output)
exit 0
```

The initial root-directory mypy invocation did not load the API's existing
pyproject settings and reported a feedparser missing-stubs error (exit 1).
Running the required existing scope from `services/api` passes unchanged; no
mypy configuration or coverage was weakened. Formatting/lint findings during
implementation were corrected before the final checks above.

Safety coverage includes 47 invalid environment/URL cases: missing variables,
non-test environments, canonical `discmon` and ambiguous database names,
different database/user/password/host/port, remote/multi-host targets, absent
host, invalid port, unsupported driver/malformed URL, host/hostaddr/port/service/
dbname/user/options overrides, duplicate hosts, unapproved/traversing sockets,
libpq environment routing and ambiguous variable casing. Each subprocess runs:
`pytest.main(['--collect-only', '-q', 'tests/test_database_safety.py'])`, with
`sqlalchemy.ext.asyncio.create_async_engine` replaced by a failing sentinel.
All 47 exit nonzero with a fixed safety message, without reaching engine creation
or echoing the dummy password/full URL. An additional stale-cached-settings
subprocess has the same assertions. Accepted CI loopback and approved socket
collection-only subprocesses exit 0, without opening a connection. Pure tests
also cover IPv6, implicit/explicit default port equality, actual database/role/
endpoint mismatches, localhost resolution and unavailable resolved addresses.
The mocked fixture executes one identity SELECT and no TRUNCATE on mismatch;
only its accepted path reaches the unchanged TRUNCATE on the same connection.

### Remaining verification / safety boundary

Local full backend integration is **BLOCKED**, not attempted: a presence-only
Python `os.environ.get` probe reported `APP_ENV explicitly supplied: False`,
`DATABASE_URL explicitly supplied: False`, `TEST_DATABASE_URL explicitly supplied:
False` (exit 0). No independently verified disposable database with the existing
schema was provided; Task 1 prohibits manual schema migrations without separate
authorization. Installed PostgreSQL tooling alone does not establish a safe
target. No real local database identity is claimed. All local SQL was mocked;
only synthetic endpoints/dummy credentials were used for negative cases. No
production connections, `.env`/secret/backup reads, data changes, container
restarts or manual migrations occurred.

Automatic push/PR CI **passed** for implementation commit `8e49cb0`:

- Push run: https://github.com/arulx06/DiscMon/actions/runs/43313987678
- PR run: https://github.com/arulx06/DiscMon/actions/runs/43314034490
- Both backend and web jobs succeeded on both runs; observed with
  `gh run watch 43313987678 --exit-status --interval 5` (exit 0),
  `gh run view 43313987678 --job 131517080193 --log` (exit 0), and
  `gh run view 43314034490 --json status,conclusion,url,jobs` (exit 0).
- Actual PostgreSQL server startup log: PostgreSQL **18.6**, disposable service
  created by the existing `postgres:18-alpine` CI workflow. Python **3.12.16**.
  Existing CI migrations ran only against that newly created CI service; no
  manual migrations or manual workflow dispatch/rerun occurred.
- `pytest tests -q`: **111 passed, 1 warning in 26.25s**, exit 0. Warning:
  existing feedparser `updated_parsed`/`published_parsed` deprecation in the RSS
  adapter fixture test. No new guard warnings. All 101 existing tests plus the
  10 safety tests passed, preserving per-case cleanup and integration behavior.
- Actual connected database/user/client endpoint were verified by the guard on
  each real fixture connection: `discmon_test`, `discmon` (both current/session
  user), `localhost:55432`, resolved loopback. The service's container port is
  5432; checks correctly use client routing rather than server-side NAT values.
- `ruff check app tests scripts`: `All checks passed!`; `mypy app scripts`:
  `Success: no issues found in 61 source files`; both exit 0. Web
  `npm run typecheck`, `npm run lint`, `npm run build` also exited 0.
- Nonblocking CI environment notices: Node 20 action-runtime deprecation and
  ubuntu-latest migration; unchanged and outside this task.
- PR https://github.com/arulx06/DiscMon/pull/1 targets
  `handoff/stabilize-idfc-audit-20261112`, not master; update monitoring enabled,
  auto-merge disabled, no merge/queue operation. No review threads were open at
  publication. Independent code review found no remaining actionable safety
  blocker after resolved-host validation was added.

Fresh local Compose acceptance remains incomplete.
The guard verifies configuration/identity, not ownership or disposability: an
operator must still independently provision/verify the test database. A local
proxy cannot be distinguished from a direct listener by these identity checks.
Generated virtualenv, egg-info, bytecode and tool caches are ignored/excluded;
execution logs and helper scripts remain outside the checkout. Only the guard,
its regressions and these three documentation files belong to the checkpoint.
Recommendation: **READY FOR REVIEW**, with local integration and fresh Compose
limitations explicitly open; no supervisory Task 1 or M0 acceptance claim.
The evidence follow-up changes only progress/changelog documentation; guard and
regression code are unchanged from the successful implementation CI checkpoint.


## 2026-11-12

### Stabilization checkpoint

- Recovered the interrupted IDFC scoring audit. Removed the invalid standalone
  `services/api/tests/run_idfc_audit.py` (incorrect ORM constructor kwargs) and
  repaired `services/api/tests/test_idfc_scoring_audit.py` to construct real
  `Opportunity`/`UserProfile` objects and assert v3 scoring behaviour.
- Repaired control-character and broken-line corruption in the October
  changelog and progress entries. October evidence is preserved as historical
  and was not re-executed by this checkpoint.

### Verification (2026-11-12)

```text
services/api> pytest -q   (DATABASE_URL=...discmon_test)
101 passed, 1 warning in 14.08s

services/api> ruff check app tests scripts
All checks passed!

services/api> mypy app scripts
Success: no issues found in 61 source files

apps/web> npm run typecheck
apps/web> npm run lint
apps/web> npm run build
apps/web> npm run test:e2e   (isolated API/web, discmon_test)
4 passed (7.2s)
```

- Backend suite ran against the isolated `discmon_test` PostgreSQL database.
- Playwright ran against an isolated local API/web stack backed by
  `discmon_test`; live `discmon` was not modified.
- Historical 2026-10-29/30 results below are not re-executed unless repeated
  above.

## 2026-10-30

### Added

- Rules v3 scoring engine with explicit hard gates for closed/archived opportunities (life_state in (closed, archived)) and full-time commitment conflicts (opportunity.employment_conflict).
- Differentiated career upside scoring based on opportunity type (fellowship, residency, mentorship, grant, hackathon, job) with published value signals (cash, equity/credits, high credibility).
- Prejoin employment stage protection: full-time job openings for users with a committed prejoin start (IDFC) are capped at prepare_early with an honest career explanation, preventing distraction from IDFC preparation while allowing selective mentorships, fellowships, and grants to reach act_now or prepare_early.
- Technical programme and mentorship project recognition: open source engineering mentorships and fellowships with non-standard project titles (e.g. CNCF LFX mentorship proposals) are evaluated based on technical scope and body evidence rather than discarded as non-engineering.
- CNCF LFX Mentorship official source (aa60aaec-769c-425b-9f8b-a345dc8a0c72, https://github.com/cncf/mentoring), approved under the GitHub adapter with label filtering Proposal. Ingested 50 real cloud, distributed systems, and AI infrastructure mentorship project proposals.
- Real non-job-board programme review: [CNCF LFX Proposal] Meshery MCP Server reviewed as research with explicit next action and follow-up date, rendered on /watchlist.
- 10 new test cases in services/api/tests/test_scoring.py (19 total tests), covering positive/negative cases, prejoin caps, closed opportunity exclusions, and technical mentorship recognition. Full test suite now passes with 90 tests.

### Fixed

- Closed Build for Bharat Fellowship and Graphic Design records now correctly evaluate to excluded (hard gate) rather than remaining in needs_verification.
- Rebuilt Docker containers (discmon-api, discmon-worker, discmon-scheduler) activated the corrected Ashby structured compensation extraction and v3 scoring logic in live services.
- Re-ingested OpenAI Ashby board cleanly separated salary cash, equity, period, and currency into structured compensation fields across 814 seen records (9 created, 639 updated, 166 skipped).
- Verified restore drill of `backups/discmon-20261029T091622Z.dump.gz` into clean disposable database discmon_restore_verify (1,075 opportunities, 1,075 sources, 14 reviews, 3 digests, alembic d4a7c1e9f210). Disposable database dropped with live database unmodified.

### Verification

```text
services/api> python -m pytest -q
90 passed, 1 warning in 17.69s

services/api> ruff check app tests scripts
All checks passed!

services/api> mypy app scripts
Success: no issues found in 61 source files

apps/web> npx playwright test
4 passed (5.1s)
```

Live database status: 1,149 opportunities (1,144 real + 5 demo fixtures), 5 enabled sources (GitLab Greenhouse, OpenAI Ashby, FOSS United RSS, Hasjob Atom, CNCF LFX Mentorship GitHub), all healthy with 24h schedules, 0 alerts.


## 2026-10-29

### Added

- FOSS United Job Board RSS source
  `a08c620f-83df-4ad9-9266-79c95cd72bc4`
  (`https://fossunited.org/jobs/rss.xml`), approved as a credible aggregator
  with venue-only discovery. First ingestion created 7 real opportunities.
- Hasjob Atom source `a59b9a54-0a6d-46dd-bba2-5f6f3be018f9`
  (`https://hasjob.co/feed`), approved as a credible aggregator with venue-only
  discovery. First ingestion created 15 real India-focused opportunities.
- RSS/Atom metadata extraction: entry `location`, `Location:` summary text,
  company links in summaries, author organization and title suffix fallback.
- Title-first opportunity classification with engineering, design, sales,
  internship and leadership title families. Body text is only a fallback.
- Indian state names added to location inference: Kerala, Karnataka, Tamil
  Nadu, Telangana, Andhra Pradesh, Maharashtra, Gujarat, Rajasthan, Uttar
  Pradesh, Haryana, West Bengal, Odisha, Madhya Pradesh, Chhattisgarh, Bihar
  and Goa.
- Regression tests for RSS organization/location extraction, title-first
  classification and Indian-state eligibility.

### Fixed

- Pinaca roles were misclassified as `founder_programme` because their body
  mentions a founding team. They are now `job` records with score 84,
  `prepare_early`, verified India and professional eligibility, and location
  Gurugram.
- Early FOSS United ingestion attributed every record to FOSS United because
  the board link was used as the organization domain. Re-ingestion corrected
  Pinaca to its `Pinaca (Pinaca Labs Private Limited)` organization and location.
- Docker image builds now set `PIP_DEFAULT_TIMEOUT=120` and `PIP_RETRIES=10`
  to tolerate transient package-index timeouts. API, worker and scheduler
  images were rebuilt successfully and recreated.

### Verification

```text
services/api> python -m pytest -q
81 passed, 1 warning in 32.80s

services/api> ruff check app tests scripts
All checks passed!

services/api> mypy app scripts
Success: no issues found in 61 source files
```

Live database after ingestion:

```text
opportunities=1075 (1070 real + 5 fixtures)
assessments=4143
reviews=14
sources=24 (4 enabled)
alerts=0
```

Latest-assessment distribution:

```text
India:        unknown=776, verified_no=242, verified_yes=57
Professional: unknown=1065, verified_no=1, verified_yes=9
Buckets:      needs_verification=828, excluded=243, prepare_early=2, act_now=2
```

The only real `prepare_early` records are Pinaca SDE-1 and SDE-2 at score 84.
The only `act_now` records are the two labelled fixtures at score 90. FOSS
United and Hasjob discovery inspected 22 and 15 links respectively; the 23
resulting candidates were rejected because those board pages are already
ingested via RSS/Atom and are not independent sources.

UI checks: `/opportunities` shows 1070 real records with Pinaca first and
`/opportunities?bucket=prepare_early` shows exactly the two Pinaca records with
source attribution to `FOSS United Job Board`. Both feeds report
`scan_complete=false`, so they cannot close records. Backup
`backups/discmon-20261029T065708Z.dump` was restore-drilled into
`discmon_restore_20261029`: 1075 opportunities (5 fixtures), 24 sources, 14
reviews and Alembic `d4a7c1e9f210`; the disposable database was dropped after
verification. The later backup `backups/discmon-20261029T091622Z.dump.gz` has
not yet been restore-drilled.

### Field-quality repair (later 2026-10-29 run)

#### Fixed

- Compensation snippets now stop at clause, benefit-list and compensation-mode
  boundaries, prefer LPA over transient lakh components, and support
  `a/an/each month` periods plus `paid` labels. Pinaca now renders
  `Compensation: INR 20-30 LPA + benefits`; Mango Giraffe renders
  `paid internship, starting at ₹10,000 a month`.
- Deadline extraction now applies explicit clocks with timezones, anchors
  yearless deadlines to publication time, and resolves day/month ambiguity
  instead of taking the first calendar match.
- Build for Bharat now records exact `2026-10-18 18:29:00+00` in
  `Asia/Kolkata`; FOSS Graphic Design records date-only `2026-09-10` with no
  invented cutoff. Both past-deadline records are `closed`.
- Eligibility now recognises explicit `Indian citizens` wording and recent
  graduate exceptions. Build for Bharat is India `verified_yes`, professional
  `unknown`, and not student-only in both feeds.
- RSS/Atom records now map explicit employment and workplace labels. FOSS has
  `FullTime` for all 7 records with `remote=2`, `hybrid=1`, `unknown=4`.
- Ashby compensation now separates salary cash, equity, currency and period
  from structured components instead of copying a combined summary into
  `cash`; the fixture asserts the structured fields.

#### Live repair

After backup `backups/discmon-20261029T091622Z.dump.gz`, three host-side
re-ingestion passes applied the corrected parser to FOSS United and Hasjob:
6 FOSS and 4 Hasjob updates, 1 Hasjob update, then 7 FOSS updates. They created
18 revisions across 11 opportunities, created 0 alerts, and kept the live total
at 1,075 opportunities. Both feeds remain `scan_complete=false`.

Live field checks: 658 records have compensation summaries, 1 exceeds 120
characters (Project Tech4Dev, 151 characters with a genuine
`depending on experience` caveat), and 0 open records have a past exact or
date-only deadline.

#### Verification

```text
services/api> python -m pytest -q
81 passed, 1 warning in 32.80s

services/api> ruff check app tests scripts
All checks passed!

services/api> mypy app scripts
Success: no issues found in 61 source files
```

#### Remaining limitations

- The running containers still use the pre-repair parser. Until an authorized
  rebuild/restart, a scheduled scan can reintroduce the corrected RSS fields.
- Existing Ashby `cash` values still include equity text until the corrected
  adapter is deployed and the board is re-ingested; summaries are unaffected.
- GitLab and Hasjob employment types are absent from source metadata; Hasjob
  workplace is also absent, so those fields remain `unknown`.
- The latest backup has not been restore-drilled.

### Known limitations

- No SMTP, Telegram, Sheets, changedetection or AI credentials; external
  delivery remains unverified.
- Alerts remain empty because no real records meet the immediate gate (85).
- Hasjob approval is based on its public `/feed`, the home-page feed link and
  robots allowing it. `/tos` governs job posting rather than feed reading; no
  separate feed licence is published.
- CI, clean-clone install, seven-day soak, worker-crash drill, load/memory
  checks and retention audit remain open.

## 2026-10-28

### Added

- Complete M0-M4 implementation: PostgreSQL schema and migrations, adapter
  registry, SSRF-defended fetchers, idempotent ingestion, revisions, evidence,
  assessments, hard gates, scoring, alerts, queue/worker/scheduler, FastAPI
  owner API, responsive Next.js UI, digests, ICS, CSV and Markdown briefs.
- Playwright configuration and review-flow coverage for 1440px and 360px.
- `services/api/tests/test_ssrf.py`: private, metadata, NAT64, redirect and
  response-size policy tests.
- `services/api/tests/test_queue.py`: two-worker claim contention test.
- `scripts/backup.sh` and `scripts/restore.sh`; restore drill into
  `discmon_restore` verified counts and Alembic revision.
- `docs/specification.md` copy of the authoritative specification.
- `docs/PROGRESS.md` and this changelog.

### Fixed

- Greenhouse root URLs were rejected when DNS returned NAT64 AAAA addresses.
  NAT64 prefixes are now unwrapped and the embedded IPv4 address is validated.
- Ashby's OpenAI board exceeded the 8 MB response cap. The configured cap is
  now 20 MB, and `FetchPolicy.max_bytes=0` correctly falls back to settings.
- Windows Proactor loop broke async adapters. Worker/scheduler use
  `app/runtime.py`, which selects the selector event loop policy.
- `Notice` rendered nothing for empty `error` strings; it now falls back to the
  notice text.
- Demo digests were reused for the real daily window. Demo digests are replaced
  for the same window; demo seeds now use the previous day and are labelled in
  the UI.
- `seed_sources.py` crashed inside the container when resolving repository
  parents; the repository candidate is now constructed safely.
- Duplicate OpenAI source rows were removed; one source per board remains.

### Verification

```text
services/api> python -m pytest -q
41 passed, 1 warning in 22.27s

services/api> ruff check app tests scripts
All checks passed!

services/api> mypy app scripts
Success: no issues found in 56 source files

apps/web> npx playwright test
4 passed (7.4s)
```

A disposable clean database migrated from zero to `b76e2a98caca` and seeded 17
registry candidates without touching live data.

Real ingestion: GitLab Greenhouse 238 records, OpenAI Ashby 806 records, both
`scan_complete=true`; repeated runs returned `not_modified` without duplicates.
Live daily digest contains 15 real opportunities and no `[Demo]` content.
Backup restore drill produced 1,049 opportunities, 1,049 source links, 9
reviews, 2 digests and Alembic `b76e2a98caca` in `discmon_restore`.

### Known limitations

- CI has not been executed in this environment.
- A clean-clone Compose run has not been recorded.
- Sheets outbox delivery, changedetection delivery and discovery promotion
  remain incomplete.
- Telegram/SMTP delivery lacks an end-to-end test; in-app alerts are tested.

### M5/M6 extension (later on 2026-10-28)

#### Added

- Discovery backend and UI: candidate extraction, approval/rejection, run and
  promote actions, promoted-source links, and source configuration JSON editing.
- Changedetection webhook with HMAC-SHA256 validation, ±300s timestamp window,
  body-size limit, SHA-256 receipt deduplication and bounded authoritative
  re-fetch; replay and invalid-signature paths are tested.
- Sheets transactional outbox with 17-column projection, idempotent upserts,
  retry limits and health/status visibility; Sheets is never authoritative.
- Optional SMTP delivery through the standard library, with failures retained
  in the in-app inbox.
- Watchlist next action and follow-up fields, grouped rendering and API
  coverage.
- Health-page cards for changedetection, Telegram, Email, Sheets and optional
  AI.
- Compose secrets mount and Sheets environment variables; ignored local
  `secrets/` directory with `.gitkeep`.
- Migration `d4a7c1e9f210` for discovery promotion, webhook receipts and
  preparation fields.

#### Fixed

- Ashby compensation component IDs/order no longer create false material
  revisions. Semantic compensation changes still count; raw volatile metadata
  does not.
- Two false revisions created before the fix were removed, their prior current
  revisions and monetary JSON restored, and orphaned assessments deleted.
- CI backend commands now run ruff, mypy and pytest from `services/api`, where
  the project configuration applies.

#### Verification

```text
services/api> python -m pytest -q
49 passed, 1 warning in 34.14s

services/api> ruff check app tests scripts
All checks passed!

services/api> mypy app scripts
Success: no issues found in 61 source files

apps/web> npm run typecheck
apps/web> npm run lint
apps/web> npm run build
apps/web> npm run test:e2e
4 passed (6.8s)
```

Clean database migration reached `d4a7c1e9f210` and seeded 17 registry
candidates with zero opportunities. Live database migrated to
`d4a7c1e9f210`; `alembic check` found no pending operations.

Current live totals: 1,053 opportunities (1,048 real plus 5 fixtures), 1,053
source links, 1,054 revisions, 2,900 assessments, 14 reviews, 0 alerts.
Post-fix source scans created no false revisions. A real OpenAI record,
`Communications Lead, Cyber`, was reviewed as Research with a next action and
follow-up and rendered on `/watchlist`.

Restore drill:

```text
docker compose backup: backups/discmon-20261028T173345Z.dump.gz
restore discmon_restore_final:
opportunities=1053, opportunity_sources=1053, reviews=14, digests=2,
alembic_version=d4a7c1e9f210
```

#### Known limitations

- CI, clean-clone Compose, seven-day soak, worker-crash recovery, load tests
  and memory profiling have not been run.
- External integrations are unconfigured; changedetection, Telegram, SMTP and
  Sheets are fixture-tested only.
- A live non-ATS discovery, promotion and Sheets mirroring run has not been
  completed.
- Alerts remain unverified for a newly eligible record; the live table is empty.
- Repeated scans append assessment rows; retention/deduplication is undecided.
