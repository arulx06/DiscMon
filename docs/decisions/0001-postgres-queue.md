# ADR 0001: PostgreSQL job queue instead of Redis/Celery

## Status
Accepted.

## Context
One owner, tens of sources, low job volume. We need exactly-once claims,
durable retries, lease recovery and idempotency without another state store.

## Decision
Use a `jobs` table with `FOR UPDATE SKIP LOCKED`, unique idempotency keys,
bounded attempts, available-at scheduling and lease expiry recovery.

## Consequences
- No Redis/broker to operate or secure.
- Queue depth and dead jobs are visible in the same database/backups.
- Throughput is ample for 30–100 sources; not designed for high fan-out SaaS.
