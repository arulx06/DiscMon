# Threat model

| Asset | Threat | Control |
|---|---|---|
| Owner records | Public exposure | Private network, no public Postgres/changedetection, owner-token API |
| Secrets | Leakage in logs/bundle | Server-only env, redaction, no token in client code |
| Fetcher | SSRF to metadata/private services | HTTPS-only, DNS/IP deny-list, redirect revalidation, per-source host allowlist |
| Source text | Prompt injection / XSS | Treated as data; no LLM in MVP; HTML sanitized/escaped; CSP |
| Webhook | Spoofed change signal | HMAC or unguessable token, body limit, re-fetch from source |
| Queue | Duplicate claim/alert | `FOR UPDATE SKIP LOCKED`, unique dedup key, lease recovery |
| Data | False closure | Completeness flag and 3-successful-absence gate |
| Sheets | Mirror blocking core | Transactional outbox, isolated retries, DB canonical |
| Exports | Accidental secret inclusion | Public opportunity fields only, redacted errors |
| Supply chain | Compromised dependency | Pinned ranges/lockfiles, CI audit, non-root containers |

## Trust boundaries

- Browser -> Next.js server: same-origin, no owner secret in browser.
- Next.js server -> FastAPI: private network plus owner bearer token.
- Worker -> external source: untrusted network; all bytes untrusted.
- Worker -> changedetection: trusted internal service on a private network.
- Worker -> Telegram/SMTP/Sheets: outbound optional integrations.

## Abuse resistance rules

- Never execute shell commands, HTML or prompts from source content.
- Reject non-HTTPS source URLs except explicitly local test mode.
- Reject loopback, private, link-local, multicast, reserved and cloud metadata
  addresses before connection and after every redirect.
- Limit response size, content type, timeout and redirect count.
- Redact tokens and credentials in errors.
- Optional AI cannot change eligibility flags, hard gates or send messages.
