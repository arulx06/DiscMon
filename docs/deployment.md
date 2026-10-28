# Deployment

## Local (Windows/macOS/Linux)

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
