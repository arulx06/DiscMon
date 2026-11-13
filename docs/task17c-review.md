# Task 17C — graceful scheduler shutdown (review only)

## Supported diagnosis

The reviewed base is `6d36be6` (Task 17B / draft PR #16). The scheduler,
worker, runtime helper and queue have no differences between `8c54d70` and
that reviewed base (`git diff 8c54d70 6d36be6 -- services/api/app/{scheduler,worker,runtime}.py services/api/app/services/queue.py`).
This is a pre-existing defect, not a demonstrated Task 17B regression.

In `scheduler._install_signal_handlers`, the `global _running` declaration
was in the **outer** function. It does not apply to the nested `stop` function.
Its assignment creates a local variable and leaves the module flag `True`.
Python accepts SIGTERM, runs the handler and consumes the signal, but the
scheduler continues its loop indefinitely. Thus a sleeping process, no pending
signals and no active jobs are consistent with this application bug. Docker
successfully sending a signal is not evidence that the handler stops the app.

`docs/evidence/task17c-scope.txt` records actual baseline handler bytecode
(`STORE_FAST`) and a real `signal.raise_signal(SIGTERM)` leaving the module flag
`True`; the corrected handler uses `STORE_GLOBAL` and sets the wake event.
The subprocess regression also reproduces the failure without Docker. This
establishes an application defect independently of Docker signal delivery.
It does not establish the exact database wait or image contents on the laptop;
no production container or Ubuntu laptop was accessed.

The original unconditional 30-second sleep is a secondary shutdown delay,
not the cause of the indefinite idle failure. During an iteration, session
creation/pool pre-ping, queue recovery, queries, enqueues and commit are awaited.
The flag is checked between iterations, not during database calls. A genuinely
unbounded database wait still waits for resolution; no speculative cancellation
or database timeout has been added.

## Small correction and file inventory

- `services/api/app/scheduler.py`: put `global` in the actual signal callback;
  wake the asyncio loop with `call_soon_threadsafe` and an event. Interrupt only
  the idle wait, skip it after a shutdown request and never start another tick.
  SIGINT retains the same graceful behavior. No in-flight task is cancelled.
- `services/api/tests/scheduler_process.py`: isolated process harness using
  real OS signals, a controlled PostgreSQL wait, and an error-path release.
  A test-only three-second watchdog sets the original module flag, allowing
  the broken baseline to exit naturally without a forced signal. It never
  cancels the scheduling transaction. Watchdog use is a test failure.
- `services/api/tests/test_scheduler_shutdown.py`: assert SIGTERM termination,
  completion of active work, no next tick, visible errors, unchanged complete
  opportunity/pending-job rows and a committed queued source job. A separate
  test uses a one-hour idle interval to prove event wakeup, not tick expiry.
- `services/api/tests/test_discovery_scheduler.py`: adapt the existing quiet-tick
  test to request shutdown after the actual iteration, rather than monkeypatch
  the removed sleep. Its existing event-log assertion is unchanged.
- Operational documentation: this review, `docs/runtime-schedule.md`,
  `docs/PROGRESS.md`, `docs/changelog.md`, and the five evidence transcripts.

No runtime-controller, backup, worker, queue, schema, migration or ingestion
implementation changes. The scheduler still commits its single iteration
transaction before exiting. Pending work remains in PostgreSQL for workers;
queue uniqueness, recovery, claims and transaction boundaries are unchanged.

## Reproduction and recorded validation

All data is disposable, local test data. Public test credentials below are not
production credentials. Setup commands (exit 0):

```sh
uv venv .venv
uv pip install --python .venv/bin/python -e 'services/api[dev]'
docker run -d --name discmon-task17c-postgres \
  -e POSTGRES_USER=discmon -e POSTGRES_PASSWORD=discmon \
  -e POSTGRES_DB=discmon_task17c_test -p 127.0.0.1:55439:5432 postgres:18-alpine
export APP_ENV=test OWNER_AUTH_MODE=disabled
export DATABASE_URL=postgresql+psycopg://discmon:discmon@127.0.0.1:55439/discmon_task17c_test
export TEST_DATABASE_URL="$DATABASE_URL"
(cd services/api && ../../.venv/bin/alembic upgrade head)
```

- `task17c-before.txt`: baseline process cases, **3 failed**, exit **1**.
  Idle/database/error used the test-only watchdog after 3.094/3.223/3.108s.
  No force-stop or SIGKILL was used. To reproduce on the reviewed baseline,
  apply only the two new test files, then run the command in that transcript.
- `task17c-after.txt`: all four focused tests pass; real process SIGTERM-to-exit
  0.114s idle, 1.653s with a 1.5s PostgreSQL wait, 0.219s on the error path.
  Each process exits **0**. The database case observes `pg_stat_activity`
  `wait_event = 'PgSleep'` before signalling, then verifies committed work.
- `task17c-checks.txt`: full backend suite, Ruff, mypy, and host/controller/backup
  script tests, with exact commands, complete output, timings and exit codes.
- `task17c-scope.txt`: actual-handler signal/bytecode comparison described above.
- `task17c-docker.txt`: full isolated Docker driver and output. Built the normal
  backend Dockerfile (`docker build -t discmon-task17c-api services/api`, exit 0).
  A separate `discmon_task17c_container_test` database was created and migrated;
  `discmon-task17c-isolated` connects only the test PostgreSQL and test schedulers.
  Run the driver after creating these resources (commands below). The actual
  `python -m app.scheduler` is PID 1, with normal 30-second tick interval.
  `docker stop --time=-1` exits **0** in **0.209s** idle and **0.499s** with a
  deliberate jobs-table lock released 0.3s after SIGTERM. The active scheduler
  remains alive while blocked, then commits and exits. Both containers report
  exit **0**, `OOMKilled=false`, and `scheduler_stopped`; queued jobs remain.
  Docker 29.1.3 warns that `--time` is deprecated in favor of `--timeout`, and
  this sandbox lacks swap-limit support. Neither warning prevents the tests.

```sh
docker network create discmon-task17c-isolated
docker network connect discmon-task17c-isolated discmon-task17c-postgres
docker exec discmon-task17c-postgres psql -U discmon -d discmon_task17c_test \
  -c 'CREATE DATABASE discmon_task17c_container_test'
docker run --rm --network discmon-task17c-isolated -e APP_ENV=test \
  -e DATABASE_URL=postgresql+psycopg://discmon:discmon@discmon-task17c-postgres:5432/discmon_task17c_container_test \
  discmon-task17c-api python -m alembic upgrade head
```

## Limitations and safe next step

**Do not activate the Task 17B controller based on this scheduler fix alone.**
The worker contains the same nested-handler scope defect. It is deliberately
unchanged in this bounded scheduler correction and needs its own reviewed fix
and real-signal active-job validation: the controller stops scheduler, then
worker, before API/PostgreSQL, so the worker can still block full shutdown.

Owner-approved Ubuntu **scheduler-only** retesting is reasonable after review
and installation of the corrected image, with no forced timeout and no active
ingestion. It has not been performed here. Continue preserving the existing
controller identity, backup protections, restart policy and user data. An
unlimited stop can still wait legitimately for an unresolved DB lock/outage;
inspect and resolve the database cause, never substitute SIGKILL. Full controller
activation additionally requires resolving the worker blocker. No production
access, deployment, live Docker/systemd changes, ingestion, protected-branch
changes or PR #16 merge was performed.
