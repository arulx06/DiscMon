# Changelog

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
