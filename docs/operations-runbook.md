# Operations runbook

## Daily

- Open Overview: check pipeline health, source failures and attention list.
- Act only on verified, high-confidence items.
- Review in-app alerts; Telegram/SMTP delivery is optional.

## Weekly

- Read the weekly digest (Sunday 19:00 IST by default).
- Review unresolved eligibility items.
- Inspect stale/failing sources and dead jobs.
- Add or reject discovery candidates deliberately.

## Debug a source

1. Sources -> source detail -> recent runs.
2. Check `last_error_category`, redacted message, HTTP status and scan
   completeness.
3. Use **Preview** to fetch/parse without changing canonical records.
4. If the source changed shape, update the approved adapter config or disable
   it. Do not lower safety rules to "fix" parsing.

## Stuck or dead jobs

- Health -> Jobs shows queued/running/dead.
- Expired leases are recovered automatically.
- Retry safe dead jobs from the UI/API. Poison jobs remain visible.

## Backup

```bash
bash scripts/backup.sh
```

Creates `backups/discmon-YYYYmmddTHHMMSSZ.dump.gz`.

## Restore drill

```bash
# Creates discmon_restore and verifies core counts/decisions
bash scripts/restore.sh backups/discmon-....dump.gz discmon_restore
```

Never restore over the live database. Record the drill in the changelog.

## Notification failure

- Telegram missing: alerts remain in the in-app inbox with `pending` status.
- SMTP failure: retry with redacted errors; no duplicate dedup key.
- Sheets failure: `sync_outbox` retries; ingestion and UI are unaffected.

## Source failure vs closure

A network/HTTP failure never closes records. Only a complete successful board
scan increments absence counters. Three consecutive complete absences produce a
closure candidate; confirmation or a fourth absence produces confirmed closure.

## Incident: suspected secret exposure

Revoke the token at the provider, rotate `.env`, restart services, inspect audit
events and logs for redacted-only entries, then document the incident.
