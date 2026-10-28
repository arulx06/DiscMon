# DiscMon — OpenCode handoff package

Open `OPPORTUNITY_RADAR_IMPLEMENTATION_SPEC.md` for the full architecture, product requirements, data schema, UI design, REST API, test criteria and deployment plan.

Give `OPENCODE_BUILD_PROMPT.md` to OpenCode as the initial instruction, together with the specification. The `source_registry_seed.yaml` file is a **disabled, unverified candidate list** to import only after source checks. It must not be treated as permission to scrape or as proof of open opportunities.

Suggested use:
1. Create a new empty Git repository named `discmon`.
2. Copy these three files into the repository root (and optionally copy the specification to `docs/specification.md`).
3. Tell OpenCode to read `OPENCODE_BUILD_PROMPT.md` and use the full specification as its authority.
4. Make it deliver M0 to M4 as one working vertical slice, then add integrations.
5. Check `/health`, sources UI, real API source run, duplicate behavior, eligibility gates, backups and mobile display before trusting alerts.

**Important:** The existing personal ChatGPT daily/weekly tasks and native Google Sheet are not deployed by OpenCode and must not be recreated automatically. They may be connected only through explicitly authorized, supported interfaces.
