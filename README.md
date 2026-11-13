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

The Compose plugin must be available without per-user Docker configuration
(for example, a system-installed plugin). The script deliberately uses an empty
Docker config directory; a plugin installed only under `~/.docker/cli-plugins`
is not supported. It checks the required JSON and `--no-env-resolution`
capabilities and suppresses CLI diagnostics that might contain secrets. Host
checks also inspect published Docker TCP ports, including NAT-only mappings,
not just socket listeners.

## Safe Compose preflight (non-mutating)

From the repository root, render the Compose configuration before any runtime
operation. Use a unique lowercase suffix for each preflight project name:

```bash
python3 scripts/compose_preflight.py --project discmon-preflight-20261112-a17c
```

The script requires Python 3.12+ (standard library only) and Docker Compose v2/v5.
It renders the base configuration and base plus the `docker-compose.dev.yml`
overlay with `--env-file /dev/null`, `config --no-env-resolution`, and a
sanitized environment. It does not read `.env` or secrets, start services, or
mutate containers, networks, volumes or databases. Its redacted output
summarizes services, named volumes, ports, profiles and routing. No arbitrary
config, environment file or override can be supplied; production YAML is
unchanged.

The script refuses when any of `COMPOSE_FILE`, `COMPOSE_PROJECT_NAME`,
`COMPOSE_ENV_FILES`, `COMPOSE_PROFILES`, `DOCKER_HOST` or `DOCKER_CONTEXT` is
inherited with a non-empty value. For local static rendering only, deliberately
unset those inputs for that invocation if they are not needed; do not use this
wrapper with `--check-host`:

```bash
env -u COMPOSE_FILE -u COMPOSE_PROJECT_NAME -u COMPOSE_ENV_FILES \
  -u COMPOSE_PROFILES -u DOCKER_HOST -u DOCKER_CONTEXT \
  python3 scripts/compose_preflight.py --project discmon-preflight-20261112-a17c
```

`--check-host` uses only the local Docker socket/default local context; it does
not support or probe a remote daemon.

Static mode does not query the Docker daemon. It can report project-scoped
volume names, but cannot establish whether an existing resource is fresh or
whether a host port is available. The current Compose file publishes fixed
localhost ports `3000`, `8000`, `55432` and (with the `changedetection`
profile) `5000`; choosing a unique project name does not isolate those ports
from another project using them.

Optional `--check-host` performs read-only Docker container, volume and network
list queries plus local socket bind probes. It requires an available Docker
daemon and still does not prove that resources are disposable or fresh. The
preflight is an inspection only, not approval to start or modify anything.

## Isolated smoke configuration (static only)

Task 3 adds `docker-compose.smoke.yml`, checked by a separate config-only
validator. No runtime drill is authorized by this command:

```bash
python3 scripts/compose_smoke.py --project discmon-smoke-20261113-a17c
```

It renders **only base + smoke**, never the dev overlay, under a sanitized
environment with an empty env file and private Docker config disabled. It
requires system-installed Compose **v2 >= 2.24.4 or v5**, including `!override`
and `!reset` support; unsupported renderers fail closed. The six inherited
Compose/Docker routing variables listed above must be unset for this static
invocation. No daemon access or host checks occur.

Only PostgreSQL 18, API and web remain. PostgreSQL has no host port and uses
only the scoped internal `private` bridge. API/web also join a scoped ordinary
`ingress` bridge and publish `127.0.0.1:38000` and `127.0.0.1:33000` respectively;
`--api-port` and `--web-port` select alternatives. The obsolete `--db-port` is
rejected. Database routing remains `postgres:5432/discmon_smoke_test`.
Credentials are public **test-only placeholders**, not deployment secrets.
There are no bind mounts, workers, scheduler or optional integrations.
**API/web may have outbound connectivity through ingress; this is not complete
egress isolation.** Production preflight and production Compose are unchanged.

Static validation proves the intended model, **not** resource freshness, free
ports, effective runtime networking or app health. The separate isolated
clean-volume drill was accepted for M0 on 2026-11-13; that acceptance is not a
production deployment or proof of complete outbound isolation. See
[deployment](docs/deployment.md#isolated-m0-acceptance) for evidence and limits.

## Quick start (Docker Compose deployment)

> **This is a state-changing deployment, not the Task 2 preflight.** Starting
> services, migrating the database or seeding sources requires explicit
> authorization for the target environment. A successful static preflight does
> not provide that authorization.

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
```

For E2E, use a **fresh disposable** `*_test` database with the matching test
variables above, never the production Compose database. From `services/api`,
validate the actual connection before migrating/seeding it:

```bash
../../.venv/bin/python - <<'PYTHON'
import os
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, text
from tests.conftest import validate_test_environment, validate_connected_database

target = validate_test_environment(os.environ)
engine = create_engine(os.environ["DATABASE_URL"])
with engine.connect() as connection:
    identity = connection.execute(text(
        "SELECT current_database() AS database, current_user AS username, "
        "session_user AS session_username"
    )).mappings().one()
    validate_connected_database(
        target, engine.url, identity, connection.connection.driver_connection.info
    )
engine.dispose()
command.upgrade(Config("alembic.ini"), "head")
PYTHON
../../.venv/bin/python scripts/seed_sources.py --demo
```

This documented seed supplies both application-link cases: the labelled
maintainer residency has no application URL; the labelled senior backend role
has a separate `/apply` URL. No Outreachy ingestion or external collection is
needed. Seeding is insert-only: use a fresh test DB rather than an old demo DB.

Start the API with these same test DB settings and the web app pointed at it
(`INTERNAL_API_URL`, with `INTERNAL_API_TOKEN` matching `OWNER_API_TOKEN`). No
worker or scheduler is needed. After the web production build, from `apps/web`:

```bash
npx playwright install chromium
PLAYWRIGHT_BASE_URL=http://127.0.0.1:3000 npm run test:e2e
```

Playwright exercises both link states, review persistence and overflow at 360px
and 1440px. Missing demo records fail the tests; they are not silently skipped.

This local deployment procedure was not the isolated M0 acceptance drill and
does not establish production deployment acceptance.

Acceptance evidence is recorded in `docs/acceptance/acceptance-report.md`.
M0 is **ACCEPTED** based on the isolated drill; M5 remains **PARTIAL**. The
fixture-backed connected discovery/approval/promotion/ingestion/Sheets-failure
regression and full backend suite passed locally, with Ruff and mypy clean; this
is not full M5 or live Sheets acceptance, and no CI result is claimed. See
`docs/PROGRESS.md` for commands and isolated test database details.

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
