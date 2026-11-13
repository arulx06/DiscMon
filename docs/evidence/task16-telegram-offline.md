# Task 16 — offline Telegram delivery acceptance

## Boundary and baseline

This is synthetic, offline transport acceptance, **not live provider acceptance**.
M5 remains **PARTIAL**. No real `/start`, Telegram message, SMTP message, Sheets,
GitHub collection, changedetection service or AI interaction was performed.
Only ordinary dependency installation and GitHub source-control/CI were permitted.

`git ls-remote origin refs/heads/handoff/stabilize-idfc-audit-20261112` returned
`c297fbded3fa9f9642e16119767632685aaf6490`, also rechecked before publication.
The original clean `hoplite/barke-86fff0a1` checkout was preserved. A new isolated
worktree and `hoplite/barke-86fff0a1--task16` branch were created at that commit.
No migrations, consent schema, broker, queue implementation or worker architecture
were added. Final-head identity and GitHub checks are attached to the PR.

## Isolation proof before existing migrations

Initial Docker container/volume inventories were empty. Created only:

- Container `discmon-task16-pg`, ID prefix `49da6bdcae55`, label `discmon.task=16`.
- Named volume `discmon-task16-pgdata`, same task label; mounted at
  `/var/lib/postgresql` (PostgreSQL 18 image layout).
- Image `postgres:18-alpine`, server PostgreSQL **18.7**, cluster system identifier
  **7707706081711407144**.
- Database `discmon_task16_test`; current/session user both `task16`.
- Explicit application endpoint `127.0.0.1:55436`, Docker-published only on loopback;
  server `172.17.0.2:5432`, server-observed client `172.17.0.1:34602` during the
  pre-migration TCP identity query. The preliminary in-container identity query
  used a Unix socket and therefore returned null inet endpoints, as expected.
- Public schema contained **0 tables** before migrations, confirmed through TCP.
- Existing Alembic revisions `b76e2a98caca` then `d4a7c1e9f210` applied, exit **0**.

Commands ran through a task-local Python subprocess launcher with a newly built
minimal environment: only PATH/HOME/LANG inherited, `APP_ENV=test`, disabled test
owner auth and identical explicit `DATABASE_URL`/`TEST_DATABASE_URL` targeting the
above database using a synthetic task-only password. No inherited `PG*` or real
provider variables. No `.env` was added. The repository's fail-closed target,
connected identity and destructive-test guards were unchanged. Python **3.12.3**;
`uv venv` and editable `services/api[dev]` installation both exited **0**.

## Actual regression-first failures

Commands below ran from `services/api` using that launcher/venv, not live settings.

1. `python -m pytest tests/test_telegram_delivery_worker.py -q`, exit **1**:
   **15 failed in 4.81s**. Fresh profile API failed before consent selection:
   `AttributeError: 'str' object has no attribute 'value'` at profile serialization.
   The constructor supplied a string rather than `EmploymentStage.prejoin`.
2. After correcting only that enum construction, same command, exit **1**:
   **14 failed, 1 passed in 4.38s**. Actual failing assertions included:
   - Revocation: `assert providers.requests == []` failed; queued Telegram sent.
   - HTTP 200 `ok=false`: `assert alert.status != AlertStatus.sent` failed:
     `AssertionError: assert <AlertStatus.sent: 'sent'> != <AlertStatus.sent: 'sent'>`.
   - Malformed JSON: the send timestamp was already set before JSON validation:
     `assert alert.sent_at is None and alert.provider_message_id is None` failed.
   - HTTPX INFO request logs contained the synthetic bot credential URL. Evidence
     excerpt, redacted: `HTTP Request: POST https://api.telegram.org/bot[REDACTED]/sendMessage`.
   - Read timeout: expected terminal `failed`, observed retryable `pending`.
   - Interrupted dispatch: independent observer expected a durable failed claim,
     observed `pending` while transport was paused.
3. Refined the concurrency barrier so a second request releases both workers.
   `python -m pytest tests/test_telegram_delivery_worker.py::test_two_independent_worker_sessions_cannot_double_dispatch -q`,
   exit **1**, **1 failed in 0.75s**: second worker returned `processed=2`, expected
   `0`; the baseline allowed two dispatchers into the same provider operation.

Only then were delivery/configuration corrections applied. An initial focused run
passed **17 tests in 2.58s**, followed by **30 in 4.00s** as coverage expanded.
An early Ruff run found four E501 lines (exit 1); those were formatted and fixed.
One format invocation used repository-root rather than API-relative paths and
failed without edits; the corrected invocation succeeded. One exploratory full
run was deliberately interrupted to avoid overlapping DB test processes:
**124 passed**, exit **2** (KeyboardInterrupt), not acceptance evidence. Subsequent
full runs were sequential. The first completed full run passed **296 tests in
98.01s**, exit **0**, with the existing feedparser deprecation warning.

## Connected results and exact transport boundaries

The tests create a real owner through `/v1/profile`, opt in through its PATCH API,
fetch deterministic official-source HTML through the real SSRF-defended fetcher,
then use real ingestion, eligibility, scoring, evidence, revisions, alert service,
PostgreSQL queue and worker. No score, eligibility, revision or alert is forced by
SQL. The existing clearly synthetic fellowship fixture naturally scores **94**,
with `verified_yes` professional/India eligibility and high source credibility.
Assessment evidence references the official fixture URL and the material revision.

Only source GET `https://93.184.216.34/fellowship` and synthetic Telegram POST
`https://api.telegram.org/bot[SYNTHETIC]/sendMessage` are permitted at HTTP transport.
Synchronous HTTP/SMTP are forbidden. Unexpected destinations and boundary-assertion
failures are remembered and fail fixture teardown even if application exception
handling catches them. No real Telegram DNS/connection occurs.

- Fresh defaults are `['in_app']`; merely configuring Telegram creates/sends only
  one in-app alert, zero Telegram requests. Explicit API opt-in creates exactly
  one alert per selected channel for one opportunity/material revision.
- Payload uses only the configured synthetic numeric chat ID. Hostile source text
  and an alert payload containing `chat_id`/`token` cannot change routing. Public
  details, official link and `2099-12-15 (date_only)` appear without a made-up time;
  credentials/CV/private configuration do not. Profile/inbox API responses and
  captured INFO/DEBUG logs contain neither the synthetic token nor chat ID.
- Valid acknowledged response stores `sent`, message ID `16001`, the frozen send
  timestamp, original dedup key and opportunity/revision links. Unchanged ingestion
  retains one opportunity, one material revision and two channel alerts; repeat
  delivery makes no additional request.
- Opt-out before delivery leaves Telegram `suppressed`, no sent timestamp, zero
  requests, and a retained/sent in-app alert available through `/v1/alerts`.
  Re-opt-in plus another worker execution cannot revive that suppressed row.
- Unknown India and verified professional exclusion (student-only) yield no
  immediate external alert, including an urgent **2026-11-17** date-only deadline
  during quiet hours. Canonical ingestion still succeeds.
- At **2026-11-13 22:30 IST / 17:00Z**, alerts schedule for
  **2026-11-14 08:00 IST / 02:30Z**. Night worker: zero requests, pending row.
  Morning worker: exactly one request and `sent_at=2026-11-14T02:30:00Z`.
  Repeat: no new request. Overdue daytime alerts are also rechecked/rescheduled
  at night. Explicit equal quiet-hour bounds permit one send at 22:30 IST.
- Two independent worker transactions synchronize inside transport: first owns
  the durable claim, second processes zero alerts, final request count **1**, ID
  `16001` preserved. Cancellation while inside transport leaves an independently
  visible terminal failed claim; rerunning queued delivery does not resend.
- A separate regression holds a request in flight while API opt-out waits on the
  profile lock: the current send completes before revocation commits, then further
  worker execution cannot resend. This is ordering, not recall of an in-flight
  Telegram message.

## Provider outcomes and limits

Each error case issues one simulated request; none fabricates a message ID or
sent timestamp. Retry counts and sanitized reasons persist. HTTP 200 `ok=false`
and pre-connection failure return to `pending` until four attempts; the bounded
rejection regression makes **4** requests, then a fifth worker makes none.
Malformed JSON, absent/null/boolean message IDs, wrong-chat acknowledgement,
HTTP 500 and read timeout remain terminal `failed` for manual review. HTTP 401/403
require configuration review; HTTP 429 requires provider-backoff/manual review,
not an immediate automatic retry. Repeated workers cannot retransmit these
terminal outcomes. Missing token/chat, nonnumeric/zero/oversized chat ID send
nothing, keep Telegram pending with retry count zero, and preserve in-app delivery.

The dedicated focused run records **22 simulated Telegram requests across 29
Telegram cases**, plus **2 unchanged SMTP tests**. Captured teardown summaries
contain only scenario names, counts and frozen clocks. They contain no real
provider data. Unchanged SMTP tests simulate their transport; Telegram opt-in is
not required for SMTP, nor is SMTP configuration required for Telegram/in-app.

A durable `failed` claim is committed before provider I/O. A crash before I/O can
therefore require manual review even when nothing was sent; a lost result commit
can leave an acknowledged provider send unconfirmed. Prefer avoiding duplicate
sends over automatic replay. This is **not exactly-once delivery**. Follow the
runbook's separate authorization and reconciliation procedure; do not reset
ambiguous/suppressed rows automatically. Live `/start`, live provider acceptance,
manual reconciliation UX and broader SMTP ambiguity handling remain outside this
bounded task. M5 is **PARTIAL**, not production-ready acceptance.

## Final local checks, CI and cleanup

Final command results, final-head CI links and cleanup proof are recorded below
and in the PR. A complete platform session-export capability was not exposed;
this sanitized execution record and the executable regressions are provided
instead. No private platform transcript or unrelated environment was exported.

- `python -m pytest tests/test_telegram_delivery_worker.py tests/test_alerts_smtp.py -q -s`:
  **31 passed in 4.47s**, exit **0** (29 Telegram cases, 22 intercepted Telegram
  requests; 2 unchanged SMTP regressions). This final focused rerun also verifies
  the strengthened terminal-status and transport-assertion safeguards.
- `python -m pytest tests -q`: **297 passed, 1 warning in 96.56s**, exit **0**.
  Includes ingestion, eligibility/time, revisions, queue, workers and all other
  backend tests. The warning is the existing feedparser deprecation above.
- `python -m ruff check app tests scripts`: **All checks passed!**, exit **0**.
- `python -m mypy app scripts`: **Success: no issues found in 61 source files**,
  exit **0**.
- `git diff --check`: exit **0**.
- Cleanup: reverified the exact container ID and both `discmon.task=16` labels,
  stopped/removed only `discmon-task16-pg`, removed only `discmon-task16-pgdata`;
  task-label container and volume inventories are empty afterward. No production
  resources or existing checkout contents were removed. The isolated feature
  worktree remains available for review; its virtualenv is ignored.

### Exact changed files

- `services/api/app/services/alerts.py`
- `services/api/app/services/assessment.py`
- `services/api/app/config.py`
- `services/api/tests/test_telegram_delivery_worker.py`
- `docs/PROGRESS.md`
- `docs/changelog.md`
- `docs/operations-runbook.md`
- `docs/evidence/task16-telegram-offline.md`

GitHub Actions backend, web and Compose results must pass on the final PR head
before acceptance; those external run URLs and mergeability are recorded in the
PR/final review handoff rather than inserting a self-referential commit into this
file. Do not merge, enable auto-merge, deploy, or begin another milestone.
