# Task 17D — graceful worker shutdown (review only)

## Baseline and substantiated root cause

This correction starts at exact accepted Task 17C commit `4e0448f`, parent
`6d36be6`. It does not rewrite Task 17C or modify the scheduler, queue,
controller, Compose configuration, migrations, ingestion rules or backup units.

In `services/api/app/worker.py`, the original outer `_install_signal_handlers`
function declared `global _running`, but its nested `stop` callback did not.
The nested assignment compiled to `STORE_FAST`: SIGTERM was consumed and a
local variable changed, while the worker's actual module flag remained true.
`docs/evidence/task17d-scope.txt` includes the complete probe and output with
real OS signal delivery and before/after flag/bytecode evidence. This is the
same pre-existing Python scope defect diagnosed in Task 17C, independently
confirmed for the worker rather than inferred from that plan.

The old worker repeatedly ran recovery, claims and processing while the flag
remained true. An empty queue led to a two-second sleep and further polling;
active jobs did not make shutdown effective either.

## Correction, claim race and transaction safety

The actual state-changing nested callback now declares `global _running`.
The raw OS signal callback schedules that callback with
`loop.call_soon_threadsafe`; the loop callback changes the flag and sets an
asyncio wake event. The two-second idle wait is interruptible, without a forced
stop deadline or any cancellation of a job/database operation.

Observing shutdown on the event loop is deliberate: it cannot mutate the flag
between a synchronous claim guard and starting its coroutine. There is no loop
yield between them. A second guard immediately inside the session context
prevents a fresh claim if session entry observed shutdown. Once an asynchronous
claim has begun, it is treated as in-flight work, even if the OS signal arrives
while it is waiting on SQL or commit:

1. Finish the existing claim transaction and commit, retaining its one attempt,
   ownership and lease. Never abandon an already-claimed job merely because
   the stop callback ran while `claim_job` or commit was awaiting.
2. Process that job through its unchanged normal path. Success commits normal
   work then records `succeeded`; failure rolls back the fixture operation,
   records `job_failed`, clears locks and uses existing retry/dead semantics.
3. Stop before another claim, recovery/poll iteration or idle wait.

The real queue implementation is unchanged. Tests hold a PostgreSQL wait inside
claim and before its commit returns, with `pg_stat_activity` confirming the
wait before signalling. They test both success and failure of active work, not
just a changed Boolean. Test-only work is a fixture-backed database transaction;
no external provider is contacted. A session-entry race and event-loop signal
serialization have separate deterministic tests.

## Exact changed-file inventory

- `services/api/app/worker.py`: callback scope, loop-serialized shutdown state,
  idle wake event and guard immediately before claiming. All business-job,
  success/failure, recovery, retry and completion code remains unchanged.
- `services/api/tests/worker_process.py`: isolated real-signal process helper;
  wraps the real claim and commit and substitutes only fixture job work. A
  test-only three-second watchdog changes the real loop flag, so the broken
  baseline exits naturally rather than being force-killed. Watchdog use fails
  the test. Only the watchdog task is cancelled on normal teardown, never work.
- `services/api/tests/test_worker_shutdown.py`: ten process cases (idle,
  success, failure, claim, commit, each with SIGTERM and SIGINT), plus two race
  tests. Assert no second claim; complete unchanged opportunity/pending/next-job
  rows; success effect commit, failure effect rollback, provenance/idempotency
  keys, exactly one attempt, cleared locks, future retry eligibility and a
  later simulated eligible retry. Recovery cannot resurrect the finished job.
- `docs/runtime-schedule.md`: current review-only shutdown status and Ubuntu
  retesting limits, preserving the runtime window and backup policy.
- `docs/PROGRESS.md`, `docs/changelog.md`: recorded validation results.
- `docs/task17d-review.md`: this diagnosis, inventory, commands and risk report.
- `docs/evidence/task17d-{before,after,checks,docker,scope,environment}.txt`:
  complete focused/full outputs, commands, timings, codes and environment retry.

No existing worker or queue test required modification. Task 17C's scheduler
implementation and regression tests remain byte-for-byte unchanged.

## Reproduce and verify

Use the disposable PostgreSQL 18 sandbox container from Task 17C, not a real
DiscMon database. The publicly documented credentials below are test-only.

```sh
uv venv .venv
uv pip install --python .venv/bin/python -e 'services/api[dev]'
# Existing isolated container; do not substitute a production container.
docker start discmon-task17c-postgres
export APP_ENV=test OWNER_AUTH_MODE=disabled
export DATABASE_URL=postgresql+psycopg://discmon:discmon@127.0.0.1:55439/discmon_task17c_test
export TEST_DATABASE_URL="$DATABASE_URL"
```

Fresh setup, if the isolated container does not exist:

```sh
docker run -d --name discmon-task17c-postgres \
  -e POSTGRES_USER=discmon -e POSTGRES_PASSWORD=discmon \
  -e POSTGRES_DB=discmon_task17c_test -p 127.0.0.1:55439:5432 postgres:18-alpine
(cd services/api && ../../.venv/bin/alembic upgrade head)
```

The backend fixture validates the explicit loopback `_test` database and
connection identity before any table cleanup. Process tests inherit only this
test target. To reproduce the baseline failure, apply only the two new test
files to `4e0448f` and run:

```sh
(cd services/api && ../../.venv/bin/pytest tests/test_worker_shutdown.py \
  -k 'idle and SIGTERM' -v -s)
```

Baseline: **1 failed**, pytest **exit 1**; app exits **0** only after the test
watchdog changes the actual flag, SIGTERM-to-exit **4.095s** (three-second
watchdog plus remainder of idle interval). The assertion is specifically
`Signal did not stop worker`, not a test setup failure. See `task17d-before.txt`.

Focused and final commands, complete outputs and timings are in
`task17d-after.txt` and `task17d-checks.txt`:

```sh
(cd services/api && ../../.venv/bin/pytest tests/test_worker_shutdown.py -v -s)
(cd services/api && ../../.venv/bin/pytest tests/test_worker_shutdown.py tests/test_queue.py -v -s)
(cd services/api && ../../.venv/bin/pytest tests -q)
(cd services/api && ../../.venv/bin/ruff check app tests scripts)
(cd services/api && ../../.venv/bin/mypy app scripts)
.venv/bin/python -m unittest discover -s scripts/tests -v
.venv/bin/python -m compileall -q services/api/app services/api/tests scripts
docker compose -f docker-compose.yml config --quiet
git diff --exit-code 4e0448f -- services/api/app/scheduler.py scripts deploy \
  docker-compose.yml services/api/app/services/queue.py
```

`task17d-after.txt` records the first 11-case passing implementation. After
serializing signal observation to close the check/call bytecode gap, final
results are recorded under the explicit final-verification heading in
`task17d-checks.txt`. A new serialization test was added, not an assertion
relaxed. The feedparser deprecation warning is pre-existing.

## Isolated actual Docker validation

Built the normal backend Dockerfile twice, including the final implementation:
`docker build -t discmon-task17d-api services/api` (both exit 0).
Created and migrated only `discmon_task17d_container_test` on the sandbox
PostgreSQL container, using the isolated Task 17C bridge network:

```sh
docker exec discmon-task17c-postgres psql -U discmon -d discmon_task17c_test \
  -c 'CREATE DATABASE discmon_task17d_container_test'
# Fresh environments first create/connect discmon-task17c-isolated as in Task 17C.
docker run --rm --network discmon-task17c-isolated -e APP_ENV=test \
  -e DATABASE_URL=postgresql+psycopg://discmon:discmon@discmon-task17c-postgres:5432/discmon_task17d_container_test \
  discmon-task17d-api python -m alembic upgrade head
```

`task17d-docker.txt` retains the complete drivers and outputs, including the
final rerun after signal serialization. Docker executes the worker as PID 1.
Active cases use the exact committed fixture helper mounted read-only; the
unmodified production `python -m app.worker` entry point is additionally tested
idle. Every stop uses `docker stop --timeout=-1`, with **no** automatic SIGKILL.
Final Docker timings: **0.214s** for the unchanged production entry point idle;
fixture loop idle **0.212s**, success **1.407s**, failure **1.387s**, claim
**1.399s**, commit **1.403s**, every CLI/application exit **0**.
Drivers observe a real PostgreSQL `PgSleep` before active signals, verify stop
is still waiting after 0.1s, then let the 1.2s fixture wait finish naturally.
They assert app/CLI exit 0, `OOMKilled=false`, one claim, no watchdog, correct
queue outcome and unchanged pending/next-job rows. Successful work commits;
failed work rolls back and enters retry wait with cleared locks and one attempt.
Stopped test containers are removed without force. No production resources used.

The first driver attempt used a marker bind directory under `/tmp` outside the
checkout and was refused (Docker exit 125). `task17d-environment.txt` records
the exact policy evidence; the retry used a temporary directory inside the
checkout, without changing policy. Docker warns that swap limits are unavailable
in this sandbox; it does not affect the successful tests.

## Remaining risks and Ubuntu decision

No new application-process shutdown blocker was found for the configured
long-running scheduler/worker services. **Owner-approved production Ubuntu
retesting can resume after review and installation of the corrected images.**
This is permission to consider retesting, not a claim of laptop validation or
controller adoption: no production access, deployment, restarts, ingestion,
migrations, systemd changes or laptop tests were performed here. Neither PR #16
nor PR #17 was merged. The 09:00–21:00 default, 20:30 backup, controller identity
and backup protections remain unchanged. No PR should be merged automatically.

Unresolved database waits or hung external work can still delay an unlimited
stop; diagnose the wait rather than force-kill or cancel the transaction. This
patch does not add database/external-operation deadlines. Process death or
ambiguous commit still uses the pre-existing at-least-once recovery model:
300-second leases, no lease renewal/fencing, and later retry can repeat side
effects. Concurrent workers/lease expiry and crash-proof exactly-once execution
are not redesigned or claimed here. Ordinary failure/retry behavior remains
unchanged, including terminal failure at max attempts. Manual `--once` mode
still uses its original standalone entry path without long-running signal
registration; the controller/Compose does not use it. It is not covered by this
service-shutdown correction.
