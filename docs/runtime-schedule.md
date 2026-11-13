# Editable Ubuntu daily runtime — Tasks 17 / 17B

**Review-only: no laptop deployment, migration, unit installation or enablement
was performed.** Task 17B extends the exact Task 17 controller, not a second
scheduler. Target remains the owner's Ubuntu checkout, user `arulxamv`, rootful
local Docker socket, project `discmon`, base `docker-compose.yml`, exactly the
existing postgres/api/worker/scheduler/web containers and `discmon_pgdata`.
Moved checkouts, overlays, profiles, rootless/remote Docker or different labels
require review; never bypass identity verification.

## Task 17C shutdown correction — review only

The scheduler's pre-existing SIGTERM handler assigned a local loop flag instead
of the module flag, so it continued indefinitely even when idle. Task 17C fixes
that scope and wakes its idle wait without cancelling the active scheduling
transaction. Isolated process and Docker unlimited-stop evidence is recorded in
`docs/task17c-review.md` and `docs/evidence/task17c-*.txt`; no laptop deployment or
live Ubuntu verification was performed.

**Do not activate this controller based on the scheduler correction alone.**
The worker has the same separate nested-handler scope defect and still needs a
reviewed fix with active-job signal tests. It can block the stop sequence before
API/PostgreSQL shutdown. Scheduler-only owner-approved Ubuntu retesting is
reasonable after review, but full controller activation remains blocked. Never
work around either failure with SIGKILL, a finite forced-stop deadline, or backup
policy changes. A genuine unresolved database wait must still be investigated;
the correction does not impose a cancellation or database timeout.

## Settings and authority

`/settings` has an Application Runtime Schedule section, separate from alert
quiet hours. Start/shutdown use strict 24-hour minute precision and the fixed
`Asia/Kolkata` timezone. Duration updates while editing. The initial saved
window is **09:00–21:00**. PostgreSQL's singleton `runtime_schedule` row is the
authority; migration `e5b8f19c2a70` creates it without touching opportunities.
Owner-authenticated saves require the displayed revision. Concurrent saves
serialize on the row and stale revisions return 409, not last-writer-wins.

A save means **pending**, not applied. The page shows saved and host-installed
revisions/times separately, last confirmation, validation errors, sync errors
and a refresh button. Missing host confirmation stays pending; confirmation
older than three minutes is stale. A host error is visible, not success. While
the app is stopped, this page and its API are inaccessible. The laptop must be
powered on and awake; this does not power on or wake hardware.

### Narrow host synchronization

One systemd oneshot runs the existing controller every minute and after boot.
It pulls only `http://127.0.0.1:8000/runtime-sync/schedule`, using a dedicated
`RUNTIME_SYNC_TOKEN`, never the owner credential. Host endpoints are always
authenticated even when development owner auth is disabled; an absent token
disables them. The token permits only schedule reads, matching-revision ACKs
and enumerated error reports. It cannot change requested times or access other
owner API routes when owner authentication is enabled.

The host installs the validated response in
`/var/lib/discmon-runtime/schedule.json`, then POSTs `/runtime-sync/ack` with the
exact revision/times/timezone. Installation uses a same-directory temporary
file, fsync, atomic replace, directory fsync and mode 0600. The state directory
is owned by the controller user, mode 0700; files must be regular, single-link,
owned by that user, mode 0400/0600 and not symlinks. `sync.token` lives in the
same private directory. Snapshot contents are only schema version, schedule
revision/times/fixed timezone and last authenticated refresh time: no secrets.

**Applied means the host durably installed the schedule, not proof that all
containers are currently healthy.** The host reports snapshot-write/runtime
operation errors where the API is reachable; otherwise the journal reports
them immediately and the heartbeat becomes stale. ACKs require a matching
current revision under the same DB lock as saves. An update during a pull/ACK
remains pending and is picked up on a later tick; it cannot be falsely ACKed.
A save just before shutdown may take up to the next available reconciliation
to install. If the API stops first, the old snapshot remains operational until
startup. Always check host confirmation before relying on changed hours.

When PostgreSQL/API is stopped or unreachable, the controller uses the last
verified protected snapshot, logs failed sync and warns when the snapshot is
stale. It can start PostgreSQL from that snapshot without a DB query. After
starting services, it pulls again and reconciles immediately if settings
changed. Missing, corrupt or insecure snapshots with no successful online
refresh cause **no container operations**: there is no default-hours fallback
in the production command. Bootstrap therefore requires the API to be running.
The token file and state directory must be provisioned before first adoption.
A stale but valid snapshot is deliberately retained for offline recovery; it
is not silently called fresh.

No container gets a Docker socket, systemd interface or host state mount.
HTTP targets are fixed loopback endpoints; redirects and proxies are disabled,
responses/files are size-bounded, errors suppress bodies and credentials, and
times are never interpolated into shell commands, paths, cron or unit files.
No timer rewrite or extra daemon is needed for schedule changes. The host user
already has Docker-group authority; do not expose this token remotely. Local
root/the Docker-owning user can change runtime state and are trusted operators.

## Preserved runtime protections

- Only existing containers start (`compose start --wait`), never `up`, create,
  build, pull, remove, prune, migrations, seeds or ingestion. Every operation
  validates project/service/working-directory/exact Compose-file labels and the
  PostgreSQL volume mount. Smoke projects are not selected.
- Every Docker call uses the explicit local socket, sanitized environment and
  empty temporary Docker config. Restart policies become `no` before operation.
  Do not recreate containers or run another boot/cron controller while enabled;
  external `compose up` can restore `unless-stopped` and defeat overnight control.
- Shared repository `.runtime.lock` coordinates runtime and `backup.sh`; no
  lock inode replacement. Backup state is checked while holding the lock, with
  up to 25 minutes of waiting; the lock is released to let pending backup work
  acquire it. Active/unknown backup state is conservative.
- Graceful stop order is web, scheduler, worker, api, postgres, using indefinite
  Docker stop timeout, no forced kill. An earlier stop error prevents subsequent
  stops. Startup failure attempts safe shutdown. Current local time is checked
  before and after startup, including a crossed cutoff.
- Boot and resume reconcile current time; they do not replay old start/stop
  events. Persistent minute timer covers missed events. All starts/stops are
  idempotent, with identity revalidation before startup.
- Safety can delay shutdown indefinitely for a hung application or active
  backup. Do not kill the controller, remove its lock, force-stop Docker or power
  down to force the clock deadline. Physical power loss is outside the guarantee.

## Backup policy: existing 20:30 timer untouched

The existing `discmon-backup.service` remains `Type=oneshot`, with the Task 17
shared backup lock and the existing 20:30 IST timer. **No backup units, timer
drop-ins, duplicate jobs or automatic retiming are introduced.** Supported
windows require start at/before **20:00** and shutdown at/after **21:00**, start
before shutdown, at least 60 minutes, same day. Thus 08:00–21:00 is supported;
08:00–20:00 and 10:00–18:00 are explicitly rejected in UI/API/host/DB, not marked
applied. The 30-minute post-backup buffer is not a completion-time guarantee:
an active backup delays shutdown until safely finished.

A **completed failed backup** remains visibly failed in systemd and generates a
warning but no longer blocks every later start/stop. An inactive/failed state
must also have no main process and a known completed substate. No failure is
reset automatically. Active, indeterminate, missing or non-oneshot services
still prevent runtime operation. A directly invoked backup also holds the lock.
A late backup against stopped PostgreSQL fails without starting it or leaving
a final partial artifact. Sleep/power-off can miss backup coverage; check backup
health before relying on any unattended schedule.

### Owner-approved earlier-shutdown transition (not implemented or executed)

To support earlier shutdown, first obtain explicit owner approval for a separate
backup-policy change. Disable runtime reconciliation and wait for its current
job and all backup work to finish; never interrupt a backup. Under the shared
lock, retire the old timer before enabling a replacement (never overlap), retain
one `discmon-backup.service`/script and design dynamic timing with adequate lead
time, a completion gate, and coverage tracking when changes cross today's
backup time. Test the new policy in isolation, including failures, rescheduling,
sleep/resume and overdue coverage. Only after successful review/migration should
the four-layer compatibility checks be relaxed. Until then use a supported
window. Merely editing systemd timer files is not a safe implementation of this
transition. Preserve old unit copies for rollback; do not delete backups.

## Owner-side installation — approval required; NOT executed here

Do not run the following against the laptop before engineering review/approval.
The runtime scheduler has not previously been installed there. Keep backup units
unchanged. Prerequisites: Ubuntu systemd, Python 3.11+ with tzdata, util-linux
flock, current Docker Compose with `start --wait` and indefinite `stop` support,
and the existing five correctly labelled containers/volume. Confirm the host
is Asia/Kolkata for the existing unchanged local-time backup timer.

1. Review this branch/diff, verify opportunity counts and a recent successful
   backup, and retain the previous application image/revision. Finish existing
   jobs. Ensure no runtime controller or backup is active. Inspect units locally
   without publishing credentials. Never touch the production database from the
   cloud workspace.
2. In an approved maintenance window, with no controller enabled, build/deploy
   the reviewed application and apply its migration using the normal documented
   deployment workflow. This is an owner-side production change, not performed
   by this task. It creates only runtime settings. Keep the API running to
   bootstrap; do not start workers or ingest sources merely to test scheduling.
3. Provision a private state directory and a dedicated token. Run as the owner
   unless a line uses sudo. Never print the token, use it in command arguments,
   commit it, paste it into chat or include it in evidence:

   ```bash
   sudo install -d -o arulxamv -g arulxamv -m 0700 /var/lib/discmon-runtime
   cd /home/arulxamv/projects/DiscMon
   python3 - <<'PY'
   import os, secrets
   from pathlib import Path
   state = Path('/var/lib/discmon-runtime/sync.token')
   env = Path('.env')
   content = env.read_text()
   if any(line.startswith('RUNTIME_SYNC_TOKEN=') for line in content.splitlines()):
       raise SystemExit('Token setting already exists; reconcile securely, do not rotate blindly')
   token = secrets.token_urlsafe(48)
   fd = os.open(state, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
   with os.fdopen(fd, 'w') as output:
       output.write(token + '\n')
   # No secret is written to stdout; restrict the existing application env file.
   env.chmod(0o600)
   with env.open('a') as output:
       output.write('\nRUNTIME_SYNC_TOKEN=' + token + '\n')
   PY
   ```

   If the key already exists (including a blank copied from `.env.example`),
   stop and reconcile it securely with `sync.token`; do not generate competing
   tokens. A partially completed provisioning step is not installation success.
   Recreate the API with the new environment **before** controller adoption,
   using the reviewed deployment workflow. Existing Compose port binding remains
   loopback. Require owner token authentication for normal application routes.
4. Validate configuration, syntax and service files. `systemd-analyze verify`
   must run on the target Ubuntu host as well; cloud checks are offline proof
   only. Check lock ownership/type and exact project/volume labels locally:

   ```bash
   python3 -m unittest discover -s scripts/tests -p 'test_runtime_schedule*.py' -v
   bash -n scripts/backup.sh
   systemd-analyze verify deploy/systemd/discmon-runtime.service deploy/systemd/discmon-runtime.timer
   systemd-analyze calendar '*-*-* *:*:00 Asia/Kolkata'
   test "$(timedatectl show -p Timezone --value)" = Asia/Kolkata
   sudo systemctl show discmon-backup.service -p ActiveState -p SubState -p MainPID -p Result
   ```
5. Only after approval and all preflights pass, install the one runtime pair:

   ```bash
   (umask 077; touch .runtime.lock) # only after verifying existing path is safe
   sudo install -o root -g root -m 0644 deploy/systemd/discmon-runtime.service /etc/systemd/system/discmon-runtime.service
   sudo install -o root -g root -m 0644 deploy/systemd/discmon-runtime.timer /etc/systemd/system/discmon-runtime.timer
   sudo systemctl daemon-reload
   sudo systemctl start discmon-runtime.service
   # This first run changes restart policies and reconciles CURRENT saved hours.
   # Continue only after successful adoption and journal/Settings review.
   sudo systemctl enable --now discmon-runtime.timer
   ```

StateDirectory creates/maintains the private state directory for the service
user; the pre-created token is not mounted into any container. Keep live backup
units unchanged. Do not enable runtime scheduling unless the initial snapshot
is durably installed and all identity/backup checks pass.

## Verification and recovery

Inspect `/settings`: save a supported change, see pending, then refresh after
one minute for the exact host-confirmed revision. Try an unsupported earlier
shutdown and confirm rejection without changing saved/applied hours. Review
service journals without publishing raw container inspection or environment.

```bash
sudo systemctl status discmon-runtime.timer discmon-runtime.service --no-pager
sudo systemctl list-timers --all discmon-runtime.timer discmon-backup.timer
sudo journalctl -u discmon-runtime.service -u discmon-backup.service --since today --no-pager
/usr/bin/docker --host unix:///var/run/docker.sock ps -a --filter label=com.docker.compose.project=discmon --format '{{.Names}} {{.Status}}'
/usr/bin/docker --host unix:///var/run/docker.sock inspect --format '{{.Name}} {{.State.Running}} {{.HostConfig.RestartPolicy.Name}}' discmon-postgres-1 discmon-api-1 discmon-worker-1 discmon-scheduler-1 discmon-web-1
```

Expect restart policies `no`, running inside the **host-installed** window and
stopped outside it after graceful completion. A successful oneshot is normally
inactive/dead. Runtime errors suppress raw Docker/systemctl/HTTP data. Repair
the indicated condition, do not reset a backup failure merely to force an
operation. Completed backup failure does not need reset for runtime recovery.
For missing/corrupt state while DB is stopped, do not invent a snapshot: restore
a trusted snapshot copy with correct permissions, or suspend scheduling and
perform an owner-approved manual startup under the shared lock so the API can
supply authoritative settings. Check labels/backup state before any manual
operation. Never restore or migrate the DB merely to repair runtime state.

## Rollback (owner approval; never delete data)

Disable the runtime timer, wait for any currently running runtime/backup job to
finish naturally, and inspect their status. Do not forcibly stop an in-flight
service. Remove only the runtime units after they are inactive, daemon-reload,
and retain the protected snapshot/token for diagnosis. Do not delete `.runtime.lock`
while any participant may hold it. Revert application code/image as reviewed;
leave the additive settings table in place (no production downgrade is needed).
Remove the optional token setting from the app environment during a reviewed
redeploy. Leave existing backup units and every backup/container/volume intact.

If reverting to unscheduled operation, only after schedule ownership is fully
released, use explicit project-verified existing container IDs to restore the
previous restart policy and start services manually under the shared lock.
If reverting specifically to Task 17, restore its exact controller/units and
fixed 09:00–21:00 policy; editable saved values no longer control it. Never run
both controllers. No rollback uses `compose down`, container removal, volume
removal, prune, DB restore or forced signals.

## Offline evidence and unverified boundary

Task 17 evidence remains in `evidence/task17-runtime-validation.txt`. Task 17B
commands, outcomes and limits are recorded separately in
`evidence/task17b-runtime-validation.txt` and the progress/changelog entries.
Cloud tests use an isolated PostgreSQL database and mocked Docker/systemd;
no real laptop boot/resume, Docker stop/start, backup or systemd installation
is asserted. The owner's platform-specific adoption and recovery checks remain
mandatory before production enablement.
