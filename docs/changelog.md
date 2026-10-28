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
