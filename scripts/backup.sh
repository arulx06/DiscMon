#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."

# Shared with the runtime controller; hold through dump verification/rename.
exec 9>>.runtime.lock
if ! flock --exclusive --wait 1500 9; then
  printf 'Backup failed: runtime lock busy after 25 minutes\n' >&2
  exit 75
fi

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

db_user="${POSTGRES_USER:-discmon}"
db_name="${POSTGRES_DB:-discmon}"
timestamp="$(date -u +%Y%m%dT%H%M%SZ)"
out="backups/discmon-${timestamp}.dump.gz"
tmp="${out}.partial"

mkdir -p backups
trap 'rm -f "$tmp"' EXIT

dc exec -T postgres \
  pg_dump -U "$db_user" -d "$db_name" --format=custom --compress=0 \
  | gzip -9 > "$tmp"

gzip -t "$tmp"
mv "$tmp" "$out"

printf 'Backup written: %s\n' "$out"
