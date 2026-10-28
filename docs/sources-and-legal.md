# Sources and legal notes

DiscMon only fetches public, permitted content. `source_registry_seed.yaml` is a
disabled candidate list, not proof of permission, active roles or eligibility.
Each source must pass review before it is enabled.

## Approval checklist

1. Confirm the URL is the official source or a clearly attributed public API.
2. Check robots.txt, terms, licence, rate limits and any stated API policy.
3. Record an officialness value and legal review status.
4. Prefer an official ATS API, then RSS/Atom, then approved static HTML.
5. Test a bounded preview and verify sample parsing.
6. Set a cadence no faster than allowed and enable deliberately.

## Adapter policy

| Adapter | Permitted scope |
|---|---|
| Greenhouse/Lever/Ashby | Public boards documented for public consumption |
| RSS/Atom | Published feeds; preserve attribution |
| GitHub | Public REST endpoints with an optional least-privilege token |
| static_html | Explicitly approved templates, bounded single pages |
| manual | Owner-submitted public URL, bounded fetch |
| changedetection | Trusted internal watcher for approved announcement pages |

No LinkedIn/Indeed scraping, login bypass, CAPTCHA solving, proxy rotation,
stealth plugins or credential harvesting. JS rendering is an explicit exception
and is not part of the MVP.

## Rate and failure behavior

Default per-host concurrency is 1, global workers 4, timeout 20 seconds, with
bounded exponential backoff and Retry-After support. 403/429/5xx and network
failures are failures, never evidence of absence. Per-source circuit breaker
opens after 5 consecutive failures and the health page shows it.

## Evidence retention

Raw full-page bodies are retained at most `RAW_RETENTION_DAYS` (default 30) and
only where storage and terms permit. Metadata, hashes, short excerpts and
decisions are retained longer. Source content is not redistributed; alerts link
to the primary source.

## changedetection.io

Optional. When enabled, the webhook only signals that a watch changed. The
worker then refetches the authoritative source through DiscMon's own compliant
client. A webhook is never treated as confirmed eligibility or a confirmed
opening. Webhooks require HMAC verification or an unguessable token on a private
network and have a maximum body size.

## RSSHub / Scrapy / Playwright

Not enabled in the MVP. Any future use requires a separate vetted route or
spider, bounded crawl and explicit owner approval. Unofficial feeds are not
primary evidence.
