# DiscMon progress

## 2026-11-13 — Task 8 Sheets outbox failure recovery

- Verified required base `63bb3fc` on `handoff/stabilize-idfc-audit-20261112`;
  implementation stays on the existing thread branch. **M5 remains PARTIAL.**
- Gateway creation/credential refresh, initial read and empty-sheet header-write
  failures now mark only the locked, selected outbox batch failed, increment
  retries once and record attempt time plus a credential-safe error. The shared
  failure helper also updates integration status without erasing prior success
  time/row key. Row-write errors use the same sanitizer instead of raw exception
  text. Successful recovery clears errors and records a new success time.
- Existing retry cap, skip-locked selection and idempotent row upserts remain;
  instantiated gateways close on preflight failure. Disabled/unconfigured paths
  make no outbound requests and consume no retries. No schema/model changes.
- Deterministic tests use real SheetsGateway HTTP methods through
  `httpx.MockTransport`, dummy tokens and mocked credential loading/refresh.
  Covered credential-load/auth failures, GET 403/429/503 and connection failure,
  header PUT failure, gateway close, batch selection/counts/attempt timestamps,
  retry cap, visible errors, prior-success preservation, recovery/header creation
  and exactly one opportunity row after a subsequent upsert. Persisted
  opportunity/assessment/review snapshots remain unchanged on read failures;
  the existing discovery-to-Sheets lost-acknowledgement regression still passes.
  Its raw-error assertion now requires the sanitized message; safety assertions
  were retained.
- Disposable PostgreSQL **16.15**: newly initialized, thread-owned data directory,
  database `discmon_task8_test`, owner/current/session user `task8`, loopback
  **55438**. Before migration/test execution an independent SQL check verified
  database/user, endpoint, disposable owner and the exact dedicated data directory;
  existing fail-closed test guards run before each cleanup. Only this newly
  created test DB was migrated. No production DB, live credentials/API calls,
  real spreadsheet, external ingestion, deployments, backup changes or
  scheduler/worker services were used.
- Actual local verification from `services/api` (guarded wrapper sets explicit
  matching DB URLs and `APP_ENV=test`):
  - `python -m pytest tests/test_sheets.py tests/test_discovery_to_sheets.py -q`:
    **14 passed**.
  - `python -m pytest tests -q`: **147 passed, 1 warning** (existing feedparser
    deprecation).
  - `python -m ruff check app tests scripts`: **All checks passed!**
  - `python -m mypy app scripts`: **Success: no issues found in 61 source files**.
  - `git diff --check`: **exit 0**.
- Final-head GitHub CI is tracked on the single Task 8 PR; local PostgreSQL 16
  verification is not a claim of CI/PostgreSQL 18 proof. No frontend or browser
  work: the UI contract is unchanged. All Sheets delivery here is emulated,
  not live integration acceptance. Remaining M5 gaps include verified service
  account sharing and real non-ATS discovery → approval/promotion → verification
  → scoring → Sheets mirroring, plus live external integration delivery.
  No merge or Task 9 work is authorized by this entry.

## 2026-11-13 — Task 7 final engineering corrections

- Supersedes the initial Task 7 precedence and E2E seed requirements below.
  Title-first classification is retained. Specific description-level categories
  now precede generic programme/internship wording: generic `Community` title +
  `A fellowship programme for engineers` → fellowship; `A technical residency
  programme` → residency; `An open-source mentorship programme` → mentorship.
  Outreachy + `A full-time internship. Resources: Mentors` remains programme;
  bare `Information for mentors` remains other. Existing explicit-title cases
  and Outreachy parser/API hard-gate/provenance assertions are unchanged.
- The existing labelled maintainer residency demo row now has a null application
  URL; the senior backend demo retains its `/apply` URL. Playwright checks those
  two records rather than requiring a separately ingested Outreachy record.
  Missing fixtures fail explicitly. API regression verifies both demo link
  states and insert-only seed idempotency.
- README now documents the guarded isolated E2E DB migration/`--demo` seed.
  Executed that exact Bash snippet against newly created PostgreSQL 16.15 DB
  `discmon_task7_e2e_test`, user/session user `task7`, loopback port 55437,
  `APP_ENV=test` and matching explicit DB URLs. Existing guards verified actual
  identity/endpoint before migration. Output: registry candidates created=17,
  demo fixtures created=5; all five opportunities labelled, no Outreachy row or
  external collection. No production DB, migration, backfill, deployment,
  runtime smoke drill, worker, scheduler or external write was used.
- Backend regressions ran against the separately guarded `discmon_task7_test`:
  - `pytest tests/test_normalize.py tests/test_wikimedia_outreachy.py tests/test_adapters.py tests/test_ingestion_pipeline.py tests/test_api.py -q`:
    **56 passed, 1 warning in 2.95s**.
  - `pytest tests -q`: **136 passed, 1 warning in 27.14s** (existing feedparser
    deprecation). Ruff: **All checks passed!**; mypy: **Success: no issues found
    in 61 source files**.
- Frontend `npm run typecheck`, `npm run lint`, `npm run build` passed.
  Managed API/web Preview used only the fresh documented demo seed;
  `PLAYWRIGHT_BASE_URL=http://127.0.0.1:3000 npm run test:e2e`:
  **6 passed (3.5s)**, no skips, at 360px/1440px. Both link states, official
  links, review persistence and overflow verified. `git diff --check`: exit 0.
- Final-head GitHub CI evidence is recorded on PR #7. **M5 remains PARTIAL**;
  no historical application URL backfill, dedicated static application-link
  extraction, merge or Task 8 work is included.

## 2026-11-13 — Task 7 evidence-accurate programme metadata (local verification)

- Required base `926551e3c9600b2d58f18083b800bd28864bff0f` confirmed on
  `handoff/stabilize-idfc-audit-20261112`; implementation stays on the thread branch.
- Outreachy changes from heuristic **mentorship** to conservative **programme**.
  Explicit title categories win over incidental body/resource mentions; bare
  mentor mentions no longer establish mentorship. No enum/schema changes.
- Static HTML overview and item links now leave `application_url` **null**.
  Ingestion no longer falls back to the official URL; missing/empty/invalid new
  application evidence preserves a previously supplied valid URL. Explicit
  application URLs from other adapters remain intact; ATS parsers are unchanged.
- Detail UI always retains Official source, hides Application page for null,
  empty or invalid URLs, and retains verified application links. TypeScript
  represents the application URL as nullable.
- The Task 6 fixture's previous assertions encoded the two unsupported heuristic
  assumptions (mentor-link category and article-as-application fallback); these
  are replaced, not the safety assertions. Fixture/API regression still requires
  full-time conflict and excluded hard gate/bucket, unknown professional/India
  eligibility and deadline precision, original page hash and evidence references.
- Isolated local PostgreSQL **16.15**, database `discmon_task7_test`, user/session
  user `task7`, loopback port **55437**. `APP_ENV=test`, matching explicit
  `DATABASE_URL`/`TEST_DATABASE_URL`; existing environment, SQL identity and
  connected-endpoint guards passed before migrating this empty test DB and
  before each test cleanup. No production DB, backups, ingestion, deployment,
  external collection, Sheets writes, workers or scheduler were used.
- Actual commands/results from `services/api`:
  - `../../.venv/bin/pytest tests/test_normalize.py tests/test_wikimedia_outreachy.py tests/test_adapters.py tests/test_ingestion_pipeline.py tests/test_api.py -q`:
    **52 passed, 1 warning in 2.98s**.
  - `../../.venv/bin/pytest tests -q`: **132 passed, 1 warning in 30.06s**.
    Warning: existing feedparser deprecation.
  - `../../.venv/bin/ruff check app tests scripts`: **All checks passed!**
  - `../../.venv/bin/mypy app scripts`: **Success: no issues found in 61 source files**.
- From `apps/web`: `npm run typecheck`, `npm run lint`, `npm run build` passed.
  Managed Preview used only that isolated DB, labelled demo fixtures and a
  fixture-labelled replay of the existing Outreachy HTML through the real
  static parser/ingestion; no live website requests. Browser DOM checks confirmed
  the exact official URL with no application button, and the demo's separate
  verified `/apply` link. `PLAYWRIGHT_BASE_URL=http://127.0.0.1:3000 npm run test:e2e`:
  **6 passed (4.4s)** across 1440px and 360px, including review persistence and
  both link states. The initial E2E attempt could not launch its missing browser;
  installing the matching Playwright Chromium resolved it. E2E now requires both
  the existing demo seed and the fixture-labelled Outreachy replay in its isolated
  test DB; absence fails explicitly instead of skipping the safety check.
- `git diff --check`: **exit 0**. Final-head GitHub CI is recorded on the review
  PR; local PostgreSQL 16 evidence does not substitute for CI's PostgreSQL 18.
- **M5 remains PARTIAL.** Classification is still a conservative heuristic, not
  field-level official confirmation. Static HTML does not discover application
  endpoints in this change. Historical inferred application URLs are not repaired
  or distinguishable from supplied URLs; no backfill/migration is performed.
  Production and external integration acceptance remain unchanged. No merge or
  Task 8 work is authorized.

## 2026-11-13 — Task 6 real non-ATS programme validation

- Live Wikimedia Outreachy discovery → API review/approval/promotion → test-only
  legal approval → ingestion/assessment → fake Sheets outbox completed in
  identity-verified `discmon_programme_test`, using a fresh local PostgreSQL 16
  cluster. Promotion initially remained disabled/legal-review-pending. No
  production changes, external writes, workers, schedulers or notifications.
- Source-exposed fixes: retain exact `www` hostname in static HTML allowlists
  and source-root validation; recognize full-time internship conflicts.
- Actual result: heuristic `mentorship`, score 66, hard gate/bucket excluded;
  professional/India eligibility unknown; deadline/cutoff unknown. Live repeat
  was HTTP 304: one opportunity/revision, no new material change. Fake Sheets
  appended/synced once, then no-op; committed PostgreSQL records reloaded.
- New minimal attributed CC-BY-SA fixture and three deterministic regressions;
  PR #5 connected-flow regression unchanged. Focused: **4 passed in 0.77s**;
  live-only harness: **1 passed in 3.88s**; full backend: **115 passed, 1 warning
  in 25.56s** (existing feedparser deprecation). Ruff: `All checks passed!`;
  mypy: `Success: no issues found in 61 source files`; `git diff --check`: exit 0.
- [Detailed source permission, IDs, provenance, assessment and test evidence](task6-real-programme-validation.md).
  **M5 remains PARTIAL**; real Sheets/external delivery is not verified. GitHub
  CI runs **43419813208 (push)** and **43419845874 (PR)** succeeded on
  implementation head `9416337` (backend, web, compose-preflight). A final
  focused rerun also protects unknown professional eligibility; final-head CI
  is reported on the review PR.

## 2026-11-13 — M5 connected-flow regression (local verification)

- The integration test exposed an ingestion defect: `ingest_source` checked
  only `enabled`, allowing enabled but unapproved or legally pending sources to
  ingest (`DID NOT RAISE`). A minimal guard now requires both
  `ApprovalStatus.approved` and `LegalReviewStatus.approved` before creating a
  run or fetching.
- From `services/api`, with `APP_ENV=test`,
  `TEST_DATABASE_URL=postgresql+psycopg://<test-user>:<test-password>@127.0.0.1:55439/discmon_task5_test`
  and `DATABASE_URL` matching it, using isolated local PostgreSQL 16.15. Actual
  database identity was verified before migration, and the existing fail-closed
  `*_test` connection guards remained intact:
  - `../../.venv/bin/pytest tests -q` — **112 passed, 1 warning in 26.69s**;
    the warning is the existing feedparser deprecation.
  - `../../.venv/bin/pytest tests/test_discovery_webhook.py tests/test_sheets.py tests/test_discovery_to_sheets.py -q` — **6 passed in 1.04s** on the final focused rerun after fake-gateway isolation cleanup (prior run: 6 passed in 1.07s).
  - `../../.venv/bin/ruff check app tests scripts` — `All checks passed!`.
  - `../../.venv/bin/mypy app scripts` — `Success: no issues found in 61 source files`.
  - `git diff --check` — exit 0.
- The local test database was ownership-checked and stopped safely after the
  runs. It is distinct from the accepted M0 PostgreSQL 18.7 cloud drill. M5
  remains **PARTIAL**; CI and live Sheets acceptance are not claimed.

## 2026-11-13 — M0 ACCEPTED

- Accepted at base `2f510c1d82532e1b87acec9082f2c56e073ec07e`; PR #4 was merged.
  Retry 5 received independent engineering acceptance. The supplied evidence
  records 38 Compose tests passing; fresh isolated PostgreSQL 18.7, API and web
  startup; actual database identity verified before the single Alembic upgrade
  to `d4a7c1e9f210`; all 19 tables present with no seeded application records;
  API live/ready and dashboard (`Radar overview`) each HTTP 200; ownership-safe
  cleanup; unchanged Git state; final exit 0.
- Evidence: [Retry 5 report](https://api.hoplite.sh/api/attachments/ceb6a69a074e494ca9c94ef85a6eb650?media=file)
  and [Retry 5 original command transcript](https://api.hoplite.sh/api/attachments/340fa8f8f5e847c3bc51dd29e2fc73d7?media=file).
  This is acceptance of an isolated cloud drill, not a production deployment
  or proof of full outbound network isolation. M0 was recorded from supplied
  evidence; it was not rerun for this documentation update.
- M5 remains **PARTIAL**. The focused connected-flow regression result is
  recorded above; it is not full M5 acceptance or live Sheets acceptance.

The dated entries below preserve the status and evidence recorded at those
earlier attempts; their then-incomplete M0 findings are superseded by this
acceptance, not retroactively changed.

## 2026-11-13 — Task 4B smoke-network compatibility correction (STATIC ONLY)

- Started from accepted handoff commit `edc2fa5b5a2e4dbe7a93611b1ade65f21b6018b6`,
  verified by fresh fetch and remote-head query. New isolated worktree
  `discmon-smoke-network-correction`, branch `hoplite/kios-4aac7279--smoke-networks`.
  All older checkouts preserved; no application/production Compose/preflight/CI edits.
- Retry 1 evidence shows a healthy PostgreSQL 18.7 container with requested
  loopback bindings but null actual publication on an internal-only bridge.
  This is not conclusive proof of an Engine bug. Original evidence remains at
  [Retry 1 report](https://api.hoplite.sh/api/attachments/1a164faf72bc40b2ac23627a83778060?media=file)
  and [original transcript](https://api.hoplite.sh/api/attachments/71d67a3504a54311840a3d919e01d3a0?media=file).
- Smoke now uses scoped `private` (internal) and `ingress` (ordinary) bridges.
  PostgreSQL is private-only with no host port; API/web join both and publish
  only loopback 38000/33000. `--db-port` is rejected. Network definitions and
  service attachments are replaced, not appended. Exact validation still
  rejects extra services/networks/aliases/env/mounts/profiles/external storage.
- Ingress may allow API/web outbound traffic. Disabled integrations are not
  a firewall; this is explicitly not complete egress isolation. DB routing,
  test-only credentials and scoped storage remain unchanged. README updated
  only to remove obsolete flags, ports and egress claims.
- Local Python 3.12.3 / Compose 2.40.3 verification (all sanitized invocations):
  - `python3 -B -m unittest discover -s scripts/tests -p 'test_compose_*.py' -v`:
    `Ran 38 tests in 1.496s`, `OK`, exit 0; 19 unchanged preflight + 19 smoke,
    no skips. Four real-Compose test methods exercise default/custom rendering,
    hostile synthetic env inputs and unsafe merge/mount/config rejections.
  - `python3 -B scripts/compose_preflight.py --project discmon-preflight-network-20261113-a83c`:
    `CONFIG PASS`, exit 0; production checks unchanged, no host-check mode.
  - `python3 -B scripts/compose_smoke.py --project discmon-smoke-network-20261113-a83c`:
    `SMOKE CONFIG PASS`, exit 0 (actual default Compose render).
  - `python3 -B scripts/compose_smoke.py --project discmon-smoke-network-20261113-b94d --api-port 38001 --web-port 33001`:
    `SMOKE CONFIG PASS`, exit 0 (actual custom-port render).
  - Same custom project with `--db-port 56432`: expected `SMOKE REFUSED`, exit 1.
  - AST syntax checks and `git diff --check`: exit 0.
- Read-only identity verification matched the local socket and daemon
  `c6bf35ec-c0e0-4031-b334-8d58d2f76d58` before inventory. Fresh metadata exactly
  matches Retry 1's final snapshot: zero containers/volumes, same three network
  IDs/labels/attachments and retained images. This corroborates cleanup now,
  not an audit of every intervening host action. Original logs are preserved.
- No local build/pull/start/stop/SQL/migration/cleanup or runtime mutation in
  this correction. Runtime publication compatibility is **not verified**;
  a later drill requires new explicit owner authorization. **M0 remains PARTIAL**.


Dates: 2026-10-30 (historical status) and 2026-11-12 (stabilization checkpoint)
Authority: docs/specification.md

## 2026-11-13 Task 3 — isolated smoke configuration (static only)

- GitHub PR #2 was verified `merged=true`; exact squash baseline is
  `685ccd3352d7936f5c0dadd95df17e61d4bf8b74`, equal to the fetched handoff HEAD.
  Its single parent is the accepted `739192275e7d4f239afa2430e36acfd8419feec9`.
  Approved Task 2 preflight/test files match PR #2 head
  `832026c26954a80bae492afdec7b23f4e4c76211` exactly (diff exit 0).
- Fresh separate worktree `discmon-task3`, branch
  `hoplite/m0-isolated-compose-smoke-20261113`, created at that baseline.
  Original worktree/branch `hoplite/samos-f2115cb5` remains clean at `2c31234`;
  no older checkout reset, switched or overwritten.
- New base+smoke overlay removes worker/scheduler/changedetection, private binds,
  inherited environment and production ports. Only PostgreSQL 18/API/web remain,
  with token auth and public test-only credentials, `discmon_smoke_test`, scoped
  pgdata/internal bridge, configurable loopback ports and restart disabled.
- Dedicated standard-library static validator uses the unchanged preflight CLI
  runner, sanitized environment, empty env file and isolated HOME/Docker config.
  Fixed inputs only; validates actual all-profile model and fails closed on
  unsafe resources/routing/ports/mounts, malformed or unsupported Compose.
- Python 3.12.3, Docker CLI 29.1.3 and actual Compose 2.40.3 are available.
  `python3 -m unittest discover -s scripts/tests -v`: **37 passed, 0 failed,
  0 skipped**, exit 0 (19 unchanged preflight + 18 smoke tests; four actual
  Compose test methods, remaining unit/mocked paths and one real socket probe).
  Pycompile and diff checks passed, exit 0. Default/custom-port smoke rendering
  and unchanged production preflight passed (exit 0). Initial inherited-routing refusal was expected (exit 1); routing
  inputs were deliberately unset only for subsequent static invocations.
- PR https://github.com/arulx06/DiscMon/pull/3 targets the handoff branch,
  open/unmerged, update monitoring enabled and auto-merge disabled. Implementation
  commit `dd2c23a` automatic CI passed all three jobs on both push and PR:
  https://github.com/arulx06/DiscMon/actions/runs/43336543594 and
  https://github.com/arulx06/DiscMon/actions/runs/43336552350.
  CI Compose v5.1.3: 37 tests, actual smoke render and unchanged production
  host checks passed. PostgreSQL 18 backend: 111 passed, 1 existing warning;
  Ruff/mypy and web typecheck/lint/build passed. No manual dispatch/rerun.
- No daemon queries, container operations/builds, DB connections, migrations,
  source seeding/ingestion, backup access or private configuration reads were
  performed locally. Production/dev Compose and Task 2 safeguards are unchanged.
  Existing backend/web CI behavior is retained; only a static render step added.
- **M0 remains PARTIAL**. Static validation cannot prove resource freshness,
  ownership, port availability, effective networking or runtime health. An
  independently authorized runtime drill, isolated migration, direct API/web
  checks and ID/label-verified cleanup remain required. Detailed local results
  and delivery evidence follow in the changelog.

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
