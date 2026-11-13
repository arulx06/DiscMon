# Changelog

## 2026-11-13 — Task 17B editable runtime schedule (review-only, not deployed)

- Recovered exact Task 17 `bdc653f`, whose parent is accepted checkpoint `8c54d70`;
  isolated branch `task17b/editable-runtime-schedule`. Original workspace `2c31234`
  was an older ancestor; no accepted work was discarded. Remote handoff still
  resolves to `8c54d70`.
- Add Settings time editor, live duration, saved/host-installed revisions, explicit
  pending/applied/stale/error states and API failure handling, separate from quiet
  hours. Persist a constrained singleton through an additive migration. Serialize
  saves/ACKs with revision conflicts and a PostgreSQL row lock.
- Extend the existing controller with dedicated-token loopback pulls, durable
  private snapshots and offline startup, followed by post-start synchronization.
  No privileged interface mounts, shell interpolation or competing controller.
- Keep 20:30 backup units unchanged. Reject starts after 20:00 and shutdowns
  before 21:00 until an approved backup migration; do not claim unsupported
  windows applied. Completed failed backup warns without blocking forever;
  active/unknown backup, including live control processes, remains conservative.
- Final verification: **304 backend tests**, **79 script tests**, **2 browser E2E
  tests** at 1440px/360px pass. API/host Ruff, focused mypy, frontend lint and
  typecheck, production build, Python compilation, Bash syntax, systemd unit
  validation, calendar validation and diff check all exit **0**. Fresh isolated
  migration upgrade/downgrade/upgrade passes. Real local host snapshot/ACK and
  browser status/error assertions pass. One pre-existing feedparser warning.
- Production-build browser verification resolved the dev/HMR hydration failure;
  no assertions were relaxed. Exact outcomes and recovered failures are in
  `docs/evidence/task17b-runtime-validation.txt`. Architecture, files, limits and
  review notes: `docs/task17b-review.md`; owner installation/rollback and safe
  earlier-shutdown transition policy: `docs/runtime-schedule.md`.
- Live deployment, database, backup units and data untouched. No ingestion,
  Docker start/stop, systemd installation/enablement, merge or deployment. Actual
  laptop boot/resume and production adoption remain unverified and approval-gated.

## 2026-11-13 — Task 17 Ubuntu daily runtime (not deployed)

- Baseline `8c54d70`, branch `handoff/stabilize-idfc-audit-20261112`.
  The prior checkpoint-to-baseline diff is exactly 67 files / 11,290 additions /
  306 deletions; none was introduced or reverted by Task 17.
- Add a bounded current-time Kolkata reconciler and one service/timer pair for
  the existing five-container Compose stack. Verify project/file/volume identity,
  disable container auto-restart, serialize with backups, and stop gracefully
  without a forced-kill timeout. Never create/remove containers or volumes.
- Add only a shared lock to the backup script; existing live backup units remain
  untouched. Failed/unknown/busy backup status fails closed. Missed backups are
  not replayed and do not cause an overnight restart. Safety can delay shutdown.
- Offline validation: `python3 -m unittest discover -s scripts/tests -p
  test_runtime_schedule.py -v`: **25 tests passed**; `python3 -m unittest discover
  -s scripts/tests`: **63 tests passed**. Ruff, Python compilation, Bash syntax,
  systemd unit verification, timezone/calendar checks and diff check all exit
  **0**. Exact outputs: `docs/evidence/task17-runtime-validation.txt`.
- Installation/verification/rollback and residual limits: `docs/runtime-schedule.md`.
  No live Docker/systemctl operation, database write/migration, ingestion, service
  installation/enablement, push, merge or deployment. Application/Compose files
  unchanged; laptop behavior remains unverified until owner-approved adoption.

## 2026-11-13 — Task 16 offline Telegram consent and delivery regression

- Reuse existing alert/queue/worker path; recheck owner opt-in at dispatch and
  retain revoked queued Telegram rows as suppressed. Preserve in-app/SMTP behavior.
- Serialize dispatch with per-alert locks, a durable failed/manual-review claim
  before Telegram I/O and a profile lock across the consent/send boundary. Never
  automatically replay ambiguous outcomes; no exactly-once guarantee is claimed.
- Require valid Telegram `ok=true`/message-ID/trusted-chat acknowledgement before
  sent status; sanitize failures, bound definite rejection retries, stop on
  authorization/rate limits, validate numeric chat configuration and avoid HTTPX
  logging of credential-bearing bot URLs. Fix the fresh-profile enum constructor
  demonstrated by the real profile API regression. No schema migration.
- Regression-first evidence: **15 failed** at the fresh-profile API, then **14
  failed/1 passed** after only that enum fix; deterministic concurrent baseline
  dispatch returned processed **2**, expected **0**. Final offline focused tests:
  **31 passed in 4.47s** (22 simulated Telegram requests, no real messages);
  full PostgreSQL 18 suite: **297 passed, 1 warning in 96.56s**; Ruff passed;
  mypy passed **61 files**; diff check passed. Commands/assertions/isolation and
  cleanup recorded in `docs/evidence/task16-telegram-offline.md`.
- Update operations for opt-in, `/start`/trusted-chat setup, revocation, quiet hours
  and safe manual reconciliation. **M5 PARTIAL**; no real Telegram/SMTP acceptance,
  deployment or merge. Final-head CI evidence belongs to the review PR handoff.

## 2026-11-13 — Task 15B correct newly queued discovery reporting

- Correct discovery-specific enqueue reporting with atomic insert/returning:
  idempotency conflicts now return `None`, not an old completed/dead job ID.
  Shared enqueue behavior, ingest locking and weekly/monthly cadence keys remain
  unchanged. No migration, worker or scheduler rewrite.
- Demonstrated 4 pre-fix failures for weekly/monthly succeeded/dead repeats;
  added 10 regressions covering terminal/active states, restart, independent
  sources/next period, concurrent ticks, synchronized insert collision and
  suppression of misleading discovery activity logs. Original 39 Task 15
  focused cases are preserved; **49 focused passed** after correction.
- Final local checks, all exit 0: **49 focused passed**, **35 existing connected
  regressions passed**, **268 full backend passed** (one existing feedparser
  warning), Ruff clean, mypy clean (61 files), whitespace clean. Owned PostgreSQL
  18.7 container/volume removed; exact commands, isolation identity, before/after
  results and cleanup evidence are recorded in `PROGRESS.md`; final-head
  backend/web/Compose CI is tracked on existing PR #14. No generated logs,
  live-provider access, production change, merge or deployment. **M5 PARTIAL**.

## 2026-11-13 — Task 15 monthly discovery scheduling

- Add explicit `config_json.discovery.cadence="monthly"` without a migration:
  day 1 at 09:00 Asia/Kolkata, current-month catch-up, source/year/month
  idempotency. Omitted/explicit weekly cadence preserves Monday/ISO-week behavior.
  Invalid cadences fail closed with a bounded count in scheduler diagnostics;
  unrelated scheduler operations continue.
- Reuse the existing queue/worker/discovery/review path with no changes to queue
  locking, models, APIs or source authorization. Added 38 scheduling regressions
  and one connected monthly worker/owner-review scenario, including next-month
  candidate deduplication, pending legal review, idempotent disabled promotion
  and failed-scan preservation. Only synthetic HTTP and DNS are intercepted.
- Fresh isolated PostgreSQL 18.7, empty-schema identity proof before migration;
  focused **39 passed**, connected discovery/webhook/queue/worker regressions
  **35 passed**; full backend **258 passed, 1 existing feedparser warning**; Ruff clean, mypy clean (61 files),
  whitespace check clean. Commands, actual synthetic IDs, timestamps, keys,
  worker/audit counts and cleanup are recorded in `PROGRESS.md`; final-head
  backend/web/Compose CI is recorded on the review-only PR.
- Document weekly defaults, monthly opt-in, IST window/catch-up, idempotency
  retention, diagnostics and deliberate candidate review. No live provider,
  delivery, credentials, production state, schema change or deployment.
  **M5 remains PARTIAL**; no search/AI discovery or M6 work.

## 2026-11-13 — Task 14 GitHub-watch ingestion and revision verification

- Add two deterministic release fixtures and **35 regressions**: 15 real
  PostgreSQL/API/queue/worker connected cases and 20 adapter safety cases.
  Prove one release's date-only deadline update yields one new material revision
  and alert, preserves original evidence and coalesces Sheets work; unchanged
  repeats and provider failures cannot duplicate or erase canonical output.
- Fix five reproduced GitHub-only defects: reject malformed API shapes instead
  of reporting empty success, skip issue-feed pull requests, avoid merging owners
  through `github.com`, leave unverified application URLs absent and persist
  original API objects as evidence. Existing queue locks/UUID generations and
  application services remain unchanged; no migration or record backfill.
- Isolated PostgreSQL **18.7**, cluster **7707688725725106215**,
  `discmon_task14_test`, user `discmon_task14`, loopback **127.0.0.1:55434**;
  independently empty before migration. All exit 0: new **35 passed**; existing
  adapter/ingestion/queue/Task 13 **40 passed**; full backend **219 passed** with
  one existing feedparser warning; Ruff clean; mypy clean (**61 files**);
  `git diff --check` clean. Commands/isolation proof are recorded in `PROGRESS.md`;
  actual outputs and pre-fix failures are supplied separately, not committed logs.
- Task-only container/volume cleanup; no live provider access, delivery, Sheets
  writes, secrets, production state, deployments or merge. **M5 remains PARTIAL**;
  final-head backend/web/Compose CI and independent review belong to the single PR.

## 2026-11-13 — Task 13 webhook-to-worker material revision regression

- Add two deterministic official-style fellowship HTML fixtures and 16 connected
  PostgreSQL cases: signed webhook → approved source/watch → queue → real worker
  processing → safe collection → material revision/evidence → assessment/alerts.
  Assert all required authentication, approval, URL-authority, failure, precision,
  eligibility and dedup negatives without replacing application services.
- Fix two reproduced queue defects only: serialize source enqueue decisions with
  a source-row `FOR NO KEY UPDATE` lock and replace second-granularity generation
  keys with UUIDs. Prevent overlapping active jobs and allow genuinely new work
  immediately after completion. Existing webhook/ingestion architecture unchanged.
- Final isolated PostgreSQL 18.7 run, all exit 0: focused **16 passed**; combined
  webhook/queue/ingestion **30 passed**; full backend **184 passed, 1 existing
  warning**; Ruff clean; mypy clean (**61 files**); `git diff --check` clean.
  Exact commands, test DB/cluster identity and synthetic before/after records are
  in [Task 13 execution evidence](task13-execution-evidence.txt) and `PROGRESS.md`.
  Final-head CI is tracked on the single PR; no historical CI is substituted.
- Test container/volume removed; no live provider/credentials, external delivery,
  production state, scheduler or deployment used. **M5 remains PARTIAL**: offline
  webhook proof is not live provider/delivery or full integration acceptance.

## 2026-11-13 — Task 12A Google requests transport dependency

- Declare `google-auth[requests]>=2.40,<3.0`, preserving version bounds and the
  existing Sheets authentication mechanism. Google's installed **2.62.2**
  metadata confirms the supported extra requires `requests>=2.30.0,<3.0.0`.
  A clean unchanged install reproduced the import failure (exit 1).
- Add a real, unmocked `Request` import/construction regression with session
  cleanup and no credentials or Google API calls. No backend lockfile or CI
  changes are necessary.
- Fresh Python **3.12.3** venv: `python -m pip install ./services/api`, real
  transport construction and `python -m pip check` all exit 0 before dev-extra
  installation; Google Auth **2.62.2** brings **requests 2.34.2** through the
  declared dependency graph, never a manual install. Exact commands and resolved
  transport package versions are recorded in `docs/PROGRESS.md`.
- New tmpfs-only PostgreSQL **18.7** cluster `7707671447009542184`, database
  `discmon_task12a_test`, user `discmon_task12a`, loopback **127.0.0.1:55482**;
  verified empty before migration, isolated test environment, matching test URLs
  and unchanged fail-closed guards. Disposable resources cleaned after tests.
- Actual checks, all exit 0: `python -m alembic -c alembic.ini upgrade head`;
  `python -m pytest tests/test_sheets.py -q` (**34 passed**);
  `python -m pytest tests -q` (**168 passed, 1 existing warning**);
  `ruff check app tests scripts` (**All checks passed!**);
  `mypy app scripts` (**61 source files, no issues**); `git diff --check`.
  Final-head backend/web/Compose CI evidence is recorded on the Task 12A PR.
- No live Google, source collection, notifications or production access.
  **M5 remains PARTIAL; original Task 12 live connected acceptance is pending.**
  This dependency fix does not complete that acceptance. No merge or deployment.

## 2026-11-13 — Task 11 PostgreSQL 18 connected Sheets HTTP proof

- Extended the existing discovery-to-Sheets regression without changing services:
  real gateway GET/header PUT/append POST/retry row PUT/independent GET over
  deterministic MockTransport, 17 columns, lost-ack HTTP 503, one retry,
  sanitized errors, successful SyncState recovery and no duplicate remote row.
- Retained approval/legal negatives; added persisted canonical/source-link/
  evidence/assessment snapshots, evidence hash/provenance, conservative
  eligibility/deadlines and zero-alert assertions. Generalized the existing test
  snapshot utility's ordering for composite primary keys.
- Fresh task-only PostgreSQL **18.7**, database `discmon_task11_test`, user
  `task11`, loopback `127.0.0.1:55441`, zero initial public tables verified
  before schema creation; matching explicit test URLs and fail-closed guards.
- Actual local output (all exit 0, commands/details in `docs/PROGRESS.md`):
  focused pytest **34 passed**; full backend **167 passed, 1 existing warning**;
  Ruff **All checks passed!**; mypy **no issues found in 61 source files**;
  migrations and `git diff --check` **exit 0**. Final-head PostgreSQL 18 backend,
  web and Compose CI results are attached to the Task 11 PR.
- Task 10 was not repeated; no live provider/production resources were accessed.
  **M5 remains PARTIAL**: fixture-connected proof does not close live non-ATS
  connected acceptance or the remaining source/integration gaps. No merge/deploy.

## 2026-11-13 — Task 9 Sheets mirror integrity and mixed-batch errors

- Required base verified as `c9b6555` on
  `handoff/stabilize-idfc-audit-20261112`. **M5 remains PARTIAL.**
- Read the entire quoted tracker tab before writes, so unexpected content after
  column Q cannot be mistaken for an empty sheet. Validate the ValueRange
  envelope, row/cell structures, exact ordered headers and unique nonempty
  opportunity IDs. Only an empty tracker receives the existing approved header;
  no automatic header repair, row deletion or deduplication. Short rows and
  blank physical rows remain valid without renumbering updates.
- Invalid remote data uses Task 8's sanitized selected-batch failure handling,
  retaining bounded retries and canonical PostgreSQL records. Success reconciles
  against unresolved failed outbox rows, including retry-exhausted rows; status
  also checks the outbox rather than trusting stale all-clear state. Successful
  timestamps/row keys survive failures, and genuine recovery clears the error.
  No schema, dependency, frontend or collector changes.
- Added deterministic real-gateway HTTP regressions using `httpx.MockTransport`
  and dummy tokens: empty and omitted-values initialization, correct/ragged
  trackers with blank rows, reordered/wrong/missing headers, malformed JSON,
  unexpected response/value/row/cell types, invalid metadata, extra columns,
  duplicate IDs, no invalid-sheet writes, selected-only sanitized failures and
  canonical snapshots. Mixed-batch tests exercise both operation orders,
  exhaustion, stale status, preserved attempt/success metadata and recovery.
  Existing idempotent upsert and discovery lost-acknowledgement tests pass.
- Before migrations/tests, an independent SQL check proved a newly initialized,
  thread-owned PostgreSQL **16.15** instance: database `discmon_task9_test`,
  owner/current/session user `task9`, loopback endpoint **127.0.0.1:55439** and
  dedicated disposable data directory. The guarded command wrapper rechecks
  identity, ownership and endpoint; existing fail-closed test guards are intact.
  Only this disposable database was migrated/tested.
- Actual final local results from `services/api`, with explicit matching test
  database URLs and `APP_ENV=test`:
  - `python -m pytest tests/test_sheets.py tests/test_discovery_to_sheets.py -q`:
    **34 passed in 3.26s**.
  - `python -m pytest tests -q`: **167 passed, 1 warning in 28.92s**
    (existing feedparser deprecation).
  - `python -m ruff check app tests scripts`: **All checks passed!**
  - `python -m mypy app scripts`: **Success: no issues found in 61 source files**.
  - `git diff --check`: **exit 0**.
- Final-head GitHub CI (backend, web and Compose preflight/smoke) is recorded on
  the single Task 9 PR. Local PostgreSQL 16 results are not PostgreSQL 18 CI
  proof. Sheets HTTP responses are emulated, not live Google acceptance.
  No production database, live Google credentials/requests, production ingestion,
  deployments, backup changes or production restarts were used. Live external
  integration acceptance remains outstanding; no merge or Task 10 is authorized.

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

## 2026-11-13 — M5 connected discovery-to-Sheets regression

The integration test exposed that `ingest_source` checked only `enabled`, so an
enabled but unapproved or legally pending source could ingest; the initial test
failed with `DID NOT RAISE`. A minimal guard now requires both
`ApprovalStatus.approved` and `LegalReviewStatus.approved` before creating a run
or fetching.

From `services/api`, tests ran with `APP_ENV=test`,
`TEST_DATABASE_URL=postgresql+psycopg://<test-user>:<test-password>@127.0.0.1:55439/discmon_task5_test`
and matching `DATABASE_URL`, using isolated local PostgreSQL 16.15. Actual
database identity was verified before migration; the existing fail-closed
`*_test` connection guards remained intact. The full and focused test runs, lint
and type checks passed:

```text
../../.venv/bin/pytest tests -q
112 passed, 1 warning in 26.69s (existing feedparser deprecation)
../../.venv/bin/pytest tests/test_discovery_webhook.py tests/test_sheets.py tests/test_discovery_to_sheets.py -q
6 passed in 1.04s (final focused rerun after fake-gateway isolation cleanup; prior run 1.07s)
../../.venv/bin/ruff check app tests scripts
All checks passed!
../../.venv/bin/mypy app scripts
Success: no issues found in 61 source files
git diff --check
exit 0
```

The local PostgreSQL cluster was ownership-checked and stopped safely after
verification. This PostgreSQL 16.15 test target is separate from the accepted
M0 PostgreSQL 18.7 cloud drill. M5 remains **PARTIAL**; CI and live Sheets
acceptance are not claimed.

## 2026-11-13 — M0 ACCEPTED

PR #4 was merged. Retry 5 received independent engineering acceptance at base
`2f510c1d82532e1b87acec9082f2c56e073ec07e`. The supplied evidence records 38
Compose tests passed; fresh isolated PostgreSQL 18.7, API and web startup; actual
database identity verified before one Alembic upgrade to `d4a7c1e9f210`; all 19
tables present with no seeded application records; API live/ready HTTP 200 and
dashboard HTTP 200 (`Radar overview`); ownership-safe cleanup; unchanged Git
state; and final exit 0.

Evidence: [Retry 5 report](https://api.hoplite.sh/api/attachments/ceb6a69a074e494ca9c94ef85a6eb650?media=file)
and [Retry 5 original command transcript](https://api.hoplite.sh/api/attachments/340fa8f8f5e847c3bc51dd29e2fc73d7?media=file).
This records acceptance from supplied evidence, not a rerun. It demonstrates an
isolated cloud drill only, not production deployment or full outbound network
isolation. M5 remains **PARTIAL**; the focused fixture-backed connected-flow
result is recorded above and does not constitute full M5 or live Sheets
acceptance.

Earlier entries retain the incomplete status observed during those attempts;
this dated acceptance supersedes those statuses without rewriting their history.

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


## 2026-11-13 — Task 3: isolated Compose smoke model (STATIC ONLY)

### A. Verified checkpoint and worktrees

- `gh api repos/arulx06/DiscMon/pulls/2` returned `merged=true`, `state=closed`,
  base `handoff/stabilize-idfc-audit-20261112`, approved head
  `832026c26954a80bae492afdec7b23f4e4c76211`, squash merge
  `685ccd3352d7936f5c0dadd95df17e61d4bf8b74`.
- `git fetch origin handoff/stabilize-idfc-audit-20261112` and
  `git rev-parse FETCH_HEAD` returned exactly that squash SHA. Its single parent
  is accepted checkpoint `739192275e7d4f239afa2430e36acfd8419feec9`.
- `git fetch origin refs/pull/2/head` followed by
  `git diff --exit-code FETCH_HEAD 685ccd3352d7936f5c0dadd95df17e61d4bf8b74 -- scripts/compose_preflight.py scripts/tests/test_compose_preflight.py`
  exited 0: both approved Task 2 files are byte-identical at the new baseline.
- `git worktree add -b hoplite/m0-isolated-compose-smoke-20261113 ../discmon-task3 685ccd3352d7936f5c0dadd95df17e61d4bf8b74`
  exited 0. No prior worktree reused or reset. Original worktree remains on
  `hoplite/samos-f2115cb5` at `2c31234e1ece52f988aa6e9aded32f6c55feefd3`, clean.

### B. Implementation and resolved model

Changed files (only this bounded scope):

- `docker-compose.smoke.yml` — new test-only override.
- `scripts/compose_smoke.py` — new fixed-input redacted static validator.
- `scripts/tests/test_compose_smoke.py` — focused unit and actual-render tests.
- `.github/workflows/ci.yml` — additional static smoke-render step only.
- `README.md`, `docs/deployment.md`, `docs/operations-runbook.md`,
  `docs/PROGRESS.md`, `docs/changelog.md` — usage, limits and evidence.

The production/dev YAML and both Task 2 Python files have no diff. Application,
schema, migrations, worker/scheduler and frontend behavior are unchanged.

Actual Compose 2.40.3 rendering of base + smoke with **all** profiles enabled
contains exactly postgres/API/web, none profiled, all `restart: no`. Worker,
scheduler and changedetection are removed, including the changedetection volume
and unused base environment extension. `!override` replaces published ports
and environments; `!reset` removes services/private mounts. Default model:

```text
project: discmon-smoke-20261113-a17c
postgres: postgres:18-alpine; 127.0.0.1:56432 -> 5432/tcp
api: 127.0.0.1:38000 -> 8000/tcp; no volumes
web: 127.0.0.1:33000 -> 3000/tcp; no volumes
volume: discmon-smoke-20261113-a17c_pgdata -> /var/lib/postgresql
network: discmon-smoke-20261113-a17c_default; internal bridge
API DB: postgres:5432/discmon_smoke_test; user discmon_smoke_user
web API: http://api:8000; matching test-only auth token
PG health: pg_isready -U discmon_smoke_user -d discmon_smoke_test
```

The static validator verifies cross-service database username/password/database
consistency without printing values. No external resources, host storage,
private mounts, fixed container names, env files, optional integrations or
inherited production bindings are accepted. Credentials are public test-only
placeholders, never production secrets. No images were built.

### C. Local verification

Environment: Python 3.12.3, Docker CLI 29.1.3, system Compose
2.40.3+ds1-0ubuntu1~24.04.1. Docker engine availability was **not queried**;
a daemon is unnecessary for config rendering.

Exact static invocations below all exited 0:

```bash
python3 -m unittest discover -s scripts/tests -v
python3 -m py_compile scripts/compose_preflight.py scripts/compose_smoke.py scripts/tests/test_compose_preflight.py scripts/tests/test_compose_smoke.py
git diff --check
git diff --exit-code 685ccd3352d7936f5c0dadd95df17e61d4bf8b74 -- docker-compose.yml docker-compose.dev.yml scripts/compose_preflight.py scripts/tests/test_compose_preflight.py

env -u COMPOSE_FILE -u COMPOSE_PROJECT_NAME -u COMPOSE_ENV_FILES \
  -u COMPOSE_PROFILES -u DOCKER_HOST -u DOCKER_CONTEXT \
  python3 scripts/compose_smoke.py --project discmon-smoke-20261113-a17c

env -u COMPOSE_FILE -u COMPOSE_PROJECT_NAME -u COMPOSE_ENV_FILES \
  -u COMPOSE_PROFILES -u DOCKER_HOST -u DOCKER_CONTEXT \
  python3 scripts/compose_smoke.py --project discmon-smoke-20261113-b28d \
  --db-port 56433 --api-port 38001 --web-port 33001

env -u COMPOSE_FILE -u COMPOSE_PROJECT_NAME -u COMPOSE_ENV_FILES \
  -u COMPOSE_PROFILES -u DOCKER_HOST -u DOCKER_CONTEXT \
  python3 scripts/compose_preflight.py --project discmon-preflight-20261113-a17c
```

Observed output: `Ran 37 tests in 1.314s`, `OK`; **37 passed, 0 failed,
0 skipped**, exit 0. This comprises 19 unchanged production preflight tests and
18 smoke tests. Four test methods use **actual Compose** (existing base/dev
fresh-copy and malformed config; new default/custom-port hostile-env checks and
negative port-merge/secret-mount/malformed-YAML cases). The other 32 methods use
fixture-only/mocked paths, plus one existing real ephemeral socket probe.
Version/capability refusal is simulated; actual v2.40.3 rendering is not mocked.

Smoke negative cases cover protected project names, reused/external/custom
resources, binds/secrets, retained production or public ports, enabled workers/
scheduler/changedetection/profiles, canonical/remote/mismatched DB routing,
missing/wrong PostgreSQL image/healthcheck, malformed JSON/YAML, credential
leakage, unsupported capabilities and inherited/unknown CLI routing inputs.
Actual negative renders fail closed; no unsafe input is executed as a service.

The initial smoke invocation without unsetting inherited routing inputs refused
with exit 1 and the redacted error `Unexpected inherited Compose/Docker routing
input; unset it before static inspection.` This was the expected safeguard,
not a render pass. Only later static invocations deliberately removed those
inputs; no daemon or remote host check was attempted.

### Automatic CI and delivery

Implementation commit `dd2c23a` passed every job (backend, web,
compose-preflight) on both automatically triggered runs:

- Push: https://github.com/arulx06/DiscMon/actions/runs/43336543594 — **success**.
- PR: https://github.com/arulx06/DiscMon/actions/runs/43336552350 — **success**.

CI's system Compose **v5.1.3** passed all **37** unit/static tests, the real
smoke render and the unchanged production host checks. Backend PostgreSQL 18:
`111 passed, 1 warning` (existing feedparser deprecation), Ruff `All checks
passed!`, mypy `Success: no issues found in 61 source files`. Web typecheck,
lint and build passed. No workflow was dispatched or rerun manually. Existing
CI alone runs its pre-existing ephemeral test database migration; no local DB,
manual migration or smoke runtime drill was performed.

PR https://github.com/arulx06/DiscMon/pull/3 targets
`handoff/stabilize-idfc-audit-20261112`, stays open/unmerged, and is linked to
update monitoring with `reviewLoop.enabled=true`, `autoMerge=false`.
GitHub auto-merge request is null. Both worktrees were preserved; original
checkout remains clean and the new feature worktree is committed. This
follow-up only records observed CI evidence; runtime acceptance remains pending.

### D. Safety and remaining acceptance gaps

Locally, Docker subprocesses were restricted to `compose version`, `compose
config --help` and `compose config`. No `info`, runtime inventory, container
start/stop/restart/build, compose up/down/run/exec, DB connection, migration
(including test migration), source seed/ingestion, backup/restore or volume
operation was performed. Temporary test inputs and HOME/Docker config directories
are ordinary local files, not Docker resources. Existing preflight host-failure
paths are mocked; its occupied-port test uses only an ephemeral local socket.
No production `.env`, repository secrets or private Docker configuration was
read; synthetic hostile test files are generated only inside temporary copies.

Static success proves the **configuration model**, not resource freshness,
port availability, Docker engine availability, effective networking, app health
or clean-checkout acceptance. API readiness only checks `SELECT 1`, not migrated
schema; the web dashboard needs schema. Future explicit owner authorization is
required for resource inventory, isolated build/start/volume creation, verified
isolated migration, direct API live/ready plus independent web checks, and
cleanup of only IDs positively matched to this run's inventory and labels.
Source import, ingestion and worker/scheduler startup remain separately gated.
No `compose down -v` or blanket pruning is permitted. M0 remains **PARTIAL**.

## 2026-11-12 — Task 2: non-destructive Compose preflight

### Scope and safety

Added `scripts/compose_preflight.py` and standalone unittest coverage; added one
independent config-only CI job without changing backend/web jobs. README,
deployment and operations docs distinguish this inspection from state-changing
deployment and document the future separately authorized clean-volume drill.
Production Compose, application, schema and fixture code are unchanged.

The script's only Docker commands are Compose version/config and, optionally,
info plus container/volume/network list queries. No up/down/exec/run/restart/
pull/build, migrations, seed/collector/worker/scheduler launch, backup/restore,
volume creation/removal or database connection is present. Compose JSON and CLI
diagnostics are captured, never forwarded. Output contains only validated
identities, service/profile/port metadata and fixed redacted routing. A temporary
empty HOME/DOCKER_CONFIG, sanitized subprocess environment, explicit files,
`--env-file /dev/null` and `--no-env-resolution` prevent implicit private inputs.
The real-Compose test uses a deliberately invalid synthetic `.env` in a fresh
temporary copy: successful rendering demonstrates it is ignored. No existing
`.env`, secret file, backup or database was opened. Host inventories read only
names/labels/published ports; they never inspect container environments or mounted contents.

### Local command evidence

Commands run from the separate worktree root unless stated otherwise:

```text
docker --version
Docker version 29.1.3, build 29.1.3-0ubuntu3~24.04.2; exit 0
docker compose version
Docker Compose version 2.40.3+ds1-0ubuntu1~24.04.1; exit 0
python3 --version
Python 3.12.3; exit 0

python3 -m unittest discover -s scripts/tests -v
Ran 19 tests; OK; exit 0 (0 failed, 0 skipped)
python3 -m py_compile scripts/compose_preflight.py scripts/tests/test_compose_preflight.py
exit 0
git diff --check
exit 0, no output

python3 scripts/compose_preflight.py --project discmon
PREFLIGHT REFUSED: Require a unique non-production ... identity; exit 1

# Only removes routing input for this single local static inspection command.
env -u DOCKER_HOST -u DOCKER_CONTEXT -u COMPOSE_FILE -u COMPOSE_PROJECT_NAME -u COMPOSE_ENV_FILES -u COMPOSE_PROFILES python3 scripts/compose_preflight.py --project discmon-preflight-20261112-a17c
CONFIG PASS; exit 0; both base and base+dev rendered, no daemon queried
# Same env prefix, adding --check-host:
PREFLIGHT REFUSED: Local Docker daemon unavailable; host isolation NOT established.
exit 1; no runtime changes
```

Initial unmodified invocation refused inherited Docker/Compose routing input
(exit 1), intentionally without printing values. Clearing those variables did
not change any saved configuration or access a remote daemon. Host checks use
the local default socket only. Docker daemon unavailability is not static
render failure and was not worked around by starting/replacing services.

### Initial CI compatibility finding

The first automatic push run `43317856314` and PR run `43317907260` rejected
runner Compose at the version-major guard (18 tests, one error in the real
Compose positive test). No unsafe fallback or runtime action was attempted.
Docker's current official documentation states that Compose v2 and v5 use the
same CLI/specification, with v5 functionally identical to v2:
https://docs.docker.com/compose/intro/history/
The guard now accepts these two supported majors, still probes required config
capabilities and applies every resource/routing check. A positive mocked v5
case was added (19 tests total); unsupported v1 remains rejected. No dependency
was changed. CI now prints only Docker/Compose versions before the checks.

### Automatic CI evidence for code commit `2dc57fa`

- `gh run watch 43318019528 --repo arulx06/DiscMon --exit-status --interval 15`
  exited 0. PR run https://github.com/arulx06/DiscMon/actions/runs/43318019528
  concluded **success**; backend, web and compose-preflight all succeeded.
- New non-mutating job: Docker 29.4.2 / Compose v5.1.3 / Python 3.12.16;
  `python3 -m unittest discover -s scripts/tests -v`: 19 tests, OK, exit 0.
  Actual `--check-host` printed `HOST CHECK PASS` and `CONFIG PASS`, exit 0.
  Job: https://github.com/arulx06/DiscMon/actions/runs/43318019528/job/131531015060
- Push run's preflight also succeeded:
  https://github.com/arulx06/DiscMon/actions/runs/43318008627/job/131530975717
  (`19 tests`, `HOST CHECK PASS`, exit 0). Its web job passed as well.
- Unchanged backend job on ephemeral PostgreSQL 18: `111 passed, 1 warning in
  31.51s`; Ruff `All checks passed!`, mypy `Success: no issues found in 61 source
  files`. Web typecheck, lint and production build passed. Existing CI migration
  occurred only inside that pre-existing job's disposable database, not locally
  and not against production; no manual migration or workflow dispatch occurred.
- Initial code `7c8f61c` runs `43317856314` (push) and `43317907260` (PR) failed
  the new preflight job's version guard; fixed rather than skipped. No tests or
  isolation checks were weakened. Runner action-deprecation/ubuntu-label notices
  were observed; unrelated action/dependency upgrades are outside Task 2.
- PR https://github.com/arulx06/DiscMon/pull/2 targets the required handoff branch,
  remains unmerged, with update monitoring enabled and auto-merge disabled.
  This evidence-only documentation commit will trigger fresh automatic checks;
  current-head results are attached to the PR, not a claim of runtime acceptance.

### Test interpretation and remaining gap

Positive tests inspect real base and dev JSON and a fresh temporary Compose
copy. Negative coverage includes protected/empty/malformed project identities,
unknown secret-bearing arguments, inherited Compose/Docker routing, absent
Docker/Compose, old Compose, malformed JSON and actual invalid YAML, external or
unscoped volume/network reuse, host/private binds, published port overlap or
wildcard bindings, profile/service changes and external/ambiguous database
routing. Mocked host tests cover existing names and project labels for each
resource kind, unavailable daemon and occupied fixed ports. Docker NAT port mappings/ranges are checked even without a socket listener.
One real local
socket test confirms occupied-port rejection. A fake subprocess allowlist
asserts the complete command set is non-mutating and app secrets are not passed
to Compose; sentinel credentials never appear in output or errors.

Static success does not check existing resources, prove unique/disposable
volumes or reserve ports. Host success is a point-in-time read-only prerequisite,
not a runtime authorization. All profiles are inspected, including optional
changedetection. Current fixed ports and secret-directory binds mean a separate
reviewed test-only override is still required before a future authorized drill.
**M0 remains PARTIAL**, full fresh-volume runtime acceptance not executed.

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
