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

## Future authorized clean-volume drill

This drill is future work, separate from the non-mutating preflight, and
has not been performed as part of Task 2. It needs separate explicit
authorization and a pinned commit checked out fresh in a disposable worktree,
with no production `.env`, secrets or credentials available. Use a disposable
Compose project, network and database volume, with a reviewed test-only
override that removes secret mounts and supplies isolated test-only database,
user and credentials. Bind services only to confirmed nonconflicting
localhost ports.

Wait for PostgreSQL 18 readiness before any separately authorized migration.
Check the API endpoints directly at `http://127.0.0.1:<api-port>/health/live`
and `http://127.0.0.1:<api-port>/health/ready`; independently check that the
web root `http://127.0.0.1:<web-port>/` is available. These are distinct API
and web checks, not health checks proxied through the web surface. Import
disabled source definitions only with separate authorization. Never start
workers or the scheduler in Task 2.

Capture container, network and volume inventories before the drill, verify
pre-existing resources remain unchanged, then capture inventories again.
Clean up only the exact container, network and volume IDs created by this
drill; verify cleanup preserves the baseline resources. Never use `docker
compose down -v`.

M0 remains **PARTIAL**. Static preflight results are not clean-checkout runtime,
migration, health, CI or M0 acceptance evidence.

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
