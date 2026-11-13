# Task 17B engineering review

## Git baseline and delivery

- Original workspace checkpoint: `2c31234` (older ancestor, initially clean).
- Accepted checkpoint: `8c54d70fd75048cd23e8f3f3379148189859d090`.
- Recovered exact Task 17: `bdc653fe6a6a9bae0717db9908c24b930a89046a`;
  its direct parent is the accepted checkpoint. Verified both through Git.
- Remote `handoff/stabilize-idfc-audit-20261112` still points to the accepted
  checkpoint. It was not changed. No Task 17 rebuild/cherry-pick approximation.
- Isolated working branch: `task17b/editable-runtime-schedule`.
- Final implementation is the commit containing this report; obtain its full
  identifier with `git rev-parse task17b/editable-runtime-schedule`. The delivery
  reply records the resulting commit reference. No merge, push or deployment.

## Architecture and UI

PostgreSQL remains authoritative for the requested revision and saved window.
An additive singleton-table migration initializes 09:00–21:00 Asia/Kolkata,
without falsely recording a host ACK. Row locking plus optimistic revisions
prevents lost concurrent saves and stale ACK/error attribution. DB constraints
also enforce the same-day, fixed-timezone, minimum-duration and backup policy.

The host pulls the fixed loopback endpoint using a separate, scope-limited
credential, validates the response, installs a private snapshot atomically and
then acknowledges the exact version. A save is pending until acknowledged;
old confirmations become stale after three minutes. Applied means durably
installed configuration, not a claim of container health. Host failures are
reported using two fixed error categories; HTTP/CLI bodies and secrets are not
logged. No timer files are generated from user input.

When the API/database is down, the protected last verified snapshot determines
startup. A successful start is followed by another pull to catch a previously
unreachable update. Missing/corrupt/insecure snapshots with no authenticated
refresh refuse container operations. Stale valid snapshots remain usable with
visible warnings, avoiding a circular dependency on a stopped database.

Settings has native time inputs, live draft duration, saved and host-installed
revisions/times, pending/applied/stale/error states, refresh, conflict handling,
validation and load/save failure messages. Profile/quiet hours remain separate.
A schedule-load failure does not remove the preferences form. The page explains
power/awake requirements and inaccessibility while services are stopped.

## Backup policy and preserved behavior

Existing live backup units are unchanged and no second backup job is added.
Supported windows start at/before 20:00 and stop at/after 21:00 so the existing
20:30 backup retains lead time. Earlier shutdown examples 08:00–20:00 and
10:00–18:00 are deliberately rejected, not cosmetically accepted. The runbook
documents the owner-approved transition needed before relaxing those gates.
A slow active backup delays shutdown; runtime control never interrupts it.

A finished failed oneshot stays failed and logs a warning without permanently
blocking application operations. Completion requires known substate and zero
main/control process IDs; active/missing/unknown states still block. The shared
backup/runtime lock, container/project/file/volume checks, smoke isolation,
restart-policy control, graceful ordered stop, current-time boot/resume
reconciliation and idempotent nondestructive operations are preserved.

## Security analysis

- Owner routes use existing owner authentication; disabled auth is accepted only
  for development/test, not staging/production. Dedicated host tokens cannot
  act as owner credentials, even under local disabled owner auth.
- Host endpoints are disabled without a configured token and always require it.
  Tokens are URL-safe, 32–256 characters, and distinct from owner credentials.
  Configuration-validation exceptions hide input values. Web gets no host token.
- Only the API receives the new environment variable; Compose adds no socket,
  systemd or host-state mounts. Host requests cannot redirect or use proxies.
- State directory is owner-only 0700. Reads reject symlinks, hardlinks, wrong
  ownership/modes, non-regular or oversized files. Snapshot writes use 0600,
  fsync, same-directory atomic replacement and directory fsync.
- Times are strict data, never commands, paths, cron expressions or unit text.
  Fixed endpoint paths, bounded reads and sanitized errors limit injection and
  accidental disclosure. Local root/the existing Docker-owning user remain
  trusted; this is not a sandbox against a compromised privileged host user.

## Changed files (relative to Task 17)

Frontend:
- `apps/web/app/settings/page.tsx`
- `apps/web/components/RuntimeScheduleSection.tsx`
- `apps/web/app/globals.css`
- `apps/web/lib/actions.ts`
- `apps/web/lib/api.ts`
- `apps/web/lib/types.ts`
- `apps/web/tests/e2e/runtime-schedule.spec.ts`

Backend/configuration:
- `services/api/app/api/runtime_schedule.py`
- `services/api/app/api/deps.py`
- `services/api/app/config.py`
- `services/api/app/main.py`
- `services/api/app/db/models/runtime_schedule.py`
- `services/api/app/db/models/__init__.py`
- `services/api/alembic/versions/e5b8f19c2a70_runtime_schedule.py`
- `services/api/tests/test_runtime_schedule_api.py`
- `docker-compose.yml`
- `.env.example`

Host:
- `scripts/runtime_schedule.py`
- `scripts/tests/test_runtime_schedule.py`
- `scripts/tests/test_runtime_schedule_config.py`
- `deploy/systemd/discmon-runtime.service`
- `deploy/systemd/discmon-runtime.timer`

Documentation:
- `docs/runtime-schedule.md`
- `docs/deployment.md`
- `docs/operations-runbook.md`
- `docs/PROGRESS.md`
- `docs/changelog.md`
- `docs/evidence/task17b-runtime-validation.txt`
- `docs/task17b-review.md`

## Verification and remaining boundaries

Actual command output/exit codes are retained in the evidence file, not inferred.
Final results: 304 backend tests, 79 script tests, 2 production-browser tests;
Ruff, focused mypy, frontend lint/typecheck/build, Python compilation, Bash
syntax, systemd unit/calendar validation and diff checks pass. Fresh isolated
PostgreSQL migration upgrade/downgrade/upgrade passes. Authenticated real local
API snapshot/ACK plus browser applied, error, missing-settings and pending
assertions pass. Screenshots were inspected in dark mode at 1440px and 360px.
The one backend warning is an existing feedparser deprecation.

The development preview did not hydrate the editor reliably. No test assertion
was weakened: managed Preview was switched to the actual production build,
where both viewport save/reload flows and browser status/error assertions pass.
The initial missing Playwright browser was installed. An overlapping manual
verification correctly hit a revision conflict and passed when run sequentially.
These recovered failures are recorded rather than called successful runs.

No actual laptop boot/resume, production PostgreSQL18, Docker operation, active
live backup, target systemd service execution or deployment is verified by these
cloud checks. PostgreSQL16 and synthetic data were used in isolated databases;
Docker/systemd lifecycle tests are mocked. Actual boot/resume and safe adoption
must be owner-verified before enabling scheduling. Runtime gracefulness cannot
protect against physical power loss or unrelated privileged administrators.

## Owner installation and rollback

See `runtime-schedule.md` for approval-gated application/migration deployment,
private token provisioning, exact unit installation, first online bootstrap,
identity/backup checks, verification and nondestructive rollback. Do not enable
the timer before bootstrap/adoption succeeds. Changes later require only saving
in Settings and checking the host-confirmed revision, not editing timer files.
Rollback disables the runtime timer, waits for work to finish, removes only its
units, preserves data/backups and normally leaves the additive table in place.

**The live laptop deployment and database were untouched.** No live migrations,
Docker starts/stops, systemd installation/enablement, source ingestion, backup
deletion, destructive cleanup, force push, merge or production deployment ran.
