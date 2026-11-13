# Operations runbook

## Current acceptance status (2026-11-13)

M0 is **ACCEPTED** from Retry 5's independent review of the isolated cloud
drill at base `2f510c1d82532e1b87acec9082f2c56e073ec07e` (PR #4 merged): 38 Compose tests
passed; fresh isolated PostgreSQL 18.7, API and web started; actual database
identity was verified before one Alembic upgrade to `d4a7c1e9f210`; all 19
tables were present with no seeded application records; API live/ready and the
`Radar overview` dashboard returned HTTP 200; ownership-safe cleanup succeeded;
Git was unchanged and the final exit was 0. See [Retry 5 evidence](https://api.hoplite.sh/api/attachments/ceb6a69a074e494ca9c94ef85a6eb650?media=file)
and [Retry 5 original command transcript](https://api.hoplite.sh/api/attachments/340fa8f8f5e847c3bc51dd29e2fc73d7?media=file).
This is not production deployment or proof of full outbound isolation. M5 is
still **PARTIAL**. The local fixture-backed connected-flow tests and full
backend suite passed; CI and live Sheets acceptance are not claimed. Commands
and isolated test database details are recorded in `PROGRESS.md`.

## Compose preflight and isolated drill boundary

Run the static Compose preflight from the repository root before considering a
runtime test:

```bash
python3 scripts/compose_preflight.py --project discmon-preflight-20261112-a17c
```

Use a unique lowercase suffix. The script requires Python 3.12+ (standard
library only) and Docker Compose v2/v5. It renders the base and
base-plus-`docker-compose.dev.yml` configurations with `--env-file /dev/null`,
`config --no-env-resolution` and a sanitized environment. It emits redacted
service, volume, port, profile and routing details; it accepts no arbitrary
config/env/override and does not read `.env` or secrets.

It refuses non-empty inherited `COMPOSE_FILE`, `COMPOSE_PROJECT_NAME`,
`COMPOSE_ENV_FILES`, `COMPOSE_PROFILES`, `DOCKER_HOST` or `DOCKER_CONTEXT`.
Deliberately unset them only for a local static invocation when needed; do
not unset them to redirect a host check. `--check-host` uses the local Docker
socket/default local context only, never a remote daemon.
Default static mode does not query Docker or mutate runtime resources. It
reports scoped volumes but cannot establish freshness or port availability.
Optional `--check-host` requires Docker and performs read-only container,
volume and network list queries plus local socket bind probes.

The current host ports are fixed at `3000`, `8000`, `55432`, and `5000` with
the changedetection profile, so a unique project name alone does not prevent
port conflicts. Neither preflight mode authorizes deployment, migration,
seeding or any other runtime mutation. Preflight itself is not acceptance
evidence; the isolated M0 acceptance is recorded above.

The accepted clean-volume drill used a pinned commit checked out fresh in a
disposable worktree with no production `.env`, secrets or credentials available.
A future repeat still requires separate explicit authorization. Use a disposable
project, private/ingress networks and volume and a test-only override that removes
secrets mounts and routes PostgreSQL to isolated test-only database/user/credentials.
Bind only API/web on confirmed nonconflicting localhost ports; PostgreSQL
remains internal at `postgres:5432`. The obsolete `--db-port` option is rejected.

Wait for PostgreSQL 18 readiness. If a migration is separately authorized,
check the API directly at `http://127.0.0.1:<api-port>/health/live` and
`http://127.0.0.1:<api-port>/health/ready`; independently check availability
of the web root at `http://127.0.0.1:<web-port>/`. Do not treat these as
web-proxied API health checks. Import disabled sources only with separate
authorization. Workers and scheduler must never start in Task 2.

Capture container, network and volume inventories before and after and verify
pre-existing resources remain unchanged. Clean up only exact container, network
and volume IDs created by this drill, then verify baseline resources remain;
never use `docker compose down -v`.

The Compose plugin must be available without per-user Docker configuration
(for example, a system-installed plugin). The script deliberately uses an empty
Docker config directory; a plugin installed only under `~/.docker/cli-plugins`
is not supported. It checks the required JSON and `--no-env-resolution`
capabilities and suppresses CLI diagnostics that might contain secrets. Host
checks also inspect published Docker TCP ports, including NAT-only mappings,
not just socket listeners.

## Task 3 smoke boundary and future ownership-safe procedure

For the new static model, use a fresh project identity:

```bash
python3 scripts/compose_smoke.py --project discmon-smoke-20261113-a17c
```

See
[deployment](deployment.md#isolated-smoke-configuration-task-3) for ports and
options. This fixed base+smoke render does not query the daemon, read private
config, start containers, build, migrate, seed, scan or send notifications.
Default/all-profile model contains only postgres/API/web. PostgreSQL attaches
only to the scoped internal `private` bridge and has no host port; API/web also
attach to a scoped ordinary `ingress` bridge for their loopback publications.
There are no secret binds or production port mappings. Ingress may allow
API/web outbound traffic: do not claim complete egress isolation. Credentials are
public test-only values. Do not use the production preflight's `--check-host` as proof
of smoke-port availability; it checks the production configuration's ports.

**Separate explicit owner authorization is required before every runtime drill.**
The proposed procedure, not executed in Task 3, is:

1. Pin the reviewed commit in a new clean worktree without private files. Choose
   a never-used project suffix, run the static validator, and retain its redacted
   report plus exact sanitized invocation. Do not reuse this document's examples.
2. Before creating anything, inventory existing container/network/volume IDs,
   names, Compose project/service labels and published ports read-only. Refuse
   if any resource has the proposed project label or expected name/prefix. Check
   chosen loopback ports with both socket probes and Docker published-port
   metadata. No inventory or host check is performed by Task 3's validator.
3. With authorization, create/build/start **only** the validated postgres, api
   and web model using the same project/files/empty-env/sanitized environment.
   Record created IDs immediately; verify names and Compose project/service
   labels against the inventory. A matching name alone never proves ownership.
4. Wait for isolated PostgreSQL readiness. Migrate only this independently
   verified isolated target if explicitly authorized; source import/seed,
   ingestion, worker/scheduler startup, scans and notifications remain forbidden
   unless separately authorized. Check API live/ready directly and web root
   independently. Verify actual API/web loopback publication through ingress,
   PostgreSQL private-only membership/no host ports, and internal service routing;
   static config does not establish this runtime behavior.
5. Record a post-drill inventory and compare it to the baseline. Before cleanup,
   positively match each created container and both network IDs to the run's
   creation record, project labels and expected service/resource name. Refuse ambiguous ownership. Remove only
   those specific IDs; never blanket-prune, remove by prefix alone, or use
   `docker compose down -v`. Verify baseline resources are unchanged and all
   owned runtime resources are gone; record any leftover images explicitly.

Task 3 itself accessed or changed no services, databases or volumes; its
static validation did not establish runtime acceptance. The later isolated M0
drill is recorded above. For any future repeat, a race between inventory and
resource creation remains possible: refuse conflicts rather than adopting
resources. Static validation still cannot prove freshness, ownership, port
availability or runtime health.

## Network correction boundary (static only)

Retry 1's original logs show a healthy PostgreSQL 18.7 container with configured
loopback port bindings but no actual published mapping. API, SQL proof, migration
and web were not attempted. This is observed incompatibility under that topology,
not conclusive proof of an Engine defect. See the session's original Retry 1
transcript and cleanup inventory; do not replace those logs with new test output.

The revised design removes PostgreSQL host publication and separates ingress.
Static rendering alone does not establish runtime acceptance. Before a later,
separately authorized drill, recheck both network identities and attachments:
PostgreSQL on private only; API/web on private and ingress; no aliases, extra
networks or external resources. Prove the actual API database target and PostgreSQL
server identity before any authorized migration. Check Alembic revision separately
from `/health/ready` (which only runs `SELECT 1`). Never seed or ingest.

## Daily

- Open Overview: check pipeline health, source failures and attention list.
- Act only on verified, high-confidence items.
- Review in-app alerts; Telegram/SMTP delivery is optional.

## Weekly

- Read the weekly digest (Sunday 19:00 IST by default).
- Review unresolved eligibility items.
- Inspect stale/failing sources and dead jobs.
- Add or reject discovery candidates deliberately.

## Debug a source

1. Sources -> source detail -> recent runs.
2. Check `last_error_category`, redacted message, HTTP status and scan
   completeness.
3. Use **Preview** to fetch/parse without changing canonical records.
4. If the source changed shape, update the approved adapter config or disable
   it. Do not lower safety rules to "fix" parsing.

## Discovery

1. Open `/discover` and inspect candidate origin, URL, evidence and status.
2. Reject candidates that are aggregators, off-topic or legally unsuitable.
3. Approve deliberately, then promote an approved candidate to create a
   disabled source.
4. Review the new source's terms, adapter, URL and discovery config before
   enabling it. Promotion does not imply legal approval or enable scanning.
5. On a discovery-enabled source page, use **Scan for links** to run a bounded
   extraction. A scan failure is visible and must not be treated as zero links.

### Discovery scheduling (weekly default, monthly opt-in)

Existing `config_json.discovery.enabled=true` sources keep the weekly Monday
09:00 IST window when `cadence` is omitted (or explicitly `"weekly"`). Weekly
keys remain `discover:weekly:<source-id>:<ISO-year>-W<ISO-week>`.

For a deliberately approved directory or newsletter, opt in through the existing
source configuration, for example:

```json
{
  "discovery": {
    "enabled": true,
    "cadence": "monthly",
    "allowed_domains": ["example.org"],
    "max_candidates": 25
  }
}
```

Monthly eligibility begins at **09:00 Asia/Kolkata on day 1**. The first eligible
tick enqueues the current month; a later tick catches up if the scheduler was
down, including before 09:00 on later days. There is no historical backfill.
The persisted key is `discover:monthly:<source-id>:<IST-year>-<two-digit-month>`;
restarts, UTC midnight and completed jobs do not permit another scheduled job
for that same month. Keep queue idempotency records: deleting them removes that
protection. Active queued/running/retry-wait discovery suppresses overlapping
work for its source; other sources remain eligible. Monthly sources do not also
receive weekly discovery jobs.

Both cadences require enabled, owner-approved, legally approved sources.
Unsupported cadence strings, nulls and non-string values fail closed for
scheduled discovery. `schedule_once()` returns `invalid_discovery_cadences` (a
count only, no raw configuration); nonzero counts are also included in the
scheduler tick log. Fix the source config rather than broadening collection.
Ordinary approved-source monitoring, alerts and digests retain their schedules.
A manually requested **Scan for links** remains a separate, explicit operation,
not a second scheduled monthly job.

The existing worker only proposes canonicalized, allowlisted candidates.
Discovery does not approve linked domains or ingest opportunities. Candidates
start unapproved/legally pending; explicit owner approval is required before
promotion, and a newly promoted source stays disabled/legally pending until
separately reviewed. Task 15 verifies synthetic HTTP/DNS fixtures only: no live
newsletter, search provider, AI discovery, outbound delivery or production
operation is validated, and **M5 remains PARTIAL**.

## Integration status

`/health` shows changedetection, Telegram, Email, Sheets and optional AI as
enabled or off. Off means unconfigured, not healthy. Check the card detail
before assuming delivery occurred:

- changedetection: base URL and webhook secret.
- Telegram: bot token and allowed chat ID.
- Email: SMTP host/credentials; TLS port 587.
- Sheets: spreadsheet ID, service-account file and tab.
- AI: no provider in rules-only mode.

## Changedetection signal

- The webhook accepts a valid HMAC and a timestamp within five minutes, limits
  body size and deduplicates the body hash.
- A signal only enqueues a bounded re-fetch from the approved source adapter.
- Never point changedetection at an unapproved or internal URL.
- Invalid signatures and stale timestamps are rejected; no canonical record is
  changed by the signal alone.

## Sheets mirror failure

- PostgreSQL remains authoritative.
- `sync_outbox` retries failures; ingestion and the UI must continue.
- Check `/health` for the last error and outbox counts.
- Fix credentials or sharing, then let the worker retry. Do not edit the sheet
  as a substitute for the database.

## Stuck or dead jobs

- Health -> Jobs shows queued/running/dead.
- Expired leases are recovered automatically.
- Retry safe dead jobs from the UI/API. Poison jobs remain visible.

## Backup

```bash
bash scripts/backup.sh
```

Creates `backups/discmon-YYYYmmddTHHMMSSZ.dump.gz`.

## Restore drill

```bash
# Creates discmon_restore and verifies core counts/decisions
bash scripts/restore.sh backups/discmon-....dump.gz discmon_restore
```

Never restore over the live database. Record the drill in the changelog.

## Notification failure

- Telegram is **owner opt-in**: select `telegram` in the profile only after separately
  initiating `/start` with the real bot and configuring its trusted numeric chat ID
  server-side. Configuring credentials alone does not authorize delivery. Task 16
  used synthetic transports only; it did not verify `/start`, Telegram acceptance
  or actual SMTP delivery.
- Telegram missing/invalid configuration: alerts remain `pending`; ingestion and
  the independent in-app alert remain available. The destination is configuration,
  never source content or alert payload data.
- Removing Telegram before dispatch suppresses queued Telegram alerts without
  deleting them. Re-enabling the channel does not revive suppressed rows. Dispatch
  locks the profile while transmitting: an already-in-flight send completes before
  a concurrent opt-out commits; opt-out cannot recall a transmitted message.
- Delivery uses per-alert PostgreSQL row locks. Before Telegram I/O, it commits a
  terminal `failed` claim with an unconfirmed/manual-review reason. The delivery
  service owns this transaction boundary; use a dedicated delivery session as the
  worker does, never a session with unrelated ingestion or owner edits.
- Only an HTTP 200 response with `ok=true`, a positive integer message ID and the
  configured chat acknowledgement becomes `sent`. Rejected (`ok=false`) requests
  and failures known to occur before connection may retry, at most four attempts.
  HTTP 401/403 and 429 stop for configuration/backoff review; automatic jobs must
  not hammer a rate-limited bot. Repair configuration or respect provider backoff
  before considering an explicitly authorized manual retry.
- Timeout after connection, malformed/invalid acknowledgement, server error or
  interruption leaves a terminal `failed` alert with **unconfirmed outcome**.
  Never bulk-reset these to `pending` or replay them by retrying a worker job.
  Inspect the owner-visible Telegram history through separately authorized access
  and correlate the public opportunity/revision details. If delivery is confirmed,
  record that evidence; if unresolved, retain `failed` for manual review. Only a
  separately authorized, explicitly reconciled retry may risk another send. A
  lost database commit can also leave a valid send unconfirmed; Telegram does not
  guarantee application-level exactly-once delivery. A crash before the request
  can conservatively require review even though nothing was sent.
- Default quiet hours are 22:00–08:00 Asia/Kolkata and are rechecked at dispatch,
  including overdue work. Equal start/end hours explicitly disable quiet hours.
- Notification integration remains **M5 PARTIAL**, not production/live acceptance.
- SMTP failure: retry with redacted errors; no duplicate dedup key.
- Sheets failure: `sync_outbox` retries; ingestion and UI are unaffected.

## Rescans and assessment history

A successful rescan appends an assessment row and does not create a duplicate
opportunity. Monitor `assessments` growth; retention or deduplication is still
an open decision. Material revisions alone may alert, once per channel, using
`opportunity_id + revision_id + channel + alert_kind`.

## Source failure vs closure

A network/HTTP failure never closes records. Only a complete successful board
scan increments absence counters. Three consecutive complete absences produce a
closure candidate; confirmation or a fourth absence produces confirmed closure.

## Incident: suspected secret exposure

Revoke the token at the provider, rotate `.env`, restart services, inspect audit
events and logs for redacted-only entries, then document the incident.

## Ubuntu daily operating window (Task 17)

See [09:00–21:00 Asia/Kolkata runtime scheduling](runtime-schedule.md) for
review-only controller/units, backup locking, owner-approved installation,
verification and rollback. No live deployment or schedule enablement is claimed.
Do not use ordinary Compose up/recreate while this schedule is enabled: it can
restore automatic restart policies and bypass the overnight guard.
