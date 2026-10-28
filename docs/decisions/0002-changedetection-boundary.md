# ADR 0002: changedetection.io is a signal, not evidence

## Status
Accepted (optional integration, M5).

## Context
Some approved programme pages lack APIs/feeds. changedetection.io can watch
them, but blindly trusting a webhook can create false openings and duplicate
pipelines.

## Decision
A verified webhook only enqueues a bounded re-fetch of the authoritative source
through DiscMon's own compliant client. The worker parses and records evidence.
One content owner per source; never monitor the same content twice.

## Consequences
- Slower but trustworthy confirmation.
- Webhook spoofing cannot create facts.
- The watcher remains outside the canonical data path.
