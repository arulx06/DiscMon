# OpenCode: Build DiscMon from the attached system specification

I am providing `OPPORTUNITY_RADAR_IMPLEMENTATION_SPEC.md` as the **authoritative product and engineering specification**. Read it in full before writing application code. The project is a personal, self-hosted, one-user career intelligence platform for an India-based engineer who **is not a student** and is preparing to join IDFC FIRST Bank. It must surface rare, credible, high-upside opportunities early without stealing attention from engineering preparation.

## Operating directives

1. **Do not create a generic job board mockup.** The main requirement is a real source ingestion pipeline that monitors programmes and career opportunities, verifies eligibility, preserves evidence, identifies changes, and sends low-noise notifications.
2. **Use the chosen stack**: Next.js 16 + TypeScript + Tailwind/shadcn, FastAPI/Pydantic, PostgreSQL 18, SQLAlchemy/Alembic, APScheduler + PostgreSQL job queue, official ATS API adapters, RSS/Atom, GitHub API; integrate changedetection.io, optional RSSHub and compliant Scrapy/Playwright only in their specified phases.
3. **Do not use n8n or Huginn as the primary engine**, and do not add Redis, Celery, microservices, Kubernetes, a vector database, or a paid LLM dependency without my authorization.
4. **Don't assume ChatGPT Plus includes the OpenAI API or that a scraper can POST to a personal ChatGPT conversation.** Build a complete standalone dashboard/notification system, an evidence-grounded Copy for ChatGPT/export mechanism, and an optional Google Sheet mirror. Optional API-powered analysis should be disabled by default.
5. **Evidence and honesty are fundamental:** Never infer India eligibility from a remote flag alone; never label an unknown eligibility fact as verified; never equate equity/credits with cash salary; never invent a precise cutoff time from date-only deadlines; never claim a collector succeeded when it failed.
6. **Security/legal:** Respect public source access policies, site terms and robots; no authentication bypass, CAPTCHA evasion, stealth scraping or secret leakage; defend URL fetchers against SSRF; treat all source content as hostile data (prompt injection); keep admin UI private.
7. **Make the application usable after every milestone.** No "all done" claim until runnable tests and real fixture-backed extraction pass. No hardcoded fake opportunities in production UI. Sample data must be clearly fixture-only.
8. **Work incrementally with reproducible commits** if Git is available. At each phase, update `docs/changelog.md` with files changed, key decisions, commands run, test outcomes, unmet requirements and known defects.
9. **Produce real deliverables**: working source code, Docker Compose, DB migrations, tests, design-consistent mobile/desktop UI, `.env.example`, runbook, legal/source notes, source registry and acceptance test report. No placeholder integration pretending to fetch data.
10. **Avoid overengineering:** Implement a modular monolith, use PostgreSQL full-text and a SQL queue, make Redis/search/vector optional only after measured need. Ensure source adapters and AI providers are replaceable.

## Read, audit, plan, build

### First, inspect and report
- Read the full specification and list all mandatory P0 functional requirements and milestones M0–M7.
- Check the repository state, tooling, runtime and OS compatibility. If starting from an empty directory, create the specified repo structure.
- Check live documentation/versions for external APIs when possible. If network access is unavailable, write adapters from documented contracts but validate them with fixtures and clearly mark live verification pending.
- Produce `docs/implementation-plan.md`: architecture, ERD, endpoint map, phase order, risks, acceptance checklist and implementation strategy.
- Produce `docs/decisions/` ADRs for key decisions (Postgres queue, why no Redis, changedetection integration, ChatGPT boundary, auth/deployment).

### Next, implement the foundation and continue
- Complete **M0**, run its tests and produce a working `docker compose up` stack.
- Complete **M1** with a real schema and official public API adapters; run the exact repeated-collection idempotency tests.
- Complete **M2** eligibility gating, provenance, revisions, rule scoring and closure semantics.
- Complete **M3** functional responsive UI; verify both 360px and desktop E2E journeys.
- Complete **M4** notifications, digest, deadlines ICS and ChatGPT export.
- Then add **M5** (changedetection, GitHub, source exploration and optional Sheets mirror) and **M6** (hardening, backup restore and deployment).
- **M7** (LLM enrichment, search-provider integration, semantic features) is optional; do not require paid credentials for the MVP.

If work is interrupted, the next session must be able to continue from a concise `docs/PROGRESS.md` showing the last completed milestone, failing tests, exact commands and next steps. Do not ask me for information already specified in the document. Do not request any production credentials until the relevant integration can be tested locally without them.

## Critical tests that must pass before declaring the MVP ready

- Repeated Greenhouse/Lever/Ashby ingestion is idempotent; stable ATS IDs dedupe properly.
- Verified student-only or graduation-restricted roles are never recommended.
- `isRemote=true` without an India-country allowlist yields `unknown`, not `verified_yes`.
- Date-only deadline stores unknown cutoff time; no invented midnight/end-of-day.
- Changes to material fields create correct revisions; same material revision never re-alerts.
- Transient 403/429/error or failed full-board scan never marks opportunities closed.
- Two workers cannot claim a job or send a unique notification twice.
- Failed Sheet sync cannot block collection or corrupt the canonical database.
- On phone, owner can find, open, review, watch and ignore opportunities.
- Optional LLM disabled: core works correctly.
- Stale sources, failed jobs and backups are visible, not hidden.
- Back up DB and restore into clean environment; queries and ownership data match.

## Evaluation priority

**Correct data > credible coverage > operational reliability > minimal user attention > attractive UI > advanced AI features.** The system is for finding real opportunities early and supporting better decisions, not collecting as many scraped pages as possible.

Proceed with M0 immediately after making the implementation plan. Maintain the selected scope. If the entire project cannot be completed within one session, finish a runnable, tested vertical slice, write `docs/PROGRESS.md`, and state clearly what remains instead of giving a falsely complete status.
