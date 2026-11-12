# DiscMon

**Discover early. Prepare deliberately.**

DiscMon is a private, self-hosted, single-user career intelligence system. It
monitors approved public sources, preserves evidence, verifies eligibility
conservatively, detects material changes and keeps notifications quiet unless a
finding is genuinely rare and actionable.

It is not a job-board mockup. The source of truth is the PostgreSQL database fed
by real adapters and fixture-verified parsers.

## Stack

- Next.js 16, React 19, TypeScript, Tailwind CSS
- FastAPI, Pydantic v2, SQLAlchemy 2, Alembic
- PostgreSQL 18
- APScheduler plus a PostgreSQL `jobs` queue (`FOR UPDATE SKIP LOCKED`)
- httpx, feedparser, BeautifulSoup
- pytest, Playwright

No Redis, Celery, Kubernetes, vector database, n8n or paid LLM is required.

## Quick start (Docker Compose)

```bash
cp .env.example .env
# edit .env: set SESSION_SECRET and OWNER_API_TOKEN
docker compose up -d --build
docker compose exec api alembic upgrade head
docker compose exec api python /app/scripts/seed_sources.py
curl http://localhost:8000/health/ready
```

Open <http://localhost:3000>. The web container proxies API requests
server-side; the owner token is never shipped to the browser bundle.

Optional integrations are off by default. To enable Google Sheets, place a
service-account JSON file at
`secrets/google-service-account.json` (the whole directory is ignored by Git)
and set `GOOGLE_SHEETS_SPREADSHEET_ID`, `GOOGLE_SHEETS_TAB` and
`SHEETS_SYNC_ENABLED=true` in `.env`. Share the target sheet with the service
account email. Sheets is a mirror; PostgreSQL remains authoritative.

Changedetection is an internal signal source only. Configure
`CHANGEDETECTION_WEBHOOK_SECRET` and point its webhook at
`POST /v1/integrations/changedetection/webhook`; a valid signal still triggers
a bounded re-fetch from the approved source adapter. Telegram and SMTP are
optional delivery channels; the in-app alert inbox remains available.

## Discovery and integrations

- `/discover` shows candidate sources, approval/rejection and promotion
  controls. A promoted candidate creates a disabled source for review.
- Source detail supports JSON configuration editing and, when
  `config_json.discovery.enabled=true`, a bounded “Scan for links” action.
- `/health` exposes integration configuration, source health, recent jobs and
  alerts. Disabled integrations are shown as off, not as successful.

## Local development

```powershell
# Python 3.12+
py -3.12 -m venv .venv
.\.venv\Scripts\python -m pip install -e "services/api[dev]"
docker compose up -d postgres
$env:DATABASE_URL="postgresql+psycopg://discmon:discmon@127.0.0.1:55432/discmon"

# API (migrate first; app modules resolve from services/api)
Push-Location services\api
& ..\..\.venv\Scripts\python -m alembic -c alembic.ini upgrade head
& ..\..\.venv\Scripts\python -m app.serve --reload --port 8000
Pop-Location
# Worker (second terminal)
Push-Location services\api
& ..\..\.venv\Scripts\python -m app.worker
Pop-Location
# Scheduler (third terminal)
Push-Location services\api
& ..\..\.venv\Scripts\python -m app.scheduler
Pop-Location
# Seed registry candidates, plus labelled demo fixtures if desired
.\.venv\Scripts\python services\api\scripts\seed_sources.py --demo

# Web
cd apps/web
npm install
$env:INTERNAL_API_URL="http://127.0.0.1:8000"
$env:INTERNAL_API_TOKEN="dev-owner-token"
npm run dev
```

## Tests

Backend tests require a **dedicated, disposable PostgreSQL database** with the
existing schema already provisioned. Never reuse production configuration: the
automatic fixture **truncates application tables and restarts identities before
every test**. These checks do not prove a database is disposable; verify its
ownership and isolation independently before running pytest.

Set `APP_ENV=test` and explicitly set **both** `DATABASE_URL` and
`TEST_DATABASE_URL` to the same target (including user, password and endpoint).
Only `postgresql+psycopg` is supported. Database names must match
`[a-z][a-z0-9_]*_test`; `discmon` is never allowed. Hosts must be `localhost`,
`127.0.0.1` or `::1`. Remove inherited `PG*` environment settings; URL query
routing/options, including `port`, `hostaddr` and `service`, are rejected.
The sole query exception is `host` for a Unix socket at `/var/run/postgresql`
or `/tmp/discmon-test-<identifier>` (letters, digits, `_` and `-` only), with no
URL authority host. Put any nondefault socket port in the URL authority, e.g.
`postgresql+psycopg://<TEST_USER>@:55432/discmon_test?host=/tmp/discmon-test-isolated`.
Failures stop collection before the application engine is created. Before each
truncation, the same connection's database, authenticated/effective user and
client endpoint are verified again.

Bash / Ubuntu (replace placeholders with the independently verified disposable
test target; URL-encode credential components):

```bash
python3.12 -m venv .venv
.venv/bin/python -m pip install -e 'services/api[dev]'
export APP_ENV=test
export TEST_DATABASE_URL='postgresql+psycopg://<TEST_USER>:<TEST_PASSWORD>@127.0.0.1:<TEST_PORT>/discmon_test'
export DATABASE_URL="$TEST_DATABASE_URL"
cd services/api
../../.venv/bin/python -m pytest tests -q
../../.venv/bin/python -m ruff check app tests scripts
../../.venv/bin/python -m mypy app scripts
```

The safety regressions alone need **no running database**, and test unsafe
collection with dummy credentials without connecting:

```bash
cd services/api  # from repository root
../../.venv/bin/python -m unittest discover -s tests -p test_database_safety.py -v
```

Windows / PowerShell (same disposable-database prerequisite):

```powershell
$env:APP_ENV="test"
$env:TEST_DATABASE_URL="postgresql+psycopg://<TEST_USER>:<TEST_PASSWORD>@127.0.0.1:<TEST_PORT>/discmon_test"
$env:DATABASE_URL=$env:TEST_DATABASE_URL
Push-Location services\api
& ..\..\.venv\Scripts\python -m pytest tests -q
& ..\..\.venv\Scripts\python -m ruff check app tests scripts
& ..\..\.venv\Scripts\python -m mypy app scripts
Pop-Location

# Web typecheck, lint and build
cd apps/web; npm run typecheck; npm run lint; npm run build

# E2E (seed demo fixtures first; services must be running)
docker compose exec api python /app/scripts/seed_sources.py --demo
cd apps/web; npx playwright install chromium; npm run test:e2e
```

Fresh local Docker Compose acceptance remains incomplete; this test guard does
not establish full M0 acceptance.

Acceptance evidence is recorded in `docs/acceptance/acceptance-report.md`.
Current milestone status, known gaps and exact commands are in
`docs/PROGRESS.md`.

## Honest capability boundary

- ChatGPT Plus does not include API access, and this app cannot post into a
  personal ChatGPT conversation. DiscMon provides evidence-grounded briefs,
  Markdown/JSON exports and copy actions instead.
- Optional AI is disabled by default. Rules-only mode is fully functional.
- Google Sheets is an optional mirror, never the canonical store.
- `isRemote=true` alone is not India eligibility. Unknown stays unknown.
- Date-only deadlines never receive an invented cutoff time.
- A failed or partial source scan never closes opportunities.

## Documentation

- `docs/specification.md`
- `docs/implementation-plan.md`
- `docs/PROGRESS.md`
- `docs/architecture.md`
- `docs/sources-and-legal.md`
- `docs/deployment.md`
- `docs/operations-runbook.md`
- `docs/threat-model.md`
- `docs/decisions/`
- `docs/acceptance/acceptance-report.md`
- `docs/changelog.md`
