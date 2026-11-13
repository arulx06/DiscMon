# Operations runbook

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
seeding or any other runtime mutation. M0 remains **PARTIAL**; preflight is not
acceptance evidence.

A clean-volume drill is future work and requires separate explicit
authorization plus a pinned commit checked out fresh in a disposable worktree
with no production `.env`, secrets or credentials available. Use a disposable
project, network and volume and a test-only override that removes secrets
mounts and routes PostgreSQL to isolated test-only database/user/credentials.
Bind only on confirmed nonconflicting localhost ports.

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
Default/all-profile model contains only postgres/API/web on an internal bridge,
with no secret binds and no production port mappings. Credentials are public
test-only values. Do not use the production preflight's `--check-host` as proof
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
   independently. Verify effective localhost exposure and internal-bridge
   routing; static config does not establish this runtime behavior.
5. Record a post-drill inventory and compare it to the baseline. Before cleanup,
   positively match each created ID to the run's creation record, project labels
   and expected service/resource name. Refuse ambiguous ownership. Remove only
   those specific IDs; never blanket-prune, remove by prefix alone, or use
   `docker compose down -v`. Verify baseline resources are unchanged and all
   owned runtime resources are gone; record any leftover images explicitly.

No services, databases or volumes were accessed or changed in Task 3. A future
race between inventory and resource creation remains possible: refuse conflicts
rather than adopting resources. Static validation cannot prove freshness,
resource ownership, port availability or runtime health. **M0 remains PARTIAL**
until the separately authorized drill provides that evidence.

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

- Telegram missing: alerts remain in the in-app inbox with `pending` status.
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
