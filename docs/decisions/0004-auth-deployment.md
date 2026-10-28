# ADR 0004: private single-owner access

## Status
Accepted.

## Context
The app contains personal decisions and administrative controls. It is not a
multi-tenant SaaS.

## Decision
Development allows disabled auth only on localhost. Hosted deployment uses a
server-side owner bearer token between Next.js and FastAPI and a private
tailnet (Tailscale Serve) for browser access. No owner token is exposed to the
browser. Strict CORS, security headers and audited mutations are required.

## Consequences
- Simple operation for one person.
- Public deployment requires an authenticated reverse proxy or the token mode.
- Multiuser accounts are out of scope.
