# Task 6 — real non-ATS programme validation (2026-11-13)

## Result and boundary

**Completed in isolated test data; M5 remains PARTIAL.** One real official
programme was evaluated: [Wikimedia Outreachy](https://www.mediawiki.org/wiki/Outreachy),
discovered from [Wikimedia's outreach directory](https://www.mediawiki.org/wiki/Outreach_programs).
No second candidate was needed. This verifies an overview programme, not an
open application round or the user's eligibility to apply.

Exact accepted base: `9d5e95f7193cb86c9ca2947c8af69b01639abc4f`.
A clean derived feature branch was created at that commit. No production source,
database, backup, migration, deployment, notification, worker, scheduler, or
existing service was accessed or restarted. No real Sheets credentials or
Google API writes were used.

## Access and sample

The [fixture attribution/access notes](../services/api/tests/fixtures/wikimedia_outreachy/README.md)
link the robots file, robot policy, User-Agent policy, terms, original articles
and contributor histories. Policies and both articles returned HTTP 200. The
robot policy explicitly allows low-rate canonical article reads; robots permits
the two article paths and disallows Special:MyLanguage paths. A narrow discovery
selector selected only `a[href="/wiki/Outreachy"]`; no linked external sites,
historical round pages, special pages, scripts, images or browser execution
were followed. Live requests identified DiscMon with the project contact URL,
used normal gzip-capable HTTP, remained serial/low-rate, and retained SSRF/DNS
checks. Approval was simulated only inside the test database.

Only two article URLs were collected. Across the initial capture and same-database
validation retries there were ten article requests, including two conditional
304 responses. Earlier runs stopped on a genuine hostname allowlist error, then
on harness assertions incorrectly comparing the normalized-evidence hash to the
page hash and requiring `success` rather than `not_modified` for HTTP 304.
Those harness mistakes were corrected without replacing the database environment.
The final live run made exactly three HTTP reads: directory 200, programme 200,
programme 304. Fixture replay is not being represented as live access.

The 1.6 KB programme fixture preserves the nested MediaWiki heading, lead and
resource links; the directory fixture retains its repeated canonical anchors.
Scripts, images, language/edit controls, historic rounds and irrelevant page
content are removed. Fixture text is CC BY-SA 4.0 with attribution. The
[capture metadata](../services/api/tests/fixtures/wikimedia_outreachy/capture.json)
records dates, HTTP metadata, original decoded response hashes and separate
sanitized fixture hashes. No cookies or identifying request headers are saved.

Final live response metadata:

- Directory: HTTP 200; `text/html; charset=UTF-8`; Date
  `Fri, 13 Nov 2026 11:40:26 GMT`; Last-Modified
  `Fri, 30 Oct 2026 11:40:26 GMT`.
- Programme: HTTP 200 then 304; `text/html; charset=UTF-8`; Date
  `Fri, 13 Nov 2026 11:40:27 GMT`; Last-Modified
  `Fri, 30 Oct 2026 11:40:27 GMT`. No ETag was observed.
- Programme decoded response SHA-256:
  `66c2ac9ee62be589be1cba48ff0b7ee74e98cb660e6d8b1303d50cdf4a7d2f1a`.

## Isolation and actual workflow

A new standalone local PostgreSQL 16 cluster and `discmon_programme_test`
database were created, separate from all existing services. Before migrating
this empty test database, the existing `validate_test_environment` and
`validate_connected_database` guards checked effective settings, actual SQL
identity, client endpoint and resolved address:

```text
current_database = discmon_programme_test
current_user = session_user = task6
client host = hostaddr = 127.0.0.1; port = 55439
APP_ENV=test; DATABASE_URL and TEST_DATABASE_URL identical
Alembic: empty -> b76e2a98caca -> d4a7c1e9f210
```

The unchanged autouse guard repeated connection checks before each test's
TRUNCATE. The live drill used the existing services and in-process ASGI API
client, not a running API/worker/scheduler. It reviewed the actual discovered
candidate through GET, approved through the decision API and promoted through
the promotion API. The promoted source was initially **disabled**, approved at
the candidate level, and **legal-review-pending**. Direct ingestion failed while
disabled, and enabling before legal approval returned HTTP 400. Only then did
a test-only PATCH approve legal review and enable the source.

Identifiers from the successful live run (ephemeral test data only):

- directory source: `95724afc-d2ed-46e7-a029-fc6421e7a820`
- candidate: `fd9bf46c-18d1-4836-8e89-359066469807`
- promoted source: `107a2d1f-abed-4803-b32d-816fef6831ce`
- opportunity: `9863addb-f0bb-452a-8d10-7bb96b337829`
- revision: `34f00910-cc5e-4074-bb0a-00f586b1ca40`
- raw evidence: `c4d5bc81-b665-488e-82ca-768bd9b84ad7`
- assessment: `602e7c9e-d3c6-46c9-bfbf-311ccd02d989`
- outbox: `e0efef75-f722-40b8-b939-c59f6a0b8cb7`

## Stored facts and assessment

- Title `Outreachy` came from the real nested H1, not the source display name.
  Organization `Wikimedia` was explicit source configuration. Domain
  `mediawiki.org` was normalized from the URL.
- Primary URL, source-item URL, raw-evidence source URL and canonical URL all
  preserve `https://www.mediawiki.org/wiki/Outreachy`. Application URL is the
  existing article fallback, **not a verified application endpoint**.
- The real article calls it a three-month, full-time internship. Existing
  classification returned `mentorship` from its mentor resource link. This is
  a heuristic category, not field-level official confirmation. No adapter or
  broad classification architecture was added.
- Professional eligibility **unknown**; India eligibility
  **unknown**; no inferred country or remote permission. No
  compensation amount, publication date or application deadline was extracted.
  Deadline precision remains **unknown**, with no invented cutoff/timezone.
- Employment conflict **true**. Actual assessment: score **66**,
  hard gate **excluded**, bucket **excluded**. Reason:
  “Hard gate: programme requires full-time commitment or leaving current employment”. The score does not override the hard gate.
- RawEvidence retained source/run IDs, observation time, HTTP content type and
  Last-Modified, normalized DTO content/hash, original page hash in
  `source_payload.page_hash`, the full-time excerpt, and a test-only
  CC-BY-SA/robot-policy terms note. OpportunitySource referenced that evidence;
  the initial revision included its ID. Assessment evidence references retained
  URL, source ID, observation time, excerpt and normalized-content hash. The
  latter hash is intentionally different from the raw page hash.

## Repetition and fake Sheets

First ingest: **1 created, 0 updated**. Conditional live repeat: HTTP 304,
`not_modified`, **0 created, 0 updated**. Exactly **one canonical opportunity**
and **one material revision** remained. This live repeat verifies the conditional
path; full unchanged-body idempotency is additionally covered by the existing
PR #5 regression, which was rerun, not duplicated.

One pending Sheets outbox entry was processed through the existing fake gateway:
**1 synced, 1 append**, expected primary URL, gateway closed, outbox `synced`.
A second outbox pass synced **0** entries. After commits and clearing the ORM
identity map, the PostgreSQL opportunity and evidence reloaded successfully.
No Google gateway or credentials were constructed. The existing connected-flow
regression separately covers fake acknowledgement failure/retry without losing
PostgreSQL authority.

## Corrections and deterministic regression

Two source-exposed defects required small corrections:

1. Domain grouping removed `www`, but network allowlists compare exact hosts.
   Static HTML fetches and promotion/source-root validation therefore rejected
   this valid URL with `host_not_allowed`. Both now use the actual URL hostname;
   SSRF checks and exact-host restrictions remain unchanged.
2. Full-time conflict detection omitted “full-time internship”. Add that phrase
   and its space-separated spelling to the existing non-job detector.

Three focused tests use only the sanitized fixture/deterministic DNS: repeated
canonical directory links, source-structure/field-origin and full-time conflict
parsing, and exact `www` host handling through fetch and promotion validation.
The original synthetic discovery-to-Sheets regression is unchanged.

## Recorded verification

Commands ran from `services/api` in a temporary Python 3.12 virtualenv, with the
explicit matching test URLs and APP_ENV above. The temporary live-only harness
was removed before the deterministic full suite and is not collected in CI.

```text
pytest tests/test_wikimedia_outreachy.py -q  # before full-time correction
1 failed, 1 passed in 0.47s (employment_conflict was False)
pytest tests/test_wikimedia_outreachy.py tests/test_discovery_to_sheets.py -q
4 passed in 0.78s
pytest tests/_task6_live.py -q -s  # temporary live-only ASGI/service harness
1 passed in 3.88s
pytest tests -q
115 passed, 1 warning in 25.56s (existing feedparser deprecation)
ruff check app tests scripts
All checks passed!
mypy app scripts
Success: no issues found in 61 source files
git diff --check
exit 0
```

GitHub CI status is recorded on the review PR after publication; no unobserved
CI success is claimed here. M5 remains **PARTIAL**: real authenticated Sheets
delivery/reconciliation, live external notification delivery, production source
approval/legal review, and broader programme-field/round extraction remain
unverified. The broad article selector and heuristic category are known limits;
there is no claim of an open round or complete personal eligibility validation.
