# ADR 0005: Sheets mirror uses a transactional outbox

## Status
Accepted (optional, M5).

## Context
The owner has an existing Google Sheet, but Sheets access can expire and must
never block collection or corrupt canonical data.

## Decision
Changes that need mirroring create `sync_outbox` rows in the same transaction
as the canonical write. A worker upserts idempotently by opportunity and
revision. Failure leaves pending rows and a visible status.

## Consequences
- DB remains authoritative.
- Mirror lag is explicit.
- Manual sheet edits are not silently imported as truth.
