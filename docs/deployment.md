# Deployment

## Safe Compose preflight (non-mutating)

From the repository root, use a unique lowercase suffix for the project name:

```bash
python3 scripts/compose_preflight.py --project discmon-preflight-20261112-a17c
```

The preflight requires Python 3.12+ (standard library only) and Docker
Compose v2/v5. It validates the base Compose file and the base plus
`docker-compose.dev.yml` overlay using `--env-file /dev/null`,
`config --no-env-resolution`, and a sanitized environment. It does not read
`.env` or secrets, start services, or mutate runtime resources or data. Its
redacted report covers services, volumes, ports, profiles and routing. No
arbitrary config, environment file or override is accepted; production YAML is
unchanged.

It refuses if any non-empty inherited `COMPOSE_FILE`,
`COMPOSE_PROJECT_NAME`, `COMPOSE_ENV_FILES`, `COMPOSE_PROFILES`, `DOCKER_HOST`
or `DOCKER_CONTEXT` is present. Only for local static rendering, deliberately
unset those variables for that invocation when needed; do not unset them
to redirect a host check. `--check-host` uses the local Docker socket/default
local context only; it does not connect to or inspect a remote daemon.

By default it does not query the Docker daemon. It reports project-scoped
volume names but cannot establish their freshness or host-port availability.
`--check-host` optionally performs read-only Docker container, volume and
network list queries and local socket bind probes; that option requires a
working Docker daemon and does not establish resource ownership or freshness.

Host ports are fixed in the current Compose configuration: web `3000`, API
`8000`, PostgreSQL `55432`, and changedetection `5000` when its profile is
enabled. A unique project name scopes Compose resources but does not avoid a
host-port conflict. Preflight is not authorization to start services, migrate
or seed a database, or perform another runtime mutation.

The Compose plugin must be available without per-user Docker configuration
(for example, a system-installed plugin). The script deliberately uses an empty
Docker config directory; a plugin installed only under `~/.docker/cli-plugins`
is not supported. It checks the required JSON and `--no-env-resolution`
capabilities and suppresses CLI diagnostics that might contain secrets. Host
checks also inspect published Docker TCP ports, including NAT-only mappings,
not just socket listeners.

## Isolated smoke configuration (Task 3)

This is **configuration design and static verification only**, not an M0
runtime drill. Use Python 3.12+ and system-installed Docker Compose v2 >=
2.24.4 or v5. Compose's [merge rules](https://docs.docker.com/reference/compose-file/merge/)
append distinct port mappings; ordinary port lists are unsafe here. Explicit
`!override` replaces ports/environments/volume definitions, while `!reset`
removes private mounts, unused environment anchors and entire unwanted services.

```bash
python3 scripts/compose_smoke.py --project discmon-smoke-20261113-a17c
# Alternative non-production bindings (still static only):
python3 scripts/compose_smoke.py --project discmon-smoke-20261113-b28d \
  --api-port 38001 --web-port 33001
```

If needed, use the README's `env -u` wrapper for this static invocation only.
The validator accepts only the explicit project and two API/web port options, never
arbitrary files, environment files, profiles or a host-check mode. It reuses
the existing preflight's redacted CLI runner and safety exception without
changing the production preflight. The subprocess environment contains only a
system PATH, empty temporary HOME/Docker config, locale and validated smoke
project/port values. Both Compose paths are fixed and absolute, `/dev/null` is
the explicit env file, and `config --no-env-resolution --format json` is the
only render operation. `--profile '*'` verifies exclusions even if all profiles
were requested. No Docker daemon query occurs; malformed/unsupported rendering
fails without forwarding CLI output or credentials.

Resolved default model:

| Item | Smoke-only configuration |
| --- | --- |
| Project | Explicit `discmon-smoke-<8–40 lowercase unique suffix>`; protected names rejected |
| Services | Exactly postgres, api, web; none has profiles or restart loops |
| PostgreSQL | `postgres:18-alpine`, database `discmon_smoke_test`, user `discmon_smoke_user` |
| Database route | API uses only `postgres:5432/discmon_smoke_test`; exact test credentials required |
| Readiness | `pg_isready -U discmon_smoke_user -d discmon_smoke_test` |
| Web route | `http://api:8000`; test token matches authenticated API |
| Host ports | PostgreSQL: none; API `127.0.0.1:38000`, web `127.0.0.1:33000` |
| Storage | Only `<project>_pgdata` at `/var/lib/postgresql`; no external/custom storage or host binds |
| Networks | `<project>_private` internal bridge (all three); `<project>_ingress` ordinary bridge (API/web only); no external networks |
| Excluded | Worker, scheduler and changedetection removed, not merely hidden behind profiles |
| Integrations | No provider credentials/endpoints; Sheets/AI false; API/web ingress may permit outbound traffic |

The overlay requires an explicit `DISCMON_SMOKE_PROJECT` when used directly;
only the validator enforces the naming/port/resource policy. Do not invoke raw
Compose to bypass validation. Public test-only placeholder passwords/tokens
must never be repurposed for production. No production `.env`, private Docker
configuration, repository secrets or backup mounts are loaded. API/web have no
runtime bind mounts, and build contexts are restricted to their existing
Dockerfiles; **no builds are executed here**.

PostgreSQL has no host publication and attaches exclusively to `private`;
connections use `postgres:5432` from the API. The API and web attach to both
networks, with service-network mappings replaced using `!override` so inherited
networks cannot survive merging. Only their two loopback ports are published.
The obsolete `--db-port` option is rejected; there is no smoke database host-port
setting. Top-level networks are also replaced, never external or pre-existing.

**Residual limitation:** the ordinary ingress bridge may permit outbound traffic
from API/web. This is not complete egress isolation, and disabled integrations
are not a firewall. PostgreSQL has no ingress attachment or host port, but Docker
host administrators and authorized private-network peers can still reach it.
No source ingestion or external provider testing is authorized by this design.
Docker documents [ordinary bridge egress and port publication](https://docs.docker.com/engine/network/drivers/bridge/)
and [loopback binding semantics](https://docs.docker.com/engine/network/port-publishing/).

Retry 1 established a healthy PostgreSQL container with a requested host binding
but `NetworkSettings.Ports["5432/tcp"] = null` and no `docker port` mapping on
an internal-only bridge. This motivates separating ingress; it does not prove a
Docker defect or prove the replacement works at runtime. A later drill needs new
explicit owner authorization, new project identity and fresh safety gates.

Static success is not proof that the proposed volume/network names are unused,
API/web ports are free, published ports on the ingress bridge work on the target
engine, or the database/API/web are healthy. No schema is created or migrated.
The API image does not automatically migrate or seed. API readiness checks
only `SELECT 1`, not schema compatibility; the web dashboard needs migrated
tables, so web-root acceptance requires a separately authorized isolated
migration. Source import and UI scan/notification actions are outside the smoke
procedure. Runtime network isolation does not constrain build-time registry or
package access. The separate isolated M0 acceptance is recorded below; static
configuration validation alone is not runtime acceptance.

## Local deployment (Windows/macOS/Linux)

The following is a deployment, not a preflight. Run it only after explicit
authorization for the target environment.

Requirements: Docker Desktop or another Compose engine, Python 3.12+, Node 22+.

```bash
cp .env.example .env
docker compose up -d --build
docker compose exec api alembic upgrade head
docker compose exec api python /app/scripts/seed_sources.py
curl http://localhost:8000/health/ready
```

Ports: web `3000`, API `8000`, Postgres host `55432` (private by default on a
VPS firewall). Do not publish Postgres or changedetection on an untrusted host.

## Isolated M0 acceptance

M0 was **ACCEPTED on 2026-11-13** from Retry 5's independent engineering
acceptance at base `2f510c1d82532e1b87acec9082f2c56e073ec07e` (PR #4 merged).
Supplied evidence records 38 Compose tests passed; fresh isolated PostgreSQL
18.7, API and web startup; actual database identity verified before one Alembic
upgrade to `d4a7c1e9f210`; all 19 tables present with no seeded application
records; API live/ready and dashboard (`Radar overview`) HTTP 200; ownership-safe
cleanup; unchanged Git state; and final exit 0.

Evidence: [Retry 5 report](https://api.hoplite.sh/api/attachments/ceb6a69a074e494ca9c94ef85a6eb650?media=file)
and [Retry 5 original command transcript](https://api.hoplite.sh/api/attachments/340fa8f8f5e847c3bc51dd29e2fc73d7?media=file).
This was an isolated cloud drill, not production deployment or proof of full
outbound network isolation. The drill is documented from supplied evidence and
was not rerun for this update. M5 remains **PARTIAL**: the fixture-backed
connected-flow regression and full backend suite passed locally with Ruff and
mypy clean, but this is not full M5 or live Sheets acceptance. CI is not claimed;
commands and isolated test database details are recorded in `PROGRESS.md`.

## Always-on VPS

1. Ubuntu LTS, 2 vCPU / 4 GB RAM minimum (8 GB if adding browser services).
2. Install Docker Engine and Compose.
3. Clone the repository and create `.env` from `.env.example` with mode `0600`.
4. Set:
   - `APP_ENV=production`
   - `OWNER_AUTH_MODE=token`
   - a long random `OWNER_API_TOKEN` and `SESSION_SECRET`
   - `APP_BASE_URL` and `ALLOWED_ORIGINS` to the private URL
5. `docker compose up -d --build`
6. `docker compose exec api alembic upgrade head`
7. `docker compose exec api python /app/scripts/seed_sources.py`
8. Put Tailscale Serve in front of the web port. Keep the API and database on
   the private Docker network. Do not expose the admin UI publicly.
9. Configure a nightly backup timer calling `bash scripts/backup.sh`.
10. Run the restore drill in `docs/operations-runbook.md` quarterly.

## Backups

`pg_dump` custom format, gzip, 7 daily plus 4 weekly. Store encrypted off-box.
The restore script creates a clean database and verifies counts and ownership
decisions.

## Upgrades

Back up, pull the pinned image/tag, run a migration dry run, roll services,
check `/health/ready` and one source run, then watch source health for 24h.
Irreversible migrations require a documented forward recovery plan.

## Environment variables

See `.env.example`. Required: `DATABASE_URL`, `SESSION_SECRET`,
`OWNER_API_TOKEN`, `INTERNAL_API_URL`, `INTERNAL_API_TOKEN`. Optional:
GitHub, changedetection, Telegram, SMTP, Sheets and AI. Core operation never
requires an AI credential.

The Compose stack mounts `./secrets` read-only at `/secrets` for API, worker
and scheduler. Keep the directory mode `0700`. To enable Sheets:

1. Create a Google service account and download its JSON key to
   `secrets/google-service-account.json`.
2. Share the target spreadsheet with the service-account email.
3. Set `GOOGLE_SHEETS_SPREADSHEET_ID`, `GOOGLE_SHEETS_TAB=Opportunities` and
   `SHEETS_SYNC_ENABLED=true`.
4. Restart API, worker and scheduler and check `/health` integration status.

Sheets failures are recorded in `sync_outbox` and never block ingestion.
`secrets/*` is ignored by Git; only `secrets/.gitkeep` is tracked.

## Migrations

Always back up first, then run the migration before rolling API/worker/
scheduler:

```bash
bash scripts/backup.sh
docker compose exec api alembic upgrade head
docker compose exec api alembic check
```

Current M5/M6 head is `d4a7c1e9f210`. Verify `/health/ready` and a source run
after upgrading. A clean database migration creates 17 registry candidates and
zero opportunities when followed by `seed_sources.py`.

## Optional services

`docker compose --profile changedetection up -d` starts the watcher. It is a
trusted internal service; its API key stays server-side. Configure the shared
webhook secret and timestamp tolerance in `.env`; the receiver deduplicates
body hashes and only enqueues authoritative source re-fetches. RSSHub/Scrapy/
Playwright are intentionally not part of the MVP Compose stack.

SMTP and Telegram are optional delivery adapters. The in-app alert inbox is
always the durable record; missing external configuration leaves alerts
visible instead of silently discarding them.

## Ubuntu daily operating window (Task 17)

See [09:00–21:00 Asia/Kolkata runtime scheduling](runtime-schedule.md) for
review-only controller/units, backup locking, owner-approved installation,
verification and rollback. No live deployment or schedule enablement is claimed.
Do not use ordinary Compose up/recreate while this schedule is enabled: it can
restore automatic restart policies and bypass the overnight guard.
