# Ubuntu daily runtime — Task 17

**Review-only implementation. Nothing has been installed or enabled.** Target:
`/home/arulxamv/projects/DiscMon`, user `arulxamv`, rootful local Docker socket,
Compose project `discmon`, base `docker-compose.yml` only, exactly the existing
postgres/api/worker/scheduler/web containers, database `discmon`, persistent
volume `discmon_pgdata`. Additional profiles, overlays, rootless/remote Docker,
missing containers, moved checkouts or different labels require a new review;
never bypass the identity checks to make installation succeed.

## Behavior and safety boundary

- One oneshot service reconciles **current** `Asia/Kolkata` time every minute:
  start at 09:00 inclusive, stop at 21:00 exclusive. Calendar time has an explicit
  timezone, independent of the host timezone. Boot activation, persistent missed
  calendar activation and the next minute cover boot/resume and Docker recovery;
  no stale start/stop event is replayed. No wake-from-suspend is requested.
- Only existing containers start (`compose start --wait`, no `up`, builds, pulls,
  recreation, migrations, seeds or manual ingestion). The controller verifies
  project, service, working-directory and exact Compose-file labels and the
  PostgreSQL volume mount **before** changing anything. Smoke projects are not
  selected. All Docker commands target `/var/run/docker.sock` explicitly, with
  a sanitized environment and empty temporary Docker configuration.
- Before starting/stopping, it persists `restart=no` on all five containers.
  After successful adoption, Docker daemon restarts/reboots cannot auto-start
  them overnight. Daytime reconciliation retries stopped/crashed services.
  **Raw Compose up/recreate, manual starts and external supervisors are outside
  this guarantee:** they can restore `unless-stopped` or bypass the clock. Do not
  use them while scheduling is enabled. All runtime management must serialize
  through this controller; do not recreate containers concurrently.
- Ordered graceful stop: web, scheduler, worker, api, then postgres. Docker
  `stop --timeout -1` sends the configured stop signal and waits indefinitely,
  never escalating to SIGKILL. A failure stops further work, so PostgreSQL is
  not stopped after an earlier service-stop error. Containers, networks and
  volumes remain intact. Startup failure attempts the same safe stop and fails
  visibly; a startup crossing 21:00 is immediately followed by graceful stop.
- **Safety takes precedence over the 21:00 cutoff.** An unresponsive service or
  Docker daemon can leave the systemd job waiting indefinitely. Do not kill the
  controller, delete its lock, or force-stop Docker to make a deadline. Physical
  power loss, forced host shutdown and unrelated administrators cannot be made
  graceful by a timer. A naturally finishing stop may extend beyond 21:00.

## Backup coordination (existing units unchanged)

Owner-supplied units: `discmon-backup.service`, `Type=oneshot`, user `arulxamv`,
`ExecStart=/usr/bin/bash /home/arulxamv/projects/DiscMon/scripts/backup.sh`,
`TimeoutStartSec=20min`; timer at local 20:30, `Persistent=false`. The laptop's
local timezone must remain `Asia/Kolkata` for that **unchanged** timer.

The only backup change is a shared `flock` in `scripts/backup.sh`, held from
before Docker detection through dump compression/validation and final rename.
The controller uses that same repository `.runtime.lock`, waits up to 25 minutes,
and rechecks the oneshot state while holding it. If the unit is active but has
not acquired the lock yet, the controller releases it to let the backup finish.
This also protects directly invoked copies of the updated backup script.

An already running backup finishes before any runtime change. If shutdown wins
the lock before a *new* late backup starts, that backup waits, then its existing
`compose exec` fails against stopped PostgreSQL; it cannot start the database,
produce a successful empty backup, or leave a `.partial` file. The existing
backup service's 20-minute timeout still applies, including lock wait time.
Unknown/missing backup status, a failed backup, or a 25-minute coordination
wait fails the runtime service **without changing containers**. Inspect the
backup journal before deliberately resetting its failed state; never reset a
failure merely to force shutdown.

**No catch-up backup is invented.** The unchanged nonpersistent timer may miss
20:30 while powered off; an elapsed calendar event during suspend may run on
resume. Either ordering with runtime reconciliation is safe, but a backup is
not guaranteed if the machine resumes outside operating hours. There is no
fresh-backup prerequisite for shutdown and no automatic overnight restart to
make one. Check backup freshness separately and arrange any manual catch-up
inside operating hours. This is runtime scheduling, not a backup-policy change.

Do not run an old/unlocked script or another backup mechanism concurrently.
A pre-update systemd backup is still protected by its active oneshot status;
finish existing jobs before installation. Never remove/replace `.runtime.lock`
while any controller or backup process might hold it. It contains no data.

## Manual installation — owner approval required, not executed in cloud

First review/obtain the Task 17 commit and ensure its files are present locally.
Do not replace the checkout or revert earlier accepted work. Requirements:
Ubuntu systemd, Python 3.11+ with tzdata, util-linux `flock`, system-installed
Docker CLI/Compose supporting `start --wait --wait-timeout`, existing built
containers and the existing backup units. Do not use an isolated smoke project.

Run these **read-only checks** on the laptop:

```bash
cd /home/arulxamv/projects/DiscMon
git status --short
python3 --version
command -v flock
/usr/bin/docker --host unix:///var/run/docker.sock compose start --help
test "$(timedatectl show -p Timezone --value)" = Asia/Kolkata
sudo systemctl cat discmon-backup.service discmon-backup.timer
sudo systemctl show discmon-backup.service -p ActiveState -p Result
python3 -m unittest discover -s scripts/tests -v
bash -n scripts/backup.sh
systemd-analyze verify deploy/systemd/discmon-runtime.service deploy/systemd/discmon-runtime.timer
systemd-analyze calendar '*-*-* *:*:00 Asia/Kolkata'
```

Do not publish backup-unit output if it contains credentials. Confirm the units
match the above definitions, no existing backup/controller is active, and the
runtime service name is not owned by another installation. If the shared lock
already exists, it must be a regular file owned by `arulxamv`, not a symlink.
Then, **only after owner approval**, install/adopt:

```bash
cd /home/arulxamv/projects/DiscMon
# Reserve the shared lock without truncating/replacing an existing inode.
(umask 077; touch .runtime.lock)
sudo install -o root -g root -m 0644 deploy/systemd/discmon-runtime.service /etc/systemd/system/discmon-runtime.service
sudo install -o root -g root -m 0644 deploy/systemd/discmon-runtime.timer /etc/systemd/system/discmon-runtime.timer
sudo systemctl daemon-reload
# This changes restart policies and starts/stops according to CURRENT time.
sudo systemctl start discmon-runtime.service
# Proceed only if the adoption service succeeded and its journal is correct.
sudo systemctl enable --now discmon-runtime.timer
```

Do not edit/reinstall/enable/disable the existing backup units. Adoption must
succeed **before** enabling the runtime timer; until then the old automatic
restart policy can still start the stack overnight. Do not install a separate
boot `compose up` service or an overlapping start/stop cron job.

## Verification and failures

```bash
sudo systemctl status discmon-runtime.timer discmon-runtime.service --no-pager
sudo systemctl list-timers --all discmon-runtime.timer discmon-backup.timer
sudo journalctl -u discmon-runtime.service -u discmon-backup.service --since today --no-pager
/usr/bin/docker --host unix:///var/run/docker.sock ps -a --filter label=com.docker.compose.project=discmon --format '{{.ID}} {{.Names}} {{.Status}}'
# Names/running-state/restart policy only; never print full container inspection.
/usr/bin/docker --host unix:///var/run/docker.sock inspect --format '{{.Name}} {{.State.Running}} {{.HostConfig.RestartPolicy.Name}}' discmon-postgres-1 discmon-api-1 discmon-worker-1 discmon-scheduler-1 discmon-web-1
/usr/bin/docker --host unix:///var/run/docker.sock volume inspect --format '{{.Name}}' discmon_pgdata
```

Expect all restart policies `no`, running during 09:00–21:00 and stopped outside
it after graceful completion. Names above are default Compose names; do not
substitute a smoke name. A successful oneshot normally becomes `inactive (dead)`;
that alone is not failure. A failure has nonzero exit and `DiscMon schedule
FAILED` with the failed stage; raw CLI output, resolved Compose configuration,
container environment and credentials are suppressed. No application health or
backup success is asserted beyond the reported checks. Docker CLI output is
captured only in memory, not written to the journal or evidence.

After a failure inspect the stage, confirm Docker/backup health and identity,
and let the next minute retry. A failed backup needs manual review and, once
resolved, `sudo systemctl reset-failed discmon-backup.service`. Never change the
clock or suspend the laptop to test boundaries against live data. Use the
mocked tests for boot 02:00/10:00/22:00, cutoff, resume and failure scenarios.

## Rollback — owner-operated only

```bash
sudo systemctl disable --now discmon-runtime.timer
# Wait for any in-progress reconciliation/graceful stop to finish; do not kill it.
sudo systemctl stop discmon-runtime.service
sudo systemctl reset-failed discmon-runtime.service
sudo rm /etc/systemd/system/discmon-runtime.timer /etc/systemd/system/discmon-runtime.service
sudo systemctl daemon-reload
```

Leave the harmless backup lock addition and lock file in place; backup units
stay unchanged. Containers retain `restart=no` and their current running state.
To return to the previous always-on policy, **only after separately approving
possible overnight starts**, verify project/container identities again and run:

```bash
/usr/bin/docker --host unix:///var/run/docker.sock update --restart=unless-stopped discmon-postgres-1 discmon-api-1 discmon-worker-1 discmon-scheduler-1 discmon-web-1
```

This restores policy only, not running state. Rollback never removes database
resources, invokes Compose down, prunes, restores a database or runs migrations.

## Offline validation evidence

See [Task 17 evidence](evidence/task17-runtime-validation.txt). All command-driven
tests are mocked or use temporary files/fake Docker; no live Docker/systemd
operation was executed. External semantics: [Docker indefinite graceful stop](https://docs.docker.com/reference/cli/docker/container/stop/),
[systemd timer persistence/resume](https://www.freedesktop.org/software/systemd/man/latest/systemd.timer.html).
