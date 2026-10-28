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

```powershell
# Full backend suite against real PostgreSQL (includes unit-style parser tests)
docker compose up -d postgres
$env:TEST_DATABASE_URL="postgresql+psycopg://discmon:discmon@127.0.0.1:55432/discmon_test"
Push-Location services\api
& ..\..\.venv\Scripts\python -m pytest -q
& ..\..\.venv\Scripts\python -m ruff check app tests scripts
& ..\..\.venv\Scripts\python -m mypy app scripts
Pop-Location

# Web typecheck, lint and build
cd apps/web; npm run typecheck; npm run lint; npm run build

# E2E (seed demo fixtures first; services must be running)
docker compose exec api python /app/scripts/seed_sources.py --demo
cd apps/web; npx playwright install chromium; npm run test:e2e
```

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
