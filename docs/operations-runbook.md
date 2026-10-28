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

## Discovery

1. Open `/discover` and inspect candidate origin, URL, evidence and status.
2. Reject candidates that are aggregators, off-topic or legally unsuitable.
3. Approve deliberately, then promote an approved candidate to create a
   disabled source.
4. Review the new source's terms, adapter, URL and discovery config before
   enabling it. Promotion does not imply legal approval or enable scanning.
5. On a discovery-enabled source page, use **Scan for links** to run a bounded
   extraction. A scan failure is visible and must not be treated as zero links.

## Integration status

`/health` shows changedetection, Telegram, Email, Sheets and optional AI as
enabled or off. Off means unconfigured, not healthy. Check the card detail
before assuming delivery occurred:

- changedetection: base URL and webhook secret.
- Telegram: bot token and allowed chat ID.
- Email: SMTP host/credentials; TLS port 587.
- Sheets: spreadsheet ID, service-account file and tab.
- AI: no provider in rules-only mode.

## Changedetection signal

- The webhook accepts a valid HMAC and a timestamp within five minutes, limits
  body size and deduplicates the body hash.
- A signal only enqueues a bounded re-fetch from the approved source adapter.
- Never point changedetection at an unapproved or internal URL.
- Invalid signatures and stale timestamps are rejected; no canonical record is
  changed by the signal alone.

## Sheets mirror failure

- PostgreSQL remains authoritative.
- `sync_outbox` retries failures; ingestion and the UI must continue.
- Check `/health` for the last error and outbox counts.
- Fix credentials or sharing, then let the worker retry. Do not edit the sheet
  as a substitute for the database.

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

## Rescans and assessment history

A successful rescan appends an assessment row and does not create a duplicate
opportunity. Monitor `assessments` growth; retention or deduplication is still
an open decision. Material revisions alone may alert, once per channel, using
`opportunity_id + revision_id + channel + alert_kind`.

## Source failure vs closure

A network/HTTP failure never closes records. Only a complete successful board
scan increments absence counters. Three consecutive complete absences produce a
closure candidate; confirmation or a fourth absence produces confirmed closure.

## Incident: suspected secret exposure

Revoke the token at the provider, rotate `.env`, restart services, inspect audit
events and logs for redacted-only entries, then document the incident.
