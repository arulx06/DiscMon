#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."

if [[ -z "${DOCKER_BIN:-}" ]]; then
  if command -v docker >/dev/null 2>&1 && docker info >/dev/null 2>&1; then
    DOCKER_BIN=docker
  elif [[ -x "/mnt/c/Program Files/Docker/Docker/resources/bin/docker.exe" ]]; then
    DOCKER_BIN="/mnt/c/Program Files/Docker/Docker/resources/bin/docker.exe"
  else
    printf 'Docker CLI not found\n' >&2
    exit 69
  fi
fi
dc() { "$DOCKER_BIN" compose "$@"; }

usage() {
  printf 'Usage: %s <backup.dump.gz> <target_database>\n' "$0" >&2
  exit 64
}

dump="${1:-}"
target="${2:-}"
[[ -n "$dump" && -n "$target" ]] || usage
[[ -f "$dump" ]] || { printf 'Backup not found: %s\n' "$dump" >&2; exit 66; }
[[ "$dump" == *.gz ]] || { printf 'Expected a gzip-compressed custom dump\n' >&2; exit 65; }
[[ "$target" =~ ^[a-z][a-z0-9_]{0,62}$ ]] || {
  printf 'Target must match ^[a-z][a-z0-9_]{0,62}$\n' >&2
  exit 64
}

db_user="${POSTGRES_USER:-discmon}"
live_db="${POSTGRES_DB:-discmon}"
if [[ "$target" == "$live_db" ]]; then
  printf 'Refusing to restore over the live database (%s)\n' "$live_db" >&2
  exit 1
fi

gzip -t "$dump"

dc exec -T postgres psql -v ON_ERROR_STOP=1 -U "$db_user" -d postgres \
  -c "SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname = '$target' AND pid <> pg_backend_pid();" \
  -c "DROP DATABASE IF EXISTS \"$target\";" \
  -c "CREATE DATABASE \"$target\" TEMPLATE template0;"

gzip -dc "$dump" | dc exec -T postgres \
  pg_restore -U "$db_user" -d "$target" --no-owner --no-privileges --clean --if-exists

dc exec -T postgres psql -v ON_ERROR_STOP=1 -U "$db_user" -d "$target" -c "
SELECT
  (SELECT count(*) FROM opportunities) AS opportunities,
  (SELECT count(*) FROM opportunity_sources) AS opportunity_sources,
  (SELECT count(*) FROM reviews) AS reviews,
  (SELECT count(*) FROM digests) AS digests,
  (SELECT version_num FROM alembic_version) AS alembic_version;"

printf 'Restore verified in %s. Live database %s was not modified.\n' "$target" "$live_db"
