.PHONY: up down migrate seed seed-demo test lint typecheck e2e backup restore

PYTHON ?= python

up:
	docker compose up -d --build

down:
	docker compose down

migrate:
	docker compose exec api alembic upgrade head

seed:
	docker compose exec api python /app/scripts/seed_sources.py

seed-demo:
	docker compose exec api python /app/scripts/seed_sources.py --demo

test:
	cd services/api && $(PYTHON) -m pytest -q

lint:
	cd services/api && $(PYTHON) -m ruff check app tests scripts
	cd apps/web && npm run lint

typecheck:
	cd apps/web && npm run typecheck

e2e:
	cd apps/web && npm run test:e2e

backup:
	bash scripts/backup.sh

restore:
	bash scripts/restore.sh "$(DUMP)" "$(TARGET)"
