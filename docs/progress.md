# Progress

Current milestone: Stage 9 streaming and release operations. The hosted React/FastAPI
app uses serverless Cosmos DB, Event Hubs ingestion, Web PubSub revision delivery
and Blob checkpoints through managed identities. Live checks cover duplicate
replay, correction/withdrawal history, frozen evidence and replica replacement.
Protected GitHub OIDC deployment is verified. Direct Azure Monitor numeric
telemetry is retained and live-verified; see the latest entry below.
The USD 75 total trial budget remains unchanged. Hosting is in East US; Cosmos
uses East US 2 after East US account creation was rejected for regional capacity.
Resolved identifiers remain in ignored local configuration.

Stage 8's scoped local detector, generator and recap path remains complete,
including one live Azure acceptance of bounded Microsoft Agent Framework recap
adaptation. The hosted model path remains off. Full-match coverage and broader
player attribution remain extensions. Stage 10 measured evaluation and the final
Microsoft-platform architecture review are the next work. After each task, report
the result and best next move.

The fixture declares Eastbridge 0–1 Northport at 48:00 and ten events through
48:55. Independent expectations identify e04 as the only Eastbridge high recovery,
with one versus zero across its two short windows. Replay now calculates these
counts and pass totals/distances from the events. The new interface displays the
eligible count-comparison insight and its exact source records.

The separate ten-minute positive and control fixtures now contain 89 events each.
Hand-written expectations and offline tests confirm one versus four and one
versus one high recoveries respectively, using `(48:00,53:00]` and `(53:00,58:00]`.
Tests also check ball location and player possession continuity. Four fault files
cover an unknown player, invalid coordinates, duplicate delivery and a correction.
See `docs/fixtures.md` for the complete review and limitations.

The in-memory replay journal now deduplicates source records, rejects conflicts,
selects the highest available revisions and rebuilds state at historical cutoffs.
The virtual clock supports play/pause/reset and speed changes. Positive and control
console reports reproduce the expected counts and source IDs; correction and
late-delivery checks pass. See `docs/replay.md` for commands and limits.

The React TypeScript screen now includes the scoreboard, replay controls, factual
card, SVG recovery markers and source evidence panel. The snapshot API creates
frozen evidence from actual calculated values and references. Tests confirm that
source changes update the card/evidence together, the control has no increase
card, and earlier cutoffs cannot expose later evidence. Browser captures are in
`docs/screenshots/`; see `docs/interface.md` for startup and behavior.

SQLite now retains the append-only source journal and versioned evidence. Restart
recovery does not depend on seed fixture files. Atomic correction ingestion produces
create/update/withdraw messages, and the client retains tombstone revisions within
each playback scope. Seeking creates a fresh scope without changing producer
history. See `docs/history.md` for the storage and availability contract.

Stage 6 now includes the single-call Azure structured-output adapter, approved
wording validation, a total deadline, expiry and an atomic evidence-version check
before commit. Attempts are audited in SQLite; the original factual card remains
the fallback. The bounded workflow is documented in `docs/workflow.md`;
the first single-call increment remains documented in `docs/adaptation.md`.

Stage 7 audience variants and the Stage 8 increments are documented below.
Best next move: Stage 10 measured evaluation and the final demonstration, followed
by the as-built architecture and separately labelled Microsoft extension proposals. Never request API
keys in chat. Do not claim cloud restart recovery from local SQLite storage.

User direction, 16 October 2026: creatively use Microsoft platforms where they
add real product value. After completing the build plan, deliver an as-built
architecture diagram and a separately labelled proposal for additional Microsoft
capabilities. Explain each addition's user benefit, integration, operational cost
and demo value; verify current product capabilities against official sources.
Distinguish deployed and verified components from local adapters and proposals.
Notify the user before Azure setup or resource decisions require their action.
Current Microsoft use is the live-verified Azure OpenAI adapter and bounded
Microsoft Agent Framework recovery and recap workflows; GitHub Actions provides protected-branch CI.
Application hosting is deployed on Azure Container Apps with private ACR images
and managed-identity pulls. Cosmos DB shared history is deployed and restart-verified;
Event Hubs and Web PubSub are deployed and live-verified. GitHub Actions uses
protected OIDC releases; direct numeric Azure Monitor retention is live-verified.

## Verification recorded on 15 October 2026

Environment: CPython 3.13.9, FastAPI 0.143.1, Pydantic 2.14.1; exact dependencies
are recorded in `uv.lock`. Commands ran from the repository root.

```console
$ UV_CACHE_DIR=.uv-cache uv sync --locked
Resolved 24 packages in 15ms
Checked 23 packages in 2ms

$ UV_CACHE_DIR=.uv-cache uv run --frozen python -m counterpress.fixture fixtures/tiny_possession.json
VALID: tiny-eastbridge-northport | 10 synthetic events | pitch 105 x 68 m
Event IDs: e01, e02, e03, e04, e05, e06, e07, e08, e09, e10

$ UV_CACHE_DIR=.uv-cache uv run --frozen pytest -q
...................................                                      [100%]
35 passed in 0.20s
```

Started the actual server with:

```sh
UV_CACHE_DIR=.uv-cache uv run --frozen uvicorn counterpress.api.main:app --host 127.0.0.1 --port 8000
```

Startup reported `Application startup complete.` and
`Uvicorn running on http://127.0.0.1:8000`. A separate terminal returned:

```console
$ curl --fail --silent --show-error http://127.0.0.1:8000/health
{"status":"ok","service":"counterpress"}
```

Dependency downloads and the live local HTTP check required execution outside
the restricted sandbox. Fixture validation and all 35 automated checks passed
inside it. Test durations can vary between runs.

## Stage 2 verification recorded on 15 October 2026

```console
$ UV_CACHE_DIR=.uv-cache uv run --frozen pytest -q
...........................................                              [100%]
43 passed in 0.21s
```

Added `fixtures/recovery_increase.json`, `fixtures/recovery_control.json`, four
files under `fixtures/faults/`, `tests/expected_recovery_scenarios.json`,
`tests/expected_faults.json`, `tests/test_scenario_fixtures.py`, and
`docs/fixtures.md`. Updated the fixture validator's wording, README and this
progress record. No dependencies or application endpoints changed.

## Stage 3 verification recorded on 15 October 2026

```console
$ UV_CACHE_DIR=.uv-cache uv run --frozen pytest -q
........................................................................ [ 91%]
.......                                                                  [100%]
79 passed in 0.44s

$ UV_CACHE_DIR=.uv-cache uv run --frozen python -m counterpress.replay fixtures/recovery_increase.json --speed 60
eastbridge-northport-recovery-increase | 58:00 | 89 canonical events
Score: Eastbridge 0, Northport 1 | Possession: eastbridge
eastbridge: passes 17/24 | attempted pass distance 322.17 m | high recoveries 5
northport: passes 20/20 | attempted pass distance 240.93 m | high recoveries 0
Baseline (48:00, 53:00]: 1 | p043@r1
Current (53:00, 58:00]: 4 | p053@r1, p064@r1, p075@r1, p086@r1
Count increase: yes (location/count fact only)
```

The control report returned one versus one with no increase. A 54:00 report had
53 canonical events and an explicit incomplete-window message. The tiny correction
report returned zero qualifying recoveries at 49:00. These console checks ran
successfully using the commands in `docs/replay.md`.

Added `domain/replay.py`, `domain/metrics.py`, `clock.py`, and `replay.py` inside
`backend/counterpress`; added `tests/test_replay.py`,
`tests/expected_tiny_metrics.json`, and `docs/replay.md`. Updated domain models,
the fixture module's InitialState import, README, contract/fixture documentation
and this progress record. Dependencies and HTTP endpoints are unchanged.

## Stage 4 verification recorded on 15 October 2026

```console
$ UV_CACHE_DIR=.uv-cache uv run --frozen pytest -q
........................................................................ [ 80%]
..................                                                       [100%]
90 passed in 0.58s

$ npm --prefix frontend test
> counterpress-frontend@0.1.0 test
> vitest run

 RUN  v3.2.7 /Users/haydn/Documents/CounterPress/frontend
 ✓ src/App.test.tsx (5 tests) 507ms

 Test Files  1 passed (1)
      Tests  5 passed (5)
   Start at  14:00:09
   Duration  1.25s (transform 64ms, setup 0ms, collect 169ms, tests 507ms, environment 353ms, prepare 43ms)

$ npm --prefix frontend run build
> counterpress-frontend@0.1.0 build
> tsc --noEmit && vite build

vite v7.3.7 building client environment for production...
transforming...
✓ 34 modules transformed.
rendering chunks...
computing gzip size...
dist/index.html                   0.53 kB │ gzip:  0.35 kB
dist/assets/index-Yhe1Cqun.css   14.32 kB │ gzip:  4.04 kB
dist/assets/index-Cj-yiUkW.js   239.29 kB │ gzip: 74.37 kB
✓ built in 394ms
```

Test and build durations vary between runs.

Real Chrome checks through the Vite proxy verified the initial 48:00 state,
the 1-to-4 card at 58:00, all five evidence rows and a full raw source record,
control suppression, switching/reset behavior, 53 known events with no card at
54:00, and real playback from 54:00 through 58:00 at 60×. The browser error log
was empty. The 390 × 844 viewport check preserved the layout and horizontally
scrollable evidence table; the temporary viewport override was reset afterward.

Saved actual browser captures: `stage4-evidence.jpg`, `stage4-control.jpg`,
`stage4-54min.jpg`, and `stage4-mobile.jpg` under `docs/screenshots/`. The in-app
browser was unavailable, so visual checks used a new Chrome tab. Local preview
servers were stopped after verification; startup instructions are in the README.

Files added:

- `backend/counterpress/api/snapshots.py`
- `tests/test_snapshot_api.py`
- `frontend/package.json`, `frontend/package-lock.json`, `frontend/tsconfig.json`,
  `frontend/vite.config.ts`, `frontend/index.html`
- `frontend/src/App.tsx`, `frontend/src/main.tsx`, `frontend/src/styles.css`,
  `frontend/src/types.ts`, `frontend/src/api.ts`, `frontend/src/InsightCard.tsx`,
  `frontend/src/Pitch.tsx`, `frontend/src/EvidencePanel.tsx`, `frontend/src/App.test.tsx`
- `docs/interface.md` and the four screenshot files above

Files updated: `backend/counterpress/api/main.py`,
`backend/counterpress/domain/models.py`, `.gitignore`, `README.md`,
`docs/contracts.md`, and `docs/progress.md`. Python dependencies and authored
match fixtures are unchanged. Frontend dependencies are locked for reproducible installation.

## Stage 5 verification recorded on 15 October 2026

```console
$ UV_CACHE_DIR=.uv-cache uv run --frozen pytest -q
........................................................................ [ 70%]
..............................                                           [100%]
102 passed in 1.46s

$ npm --prefix frontend test
> counterpress-frontend@0.1.0 test
> vitest run

 RUN  v3.2.7 /Users/haydn/Documents/CounterPress/frontend
 ✓ src/App.test.tsx (8 tests) 777ms
   ✓ the local replay screen > opens the exact evidence records and hides them on reset, then replays again  313ms

 Test Files  1 passed (1)
      Tests  8 passed (8)
   Start at  14:45:03
   Duration  1.74s (transform 67ms, setup 0ms, collect 174ms, tests 777ms, environment 504ms, prepare 69ms)

$ npm --prefix frontend run build
> counterpress-frontend@0.1.0 build
> tsc --noEmit && vite build

vite v7.3.7 building client environment for production...
transforming...
✓ 35 modules transformed.
rendering chunks...
computing gzip size...
dist/index.html                   0.53 kB │ gzip:  0.35 kB
dist/assets/index-Yhe1Cqun.css   14.32 kB │ gzip:  4.04 kB
dist/assets/index-CVcZVXQ6.js   240.28 kB │ gzip: 74.76 kB
✓ built in 493ms

$ UV_CACHE_DIR=.uv-cache uv run --frozen python -m counterpress.ingest increase fixtures/faults/recovery_corrections.json --db var/stage5-verification.sqlite3
Stored 4 new records; history version 93
58:05 | update r2 | 1 -> 3 | evidence v2
58:10 | withdraw r3 | 1 -> 1 | evidence v3
58:15 | create r4 | 1 -> 2 | evidence v4

$ UV_CACHE_DIR=.uv-cache uv run --frozen python -m counterpress.ingest increase fixtures/faults/recovery_corrections.json --db var/stage5-verification.sqlite3
Stored 0 new records; history version 93
```

The first CLI invocation used a fresh database; the second was a separate process
against the same persisted file. Test/build durations vary. Database files and
build outputs are ignored, not source deliverables.

Real browser verification used:

```sh
COUNTERPRESS_DB_PATH=var/stage5-verification.sqlite3 UV_CACHE_DIR=.uv-cache uv run --frozen uvicorn counterpress.api.main:app --host 127.0.0.1 --port 8000
npm --prefix frontend run dev -- --host 127.0.0.1
```

Chrome showed the original 1-to-4 card at 58:00, withdrawal with no recovery markers
at 58:10, and the new 1-to-2 card at 58:15. Its evidence table showed p043 r1, p053 r3
and p086 r1. Rewinding to 58:00 restored the original five supporting events and
1-to-4 card. The browser error log was empty. Captures are
`docs/screenshots/stage5-withdrawal.jpg` and `stage5-restored-evidence.jpg`.
The temporary local servers were stopped after verification.

Files added:

- `backend/counterpress/history.py`
- `backend/counterpress/ingest.py`
- `fixtures/faults/recovery_corrections.json`
- `tests/test_history.py`
- `frontend/src/playbackScope.ts`
- `docs/history.md`
- `docs/screenshots/stage5-withdrawal.jpg`
- `docs/screenshots/stage5-restored-evidence.jpg`

Files updated:

- `backend/counterpress/api/main.py`
- `backend/counterpress/api/snapshots.py`
- `backend/counterpress/domain/replay.py` (journal documentation only)
- `tests/test_snapshot_api.py`
- `frontend/src/App.tsx`, `frontend/src/App.test.tsx`, `frontend/src/api.ts`, `frontend/src/types.ts`
- `.gitignore`, `README.md`, `docs/contracts.md`, `docs/replay.md`, `docs/interface.md`, `docs/progress.md`

No dependencies, original possession fixtures or independently authored prior
oracles changed. This milestone adds no model calls, agent workflow or cloud resources.

## Stage 6 first increment: offline verification on 15 October 2026

Implemented one explicitly invoked Azure structured-output request, approved-template
validation, an eight-second total deadline, sixty-second expiry, sanitized SQLite
audit records and an atomic evidence-version check before commit. The browser uses
accepted wording only for matching, unexpired evidence and otherwise keeps the
original factual explanation. No Analyst/Producer agents were added.

```console
$ UV_CACHE_DIR=.uv-cache uv run --frozen pytest -q
........................................................................ [ 52%]
..................................................................       [100%]
138 passed in 1.25s

$ npm --prefix frontend test
> counterpress-frontend@0.1.0 test
> vitest run

 RUN  v3.2.7 /Users/haydn/Documents/CounterPress/frontend
 ✓ src/App.test.tsx (9 tests) 696ms
   ✓ the local replay screen > opens the exact evidence records and hides them on reset, then replays again  301ms

 Test Files  1 passed (1)
      Tests  9 passed (9)
   Start at  14:54:51
   Duration  1.59s (transform 69ms, setup 0ms, collect 174ms, tests 696ms, environment 414ms, prepare 50ms)

$ npm --prefix frontend run build
> counterpress-frontend@0.1.0 build
> tsc --noEmit && vite build

vite v7.3.7 building client environment for production...
transforming...
✓ 35 modules transformed.
rendering chunks...
computing gzip size...
dist/index.html                   0.53 kB │ gzip:  0.35 kB
dist/assets/index-Yhe1Cqun.css   14.32 kB │ gzip:  4.04 kB
dist/assets/index-3fcGzfuL.js   240.62 kB │ gzip: 74.89 kB
✓ built in 495ms

$ env -u AZURE_OPENAI_ENDPOINT -u AZURE_OPENAI_DEPLOYMENT -u AZURE_OPENAI_API_KEY UV_CACHE_DIR=.uv-cache uv run --frozen python -m counterpress.adapt increase --db var/stage6-offline-verification.sqlite3
{
  "attempt_id": "adapt-1bf2b03a-05a6-420f-871f-7d11dce80010",
  "status": "unconfigured",
  "evidence_id": "ev-428caa9cdc25d7c20d43e8ba",
  "evidence_version": 1,
  "requested_at": {
    "period": 2,
    "elapsed_ms": 780000
  },
  "deployment": null,
  "prompt_version": "recovery-wording-v1",
  "started_at_unix_ms": 1792047393585,
  "expires_at_unix_ms": 1792047453585,
  "duration_ms": 4,
  "provider_requests": 0,
  "reason": "azure_not_configured",
  "text": null
}
```

The last command correctly exited 2. Its local audit database is ignored. Test
runtimes, attempt IDs and wall-clock timestamps vary. Dependencies were synchronized
using `uv lock --offline` and `uv sync --locked --offline`; httpx 0.28.1 moved from
the test group to runtime dependencies without changing its locked version.

The HTTP adapter was exercised through httpx MockTransport, never a real Azure
endpoint. Tests prove accepted wording, rejected facts/prose, refusal, timeout,
expiry, HTTP errors, no retries, concurrent correction and stale-result rejection.
A live deployment's authentication, quota and structured-output compatibility have
not been verified. This is an offline-complete increment with a pending live check,
not completion of all Stage 6.

Files added:

- `backend/counterpress/adaptation/__init__.py`
- `backend/counterpress/adaptation/contracts.py`
- `backend/counterpress/adaptation/azure.py`
- `backend/counterpress/adaptation/service.py`
- `backend/counterpress/adapt.py`
- `tests/test_adaptation.py`
- `.env.example`
- `docs/adaptation.md`

Files updated:

- `backend/counterpress/history.py`
- `backend/counterpress/api/snapshots.py`
- `frontend/src/App.tsx`, `frontend/src/App.test.tsx`, `frontend/src/InsightCard.tsx`, `frontend/src/types.ts`
- `pyproject.toml`, `uv.lock`
- `README.md`, `docs/history.md`, `docs/interface.md`, `docs/progress.md`

No seed fixtures or prior expected results changed. No cloud resources, agent
workflow, procedural generator or new personalization modes were introduced.

## Stage 6 live Azure verification on 15 October 2026

The user configured Azure locally and explicitly requested a live test. Configuration
validation confirmed that endpoint, deployment and key were present without printing
their values. The latest eligible comparison was evidence version 1 at 58:00.

Exactly one provider request was made:

```console
$ UV_CACHE_DIR=.uv-cache uv run --env-file .env --frozen python -m counterpress.adapt increase --at-ms 780000
{
  "attempt_id": "adapt-cabecc5d-04ac-49ab-935c-36d28ba6a94d",
  "status": "accepted",
  "evidence_id": "ev-428caa9cdc25d7c20d43e8ba",
  "evidence_version": 1,
  "requested_at": {
    "period": 2,
    "elapsed_ms": 780000
  },
  "deployment": "REDACTED-DEPLOYMENT",
  "prompt_version": "recovery-wording-v1",
  "started_at_unix_ms": 1792051420154,
  "expires_at_unix_ms": 1792051480154,
  "duration_ms": 3170,
  "provider_requests": 1,
  "reason": "validated_approved_wording",
  "text": "Eastbridge: 4 high recoveries in 53:00–58:00, compared with 1 in 48:00–53:00."
}
```

The command exited zero. A separate Python process created a fresh FastAPI app
against the same SQLite file and checked the actual snapshot route through
httpx ASGITransport before the wording expired. Its assertions returned:

```text
PASS: restarted API reads accepted adaptation from SQLite
PASS: wording matches evidence version 1; authoritative counts remain 1 and 4
PASS: no adaptation appears at the earlier 54:00 playback position
```

That local verification made no additional provider requests. The accepted wording
retains its normal sixty-second expiry; the durable audit record remains afterward.
This verifies the configured deployment's authentication and structured-output
compatibility for one request, not sustained latency or quota capacity. Earlier
offline tests cover rejection, timeout, expiry and stale-result behavior.

Documentation updated: `README.md`, `docs/adaptation.md`, `docs/progress.md`.
The live attempt was appended to the ignored local SQLite database. No application
code, credentials or cloud resources were changed.


## Stage 6 bounded Analyst/Producer workflow — 15 October 2026

Implemented the Microsoft Agent Framework graph with explicit Azure configuration,
three read-only tools, validated accept/narrow/reject decisions and a fresh Producer
handoff. Application guards enforce three Analyst requests, three individual tool
invocations, one Producer request, four total provider requests and a shared
eight-second deadline. Retries and redirects are disabled. The journal is checked
before handoff and atomically before publication; no transaction spans a model
request. Durable audit records include evidence references, deployment, prompt
version, counters, elapsed action timestamps and duration. The replay screen shows
short action labels and retains its existing factual fallback and expiry behavior.

Final backend verification (exact command and final output line):

```console
$ UV_CACHE_DIR=.uv-cache uv run --frozen pytest -q
164 passed in 2.19s
```

Frontend verification (exact commands and output):

```console
$ npm --prefix frontend test

> counterpress-frontend@0.1.0 test
> vitest run

 RUN  v3.2.7 /Users/haydn/Documents/CounterPress/frontend

 ✓ src/WorkflowActivity.test.tsx (2 tests) 79ms
 ✓ src/App.test.tsx (9 tests) 619ms

 Test Files  2 passed (2)
      Tests  11 passed (11)
   Start at  16:27:50
   Duration  1.35s (transform 92ms, setup 0ms, collect 270ms, tests 698ms, environment 721ms, prepare 81ms)

$ npm --prefix frontend run build

> counterpress-frontend@0.1.0 build
> tsc --noEmit && vite build

vite v7.3.7 building client environment for production...
transforming...
✓ 36 modules transformed.
rendering chunks...
computing gzip size...
dist/index.html                   0.53 kB │ gzip:  0.36 kB
dist/assets/index-CKpc-_FN.css   14.73 kB │ gzip:  4.15 kB
dist/assets/index-CP1lkZRI.js   240.94 kB │ gzip: 74.99 kB
✓ built in 384ms
```

The 26 workflow tests exercise the actual framework and SDK with mocked HTTP:
acceptance, narrowing, rejection, missing tool evidence, unsupported facts or
prose, a fourth tool blocked within one batch, bounded event sequence, repeated
model calls, pre-invocation deadline checks, compressed responses, timeout
cancellation, provider errors without retries, expiry, restart, append-only audit,
and corrections during Analyst and Producer requests. The correction tests also
read match metrics and commit a withdrawal while the request is pending.
The existing 138 backend tests continue to pass.

Two live workflow invocations used the existing configured `REDACTED-DEPLOYMENT`
deployment. The first timed out during the Producer request at 8,014 ms, after
three provider invocations and two tools. It published no model wording and kept
the factual fallback. The Producer package was then reduced to the fresh packet,
source references, metric definition, coordinate convention and required facts;
it does not need full source-event bodies. The second invocation succeeded with
the same eight-second limit. This is a successful sample, not a latency guarantee.

Successful live command and complete sanitized output:

```console
$ UV_CACHE_DIR=.uv-cache uv run --env-file .env --frozen python -m counterpress.workflow increase --at-ms 780000
{
  "attempt_id": "workflow-bdfb5305-3a61-41bd-b18d-bc1532953144",
  "status": "accepted",
  "candidate": "recovery_increase",
  "evidence_id": "ev-428caa9cdc25d7c20d43e8ba",
  "evidence_version": 1,
  "evidence_references": [
    {
      "event_id": "p043",
      "revision": 1
    },
    {
      "event_id": "p053",
      "revision": 1
    },
    {
      "event_id": "p064",
      "revision": 1
    },
    {
      "event_id": "p075",
      "revision": 1
    },
    {
      "event_id": "p086",
      "revision": 1
    }
  ],
  "requested_at": {
    "period": 2,
    "elapsed_ms": 780000
  },
  "available_at": {
    "period": 2,
    "elapsed_ms": 780000
  },
  "source_history_version": 89,
  "deployment": "REDACTED-DEPLOYMENT",
  "prompt_version": "analyst-producer-v1",
  "started_at_unix_ms": 1792052956734,
  "expires_at_unix_ms": 1792053016734,
  "duration_ms": 6929,
  "analyst_requests": 2,
  "producer_requests": 1,
  "provider_requests": 3,
  "tool_invocations": 2,
  "actions": [
    {
      "label": "Requested comparison",
      "elapsed_ms": 2960
    },
    {
      "label": "Checked data quality",
      "elapsed_ms": 2960
    },
    {
      "label": "Accepted supported comparison",
      "elapsed_ms": 4407
    },
    {
      "label": "Prepared explanation",
      "elapsed_ms": 6916
    }
  ],
  "reason": "supported_count_comparison",
  "text": "Eastbridge: 4 high recoveries in 53:00–58:00, compared with 1 in 48:00–53:00."
}
```

Exit code: 0. The earlier timeout exited 2. Both complete audit records are saved
in `docs/verification/workflow-live-accepted.json` and
`docs/verification/workflow-live-timeout.json`. No credentials or endpoint values
are included. A separate local process opened the same SQLite database, checked
that the accepted workflow and wording appeared before expiry, checked unchanged
1-to-4 facts, and checked that 54:00 hid the later workflow. Output:

```text
PASS: persisted live workflow is visible before expiry; facts remain 1 to 4; earlier replay hides the workflow.
```

Files added:

- `backend/counterpress/workflow/__init__.py`
- `backend/counterpress/workflow/__main__.py`
- `backend/counterpress/workflow/contracts.py`
- `backend/counterpress/workflow/budget.py`
- `backend/counterpress/workflow/service.py`
- `tests/test_workflow.py`
- `frontend/src/WorkflowActivity.tsx`
- `frontend/src/WorkflowActivity.test.tsx`
- `docs/workflow.md`
- `docs/verification/workflow-live-accepted.json`
- `docs/verification/workflow-live-timeout.json`

Files updated:

- `backend/counterpress/history.py`
- `backend/counterpress/api/snapshots.py`
- `frontend/src/App.tsx`, `frontend/src/types.ts`, `frontend/src/styles.css`
- `pyproject.toml`, `uv.lock`
- `README.md`, `docs/adaptation.md`, `docs/progress.md`

Live attempts were appended to the ignored local SQLite database. No credentials,
seed fixtures or independent expected results changed. No new Azure resources
were created. The interface remains local; audience modes, procedural generation
and Azure application deployment remain subsequent stages.

Best next move: Stage 7 audience preferences and explanation styles, preserving
all evidence, freshness and factual validation checks. The existing Azure model
deployment is sufficient to begin; no additional Azure action is needed now.


## Stage 7 personalization and languages — 15 October 2026

Added analyst and casual presentations of the same eligible insight, English and
Simplified Chinese approved templates, local viewer profiles, registered club and
player preferences, metric focus and a zero-or-one card budget. Player selection
uses the actual recovery actor and preserves the authoritative team comparison.
At 58:00, selecting eb09 shows p064 and sequence p063/p064/p065; selecting eb04
shows no qualifying contribution. Analyst mode adds sample counts and canonical
context; casual mode presents one count graphic and a short explanation.

Variants are cached by insight identity/revision, language, depth and perspective
in a bounded process-local LRU. Corrections invalidate old variants, while
historically valid replay remains available without repopulating the current
cache. Each viewer, preference and seek change establishes a fresh browser scope;
the client also checks returned preferences and variant identity.

This stage uses approved bilingual templates over validated facts and makes no
Azure calls. The earlier general-English model adaptation remains separately
available and audited. Only the existing recovery detector supplies stories;
club and metric preferences affect priority but cannot create a passing or
opponent story. No fixture, source contract, dependency or Azure resource changed.

Exact final verification commands and output:

```console
$ UV_CACHE_DIR=.uv-cache uv run --frozen pytest -q
........................................................................ [ 40%]
........................................................................ [ 81%]
.................................                                        [100%]
177 passed in 3.16s

$ npm --prefix frontend test

> counterpress-frontend@0.1.0 test
> vitest run

 RUN  v3.2.7 /Users/haydn/Documents/CounterPress/frontend

 ✓ src/api.test.ts (2 tests) 3ms
 ✓ src/WorkflowActivity.test.tsx (2 tests) 100ms
 ✓ src/App.test.tsx (12 tests) 1026ms

 Test Files  3 passed (3)
      Tests  16 passed (16)
   Start at  16:45:40
   Duration  2.08s (transform 218ms, setup 0ms, collect 491ms, tests 1.13s, environment 1.34s, prepare 171ms)

$ npm --prefix frontend run build

> counterpress-frontend@0.1.0 build
> tsc --noEmit && vite build

vite v7.3.7 building client environment for production...
transforming...
✓ 38 modules transformed.
rendering chunks...
computing gzip size...
dist/index.html                   0.53 kB │ gzip:  0.36 kB
dist/assets/index-Bkfb8XF_.css   16.42 kB │ gzip:  4.52 kB
dist/assets/index-DR4WpExT.js   249.65 kB │ gzip: 78.48 kB
✓ built in 441ms
```

The 13 new backend cases cover language/depth fact agreement, actual player
contributions, honest empty states, ranking and budget eligibility, cache reuse
and capacity, immediate correction invalidation, historical cache isolation,
invalid preference values and separate API scopes. Five new frontend cases cover
mode/language and evidence switching, budget/empty states, a delayed response
across viewer changes, explicit preference requests and rejected mismatched
perspectives. All earlier tests still pass.

Chrome walkthrough against the local API and Vite server confirmed the original
1-to-4 comparison, the p064 marker for eb09, the simplified Chinese casual view,
unchanged names/windows/uncertainty, and analyst sequence context. Review caught
and fixed a Chinese heading wrapping issue and dark-theme contrast in the new
controls and activity display. The two screenshots are saved below. The test tab
and both local servers were closed after verification.

Files added:

- `backend/counterpress/audience.py`
- `tests/test_audience.py`
- `frontend/src/AudienceControls.tsx`
- `frontend/src/EventSequence.tsx`
- `frontend/src/api.test.ts`
- `docs/audience.md`
- `docs/screenshots/audience-analyst-en.png`
- `docs/screenshots/audience-casual-zh.png`

Files updated:

- `backend/counterpress/api/main.py`
- `backend/counterpress/api/snapshots.py`
- `frontend/src/App.tsx`, `frontend/src/App.test.tsx`
- `frontend/src/InsightCard.tsx`, `frontend/src/Pitch.tsx`, `frontend/src/EvidencePanel.tsx`
- `frontend/src/WorkflowActivity.tsx`, `frontend/src/api.ts`, `frontend/src/types.ts`, `frontend/src/styles.css`
- `README.md`, `docs/workflow.md`, `docs/progress.md`

Best next move: start Stage 8 with the seeded procedural match generator and
held-out positive/negative controls before adding more detectors or recaps.
No Azure setup is needed for that local generation work.

## Stage 8 seeded generator — first increment, 15 October 2026

Added a seeded conditional possession state machine to the existing Event
contract. Passes, carries, duels, open-play recoveries and restarts preserve ball
and player continuity. Hidden pressure, directness, flank and escape settings
change probabilities without guaranteeing an outcome. Stable match/event IDs,
revision 1, delivery sequence, occurrence order and availability times reuse the
existing replay and evidence pipeline. Unfinished boundary episodes remain pending.

The export separates public feeds from private evaluator configurations, labels,
hashes and split assignments. The fixed suite has 36 development and six held-out
whole segments with disjoint seeds and paired team-setting combinations. Holdout
checks cover structural validity only. Four independent development controls
cover successful pressure, unsuccessful pressure, no change and rising recovery
counts without successful pressure challenges. A separate seed-59 regression
covers a pending challenge at the final cutoff.

Exact verification commands and output, run from the repository root:

```console
$ UV_CACHE_DIR=.uv-cache uv run --frozen pytest -q tests/test_generator.py
...........................................................              [100%]
59 passed in 0.44s

$ UV_CACHE_DIR=.uv-cache uv run --frozen pytest -q
........................................................................ [ 30%]
........................................................................ [ 61%]
........................................................................ [ 91%]
....................                                                     [100%]
236 passed in 2.57s

$ UV_CACHE_DIR=.uv-cache uv run --frozen python -m counterpress.generator --seed 2 --profile pressure-shift --output var/generated-stage8-demo
single: 1 matches | 112 events
Feed: var/generated-stage8-demo/feeds/sim-cd3f34e3015e1cec5197fe8c.json
Evaluator-only metadata: var/generated-stage8-demo/evaluation
VALID: Event v1 feeds; hidden settings, seeds and outcome labels excluded from feeds.

$ UV_CACHE_DIR=.uv-cache uv run --frozen python -m counterpress.generator --suite --output var/generated-stage8-suite
development: 36 matches | 4085 events
holdout: 6 matches | 659 events
Evaluator-only metadata: var/generated-stage8-suite/evaluation
VALID: Event v1 feeds; hidden settings, seeds and outcome labels excluded from feeds.

$ UV_CACHE_DIR=.uv-cache uv run --frozen python -m counterpress.replay var/generated-stage8-demo/feeds/sim-cd3f34e3015e1cec5197fe8c.json
sim-cd3f34e3015e1cec5197fe8c | 58:00 | 112 canonical events
Score: Eastbridge 0, Northport 1 | Possession: northport
eastbridge: passes 17/25 | attempted pass distance 305.92 m | high recoveries 4
northport: passes 19/24 | attempted pass distance 260.18 m | high recoveries 1
Baseline (48:00, 53:00]: 1 | g0031@r1
Current (53:00, 58:00]: 3 | g0087@r1, g0097@r1, g0107@r1
Count increase: yes (location/count fact only)

$ UV_CACHE_DIR=.uv-cache uv run --frozen python -m counterpress.replay var/generated-stage8-suite/feeds/sim-dbe085e7da766da19d73ef4c.json
sim-dbe085e7da766da19d73ef4c | 58:00 | 111 canonical events
Score: Eastbridge 0, Northport 1 | Possession: eastbridge
eastbridge: passes 21/29 | attempted pass distance 333.48 m | high recoveries 0
northport: passes 20/29 | attempted pass distance 417.29 m | high recoveries 4
Baseline (48:00, 53:00]: 0 | none
Current (53:00, 58:00]: 0 | none
Count increase: no (location/count fact only)
```

The 59 new tests include independent geometry/holder audits across all 42 suite
runs, invalid configurations, reproducibility without global random state,
before-change prefix agreement, meaningful frozen controls, disjoint splits,
label/source consistency, pending resolution, export rollback/overwrite refusal,
and generated-feed persistence with valid evidence and audience presentation.
No frontend file changed, so frontend checks were not repeated in this increment.

Files added:

- `backend/counterpress/generator/__init__.py`
- `backend/counterpress/generator/models.py`
- `backend/counterpress/generator/engine.py`
- `backend/counterpress/generator/suite.py`
- `backend/counterpress/generator/__main__.py`
- `tests/test_generator.py`
- `tests/expected_generator_controls.json`
- `docs/generator.md`

Files updated: `README.md`, `docs/progress.md`.
CLI verification artifacts are in ignored `var/generated-stage8-demo/` and
`var/generated-stage8-suite/`. No existing fixture, Event contract, dependency,
frontend, credential or Azure resource changed.

This completes the generator increment, not all of Stage 8. The simulator covers
a ten-minute segment with fixed teams and score; its heuristics are not calibrated
to real matches. Generated feeds currently use the CLI rather than the browser
scenario selector. See [the generator guide](generator.md) for operation and limits.

Best next move: pressure-exposure and defensive build-up-escape detection with
fully observed episodes, per-window sample requirements, boundary exclusions,
pending episodes, positive/negative controls and cooldowns. Recaps follow later.
No Azure action is needed for this next local detector increment.

## Stage 8 pressure/escape detector — second increment, 15 October 2026

Added observed defensive-third build-up episodes and two rate comparisons:
duel-proxy pressure exposure and controlled escape among exposed episodes.
Fully observed starts and resolutions must both lie inside each `(start,end]`
window. Reports disclose boundary exclusions, initial left-censoring and pending
episodes. Each metric requires three denominator episodes in each window and a
25-percentage-point change. A 60-second cooldown is scoped to match/team/metric;
same-window corrections bypass it. Publication receipts are caller-owned and
the CLI can read them from JSON.

The detector uses canonical public events, not generator settings or labels.
Typed evidence includes complete source revisions, episode references, fractions,
policy, decisions and a content fingerprint. Correcting a duel into a carry
removes that exposure and can make a previous claim ineligible. Earlier cutoffs
retain the earlier evidence; late resolutions remain pending until available.
Review also caught and fixed a challenger-perspective issue: challenging for
possession cannot start a build-up episode before control is established.

Two hand-authored, independently reviewed controls contain six episodes per
window. The positive changes exposure from 3/6 to 6/6 and pressured escape from
3/3 to 1/6. The meaningful negative has actual pressure, escapes and turnovers
but holds exposure at 3/6 and pressured escape at 2/3 in both windows.

Exact final backend verification:

```console
$ UV_CACHE_DIR=.uv-cache uv run --frozen pytest -q
........................................................................ [ 26%]
........................................................................ [ 52%]
........................................................................ [ 79%]
.........................................................                [100%]
273 passed in 2.86s
```

Exact CLI commands and output:

```console
$ UV_CACHE_DIR=.uv-cache uv run --frozen python -m counterpress.pressure fixtures/pressure/increase.json --windows 48:00 49:00 50:00
build-up-increase | eastbridge | observed-build-up-v1
Baseline: completed=6; exposed=3; escaped_under_pressure=3; boundary_excluded=0; left_censored=0; pending=0
Current: completed=6; exposed=6; escaped_under_pressure=1; boundary_excluded=0; left_censored=0; pending=0
pressure_exposure: 3/6 -> 6/6 | +50.0 pp | eligible (increase)
pressured_escape: 3/3 -> 1/6 | -83.3 pp | eligible (decrease)
Evidence SHA-256: 47b2b047f9d3c47b6d49de7703337f8d968153494da07ba7519723b32ae6482b
Pressure exposure is a defensive-third duel proxy, not tracking-measured pressure. Escape means observed controlled progression beyond x=35 m. Rates describe fully observed episodes, not causal tactical effectiveness.

$ UV_CACHE_DIR=.uv-cache uv run --frozen python -m counterpress.pressure fixtures/pressure/control.json --windows 48:00 49:00 50:00
build-up-control | eastbridge | observed-build-up-v1
Baseline: completed=6; exposed=3; escaped_under_pressure=2; boundary_excluded=0; left_censored=0; pending=0
Current: completed=6; exposed=3; escaped_under_pressure=2; boundary_excluded=0; left_censored=0; pending=0
pressure_exposure: 3/6 -> 3/6 | +0.0 pp | below_threshold (unchanged)
pressured_escape: 2/3 -> 2/3 | +0.0 pp | below_threshold (unchanged)
Evidence SHA-256: 19f00ddd282f05e2f231f10f0cd2d88e0d8cafd62f322958cd02863124d64e48
Pressure exposure is a defensive-third duel proxy, not tracking-measured pressure. Escape means observed controlled progression beyond x=35 m. Rates describe fully observed episodes, not causal tactical effectiveness.

$ UV_CACHE_DIR=.uv-cache uv run --frozen python -m counterpress.pressure var/generated-stage8-demo/feeds/sim-cd3f34e3015e1cec5197fe8c.json --team northport
sim-cd3f34e3015e1cec5197fe8c | northport | observed-build-up-v1
Baseline: completed=3; exposed=2; escaped_under_pressure=1; boundary_excluded=0; left_censored=1; pending=0
Current: completed=3; exposed=3; escaped_under_pressure=0; boundary_excluded=0; left_censored=0; pending=1
pressure_exposure: 2/3 -> 3/3 | +33.3 pp | eligible (increase)
pressured_escape: 1/2 -> 0/3 | -50.0 pp | insufficient_sample (decrease)
Evidence SHA-256: 4255d28200de43148307a9d47e798db8840c75e46ffb6e6750e762631c0b3ad8
Pressure exposure is a defensive-third duel proxy, not tracking-measured pressure. Escape means observed controlled progression beyond x=35 m. Rates describe fully observed episodes, not causal tactical effectiveness.
```

Exact JSON export and typed reload:

```sh
UV_CACHE_DIR=.uv-cache uv run --frozen python -m counterpress.pressure fixtures/pressure/increase.json --windows 48:00 49:00 50:00 --json > var/pressure-evidence.json
UV_CACHE_DIR=.uv-cache uv run --frozen python - <<'PY'
from pathlib import Path
from counterpress.domain.pressure import PressureEvidence
packet = PressureEvidence.model_validate_json(Path('var/pressure-evidence.json').read_text())
print(f'VALID: {len(packet.episodes)} episodes | {len(packet.records)} canonical source records | {packet.fingerprint}')
PY
```

```text
VALID: 12 episodes | 63 canonical source records | 47b2b047f9d3c47b6d49de7703337f8d968153494da07ba7519723b32ae6482b
```

The 37 new tests cover independent control expectations and geometry, exact time
and pitch boundaries, observed re-entry, challenger perspective, repeated duels,
restart resolutions, left-censoring, pending endings, per-window/per-metric sample
requirements, zero denominators, threshold and cooldown decisions, future and
same-window receipts, correction invalidation, late resolution, generated public
feeds and malformed policies/evidence. No held-out detector tuning was performed.

Files added:

- `backend/counterpress/domain/pressure.py`
- `backend/counterpress/pressure.py`
- `fixtures/pressure/increase.json`
- `fixtures/pressure/control.json`
- `tests/test_pressure.py`
- `tests/expected_pressure.json`
- `docs/pressure.md`

Files updated: `README.md`, `docs/generator.md`, `docs/progress.md`.
Ignored verification output: `var/pressure-evidence.json`.

This completes the local detector/evidence increment. No Event contract,
dependency, existing recovery publication, frontend or Azure resource changed.
Frontend tests were not repeated because this increment has no frontend changes.
The proxy cannot measure unrecorded pressure or establish tactical causality;
thresholds are synthetic-demo eligibility rules. See [the pressure guide](pressure.md).

Best next move: integrate this evidence into the durable insight ledger and replay
screen with create/update/withdraw behavior and audience handling, before adding
another detector. Recaps and Azure application deployment remain later stages.
No Azure action is needed for the next integration increment.

## Stage 8 durable pressure cards — third increment, 15 October 2026

Connected pressure and escape evidence to independent append-only SQLite
publication streams and the replay UI. Each metric has a stable comparison ID,
its own revision counter, create/update/withdraw operations, frozen source
evidence and prior-version invalidations. Additive tables and a source checkpoint
backfill existing histories without rewriting recovery or source records.

Snapshots expose pressure lifecycle tombstones and a selected pressure view.
Recovery and pressure candidates share the zero-or-one display budget, with
club/player/metric priority and deterministic ties. Pressure views use fresh
English/Simplified Chinese templates for analyst/casual audiences. Player
selection highlights recorded involvement and leaves team-rate denominators
unchanged. The client validates perspective and source revision and retains
separate tombstone watermarks for every pressure story.

The new Pressure and escape shift/control scenarios scale the reviewed
two-minute controls to the screen's ten-minute windows. Their event outcomes and
coordinates are unchanged. Cards show fractions and percentages; evidence expands
to sample/exclusion counts, episode classifications, pressure refs and raw source
revisions. The original recovery cards and workflow remain compatible.

Exact final backend command and output:

```console
$ UV_CACHE_DIR=.uv-cache uv run --frozen pytest -q
........................................................................ [ 25%]
........................................................................ [ 50%]
........................................................................ [ 76%]
....................................................................     [100%]
284 passed in 3.16s
```

Exact frontend commands and output:

```console
$ npm --prefix frontend test

> counterpress-frontend@0.1.0 test
> vitest run

 RUN  v3.2.7 /Users/haydn/Documents/CounterPress/frontend

 ✓ src/api.test.ts (3 tests) 6ms
 ✓ src/WorkflowActivity.test.tsx (2 tests) 94ms
 ✓ src/PressureCard.test.tsx (3 tests) 280ms
 ✓ src/App.test.tsx (12 tests) 1041ms
   ✓ the local replay screen > opens the exact evidence records and hides them on reset, then replays again  342ms

 Test Files  4 passed (4)
      Tests  20 passed (20)
   Start at  17:46:29
   Duration  1.92s (transform 208ms, setup 0ms, collect 627ms, tests 1.42s, environment 1.81s, prepare 214ms)

$ npm --prefix frontend run build

> counterpress-frontend@0.1.0 build
> tsc --noEmit && vite build

vite v7.3.7 building client environment for production...
transforming...
✓ 39 modules transformed.
rendering chunks...
computing gzip size...
dist/index.html                   0.53 kB │ gzip:  0.35 kB
dist/assets/index-DuEt4Cep.css   17.60 kB │ gzip:  4.76 kB
dist/assets/index-CMoPuTjK.js   256.91 kB │ gzip: 80.38 kB
✓ built in 437ms
```

The 11 new backend cases cover independent lifecycle revisions, atomic correction
rejection, restart durability, legacy backfill/idempotency, version/cutoff-scoped
evidence, bilingual/player views, viewer isolation and cross-metric card ranking.
Four new frontend cases cover episode/source inspection, translated fractions,
separate tombstones, missing/stale stream rejection, visible withdrawal/recreation
and mismatched narrative identity/preferences. The catalog expectation was updated
for the two new replay scenarios; all earlier tests still pass.

Chrome walkthrough used separate verification history. Local servers were started
with these commands after the sandbox denied localhost binding; automatic review
approved running them outside the sandbox:

```sh
COUNTERPRESS_DB_PATH=var/pressure-ui-verification.sqlite3 UV_CACHE_DIR=.uv-cache uv run --frozen uvicorn counterpress.api.main:app --host 127.0.0.1 --port 8000
npm --prefix frontend run dev -- --host 127.0.0.1
```

Exact correction command and output during the browser walkthrough:

```console
$ UV_CACHE_DIR=.uv-cache uv run --frozen python -m counterpress.ingest pressure-increase fixtures/pressure/replay_corrections.json --db var/pressure-ui-verification.sqlite3
Stored 10 new records; history version 73
58:05 | eastbridge pressure_exposure | update r2 | 2/6 -> 6/6 | eligible
58:05 | eastbridge pressured_escape | withdraw r2 | 2/2 -> 1/6 | insufficient_sample
58:10 | eastbridge pressure_exposure | withdraw r3 | 2/6 -> 2/6 | below_threshold
58:15 | eastbridge pressure_exposure | create r4 | 3/6 -> 6/6 | eligible
58:15 | eastbridge pressured_escape | create r3 | 3/3 -> 1/6 | eligible
```

Browser review confirmed the 50%→100% exposure card, sample/exclusion table,
Chinese casual 100%→16.7% escape card, unchanged score, correction-horizon discovery
without moving the paused viewer, withdrawal at 58:10, restoration at 58:15 and
the negative control's no-eligible-rate-change state. The temporary tab and both
servers were closed. Screenshots are linked in [the publication guide](pressure-publication.md).

Files added:

- `backend/counterpress/pressure_publications.py`
- `backend/counterpress/pressure_views.py`
- `fixtures/pressure/replay_corrections.json`
- `tests/test_pressure_history.py`
- `frontend/src/PressureCard.tsx`
- `frontend/src/PressureCard.test.tsx`
- `docs/pressure-publication.md`
- `docs/screenshots/pressure-evidence-en.png`
- `docs/screenshots/pressure-casual-zh.png`

Files updated:

- `backend/counterpress/history.py`, `backend/counterpress/api/snapshots.py`
- `backend/counterpress/api/main.py`, `backend/counterpress/audience.py`, `backend/counterpress/ingest.py`
- `tests/test_snapshot_api.py`
- `frontend/src/App.tsx`, `frontend/src/AudienceControls.tsx`, `frontend/src/types.ts`
- `frontend/src/api.ts`, `frontend/src/api.test.ts`, `frontend/src/playbackScope.ts`, `frontend/src/styles.css`
- `README.md`, `docs/pressure.md`, `docs/generator.md`, `docs/audience.md`, `docs/progress.md`

The separate verification database is ignored under `var/`. No dependency,
Event contract, original control fixture, Azure resource or credential changed.
Pressure wording is deterministic; the Azure workflow still targets recovery
stories only. Pressure remains a duel-based proxy rather than tracking-measured
pressure, and the rate changes do not establish tactical causality.

Best next move: add possession-without-progression detection with independent
positive/negative episode controls and the same durable evidence lifecycle.
Player-contribution expansion and recaps follow later. No Azure action is needed
for the next local detector increment.

## Stage 8 fourth increment — possession without progression

Implemented the `sustained-possession-v1` rule, independent positive/negative
controls and durable bilingual replay cards. The positive comparison is 1/6→4/6;
the negative stays 1/6→1/6. Maximum observed forward gain distinguishes a team
that advances then returns from a team that never advances. Eligibility requires
three completed actions over an observed span of at least 20 seconds; incomplete
pass destinations and delayed opponent recoveries cannot manufacture progression
or sustain the observed span. Full rules and limitations: [progression guide](progression.md).

Exact verification commands and output:

```console
$ UV_CACHE_DIR=.uv-cache uv run --frozen pytest -q
........................................................................ [ 23%]
........................................................................ [ 46%]
........................................................................ [ 69%]
........................................................................ [ 92%]
.........................                                                [100%]
313 passed in 9.06s

$ npm --prefix frontend test

> counterpress-frontend@0.1.0 test
> vitest run

 RUN  v3.2.7 /Users/haydn/Documents/CounterPress/frontend

 ✓ src/api.test.ts (3 tests) 16ms
 ✓ src/WorkflowActivity.test.tsx (2 tests) 261ms
 ✓ src/PressureCard.test.tsx (5 tests) 918ms
   ✓ opens episode classifications and exact source revisions while retaining the rate denominators  328ms
 ✓ src/App.test.tsx (12 tests) 2020ms
   ✓ the local replay screen > opens the exact evidence records and hides them on reset, then replays again  749ms
   ✓ the local replay screen > shows no increase card for the control and no future evidence after a seek  302ms

 Test Files  4 passed (4)
      Tests  22 passed (22)
   Start at  18:04:36
   Duration  4.14s (transform 650ms, setup 0ms, collect 1.68s, tests 3.21s, environment 3.87s, prepare 791ms)

$ npm --prefix frontend run build

> counterpress-frontend@0.1.0 build
> tsc --noEmit && vite build

vite v7.3.7 building client environment for production...
transforming...
✓ 39 modules transformed.
rendering chunks...
computing gzip size...
dist/index.html                   0.53 kB │ gzip:  0.35 kB
dist/assets/index-3c30FPTv.css   17.64 kB │ gzip:  4.77 kB
dist/assets/index-Dfuf-TqP.js   258.57 kB │ gzip: 80.89 kB
✓ built in 656ms

$ UV_CACHE_DIR=.uv-cache uv run --frozen python -m counterpress.progression fixtures/progression/increase.json
possession-increase | eastbridge | sustained-possession-v1
Baseline: 1/6 without progression | boundary=0; unknown_start=0; pending=0; brief=0; limited_space=0
Current: 4/6 without progression | boundary=0; unknown_start=0; pending=0; brief=0; limited_space=0
eligible (increase) | +50.0 pp
Sustained possessions without 15 m of observed forward gain; a spatial proxy, not possession dominance, passing quality or tactical value.

$ UV_CACHE_DIR=.uv-cache uv run --frozen python -m counterpress.progression fixtures/progression/control.json
possession-control | eastbridge | sustained-possession-v1
Baseline: 1/6 without progression | boundary=0; unknown_start=0; pending=0; brief=0; limited_space=0
Current: 1/6 without progression | boundary=0; unknown_start=0; pending=0; brief=0; limited_space=0
below_threshold (unchanged) | +0.0 pp
Sustained possessions without 15 m of observed forward gain; a spatial proxy, not possession dominance, passing quality or tactical value.
```

The 29 new backend cases cover independent controls and continuity, exact
15 m/20 second/window boundaries, brief/near-goal/unknown-start/pending exclusions,
incomplete passes and loose-ball delays, sample sufficiency, cooldown scope,
late availability, evidence consistency, durable lifecycle corrections, restart
without fixtures, idempotence, old SQLite schema migration, bilingual/player views
and historical cutoff safety. Two new frontend cases cover progression evidence
and scenario selection. Browser review found a clipped table header; allowing
header wrapping fixed it, and the final build above includes that CSS change.

The browser walkthrough used an isolated database and these server commands:

```sh
COUNTERPRESS_DB_PATH=var/progression-ui-verification.sqlite3 UV_CACHE_DIR=.uv-cache uv run --frozen uvicorn counterpress.api.main:app --host 127.0.0.1 --port 8000
npm --prefix frontend run dev -- --host 127.0.0.1
```

Exact ingestion command and output during browser review:

```console
$ UV_CACHE_DIR=.uv-cache uv run --frozen python -m counterpress.ingest progression-increase fixtures/progression/replay_corrections.json --db var/progression-ui-verification.sqlite3
Stored 12 new records; history version 96
58:05 | eastbridge possession_without_progression | update r2 | 1/6 -> 3/6 | eligible
58:10 | eastbridge possession_without_progression | withdraw r3 | 1/6 -> 1/6 | below_threshold
58:15 | eastbridge possession_without_progression | create r4 | 1/6 -> 4/6 | eligible
```

Chrome confirmed the 16.7%→66.7% card, complete exclusion table, an episode's
10 m gain/three actions/22-second span, exact source revisions, Chinese casual
wording, paused historical evidence after ingest, withdrawal at 58:10 and restored
1/6→4/6 at 58:15. The tab and both servers were closed. Screenshot:
[English progression evidence](screenshots/progression-evidence-en.png).

Files added:

- `backend/counterpress/domain/progression.py`
- `backend/counterpress/progression.py`
- `fixtures/progression/increase.json`
- `fixtures/progression/control.json`
- `fixtures/progression/replay_corrections.json`
- `tests/expected_progression.json`
- `tests/test_progression.py`
- `docs/progression.md`
- `docs/screenshots/progression-evidence-en.png`

Files updated:

- `backend/counterpress/domain/pressure.py`
- `backend/counterpress/pressure_publications.py`, `backend/counterpress/pressure_views.py`
- `backend/counterpress/history.py`, `backend/counterpress/api/snapshots.py`
- `backend/counterpress/api/main.py`, `backend/counterpress/audience.py`
- `tests/test_snapshot_api.py`
- `frontend/src/types.ts`, `frontend/src/App.tsx`, `frontend/src/AudienceControls.tsx`
- `frontend/src/PressureCard.tsx`, `frontend/src/PressureCard.test.tsx`, `frontend/src/styles.css`
- `README.md`, `docs/progress.md`, `docs/pressure-publication.md`, `docs/audience.md`

The ignored verification database is under `var/`. No dependency, Event contract,
existing control fixture, Azure resource or credential changed. The new detector
shares the existing episode publication API compatibility names and one-card
budget; its metric-specific evidence and labels remain distinct. Older databases
receive an additive rules-version checkpoint and progression backfill without
rewriting established pressure publications.

Best next move: player-contribution detector expansion with independent controls
and evidence-linked attribution, then recaps. Current player preferences indicate
source involvement only. No Azure action is needed for that next local increment;
application deployment and broader model adaptation remain later work.

## Stage 8 fifth increment — player high-recovery contribution detector

Implemented an actor-attributed share comparison using only canonical high-recovery
records. Both independent controls keep team totals at four per window. The
positive assigns `eb04` one then three recoveries; the negative assigns one then
one. `eb09` wins all preceding duels and receives no recovery attribution. Counts
and shares must both rise; shrinking denominators alone cannot qualify. Defaults
require three team recoveries in each window, three current player recoveries,
a count increase of two and a share increase of 25 percentage points.

The CLI exposes the typed evidence and configurable subject/windows/cutoff. A new
API route reads persisted source history, including actor revisions, without a
new database table or changes to existing story publication. Evidence validation
checks actor attribution, denominators, policy decisions and source availability.
The separate guide documents equal-duration windows, roster/membership checks,
undefined shares, missing minutes-played information and descriptive limitations:
[contribution guide](contributions.md).

Exact local verification command and output:

```console
$ UV_CACHE_DIR=.uv-cache uv run --frozen pytest -q
........................................................................ [ 20%]
........................................................................ [ 41%]
........................................................................ [ 61%]
........................................................................ [ 82%]
..............................................................           [100%]
350 passed in 5.69s

$ UV_CACHE_DIR=.uv-cache uv run --frozen python -m counterpress.contributions fixtures/contributions/increase.json --player eb04
player-recoveries-increase | eastbridge/eb04 | player-high-recoveries-v1
Baseline: 1/4 team high recoveries | share=25.0%
Current: 3/4 team high recoveries | share=75.0%
eligible | player count +2 | share +50.0 pp
Recorded open-play high recoveries attributed only to the recovering actor. Shares are not a player rating, per-minute rate, or evidence of tactical causality.

$ UV_CACHE_DIR=.uv-cache uv run --frozen python -m counterpress.contributions fixtures/contributions/control.json --player eb04
player-recoveries-control | eastbridge/eb04 | player-high-recoveries-v1
Baseline: 1/4 team high recoveries | share=25.0%
Current: 1/4 team high recoveries | share=25.0%
below_threshold | player count +0 | share +0.0 pp
Recorded open-play high recoveries attributed only to the recovering actor. Shares are not a player rating, per-minute rate, or evidence of tactical causality.

$ UV_CACHE_DIR=.uv-cache uv run --frozen python -m counterpress.contributions fixtures/contributions/increase.json --player eb04 --updates fixtures/contributions/actor_corrections.json --at 58:10
player-recoveries-increase | eastbridge/eb04 | player-high-recoveries-v1
Baseline: 1/4 team high recoveries | share=25.0%
Current: 1/4 team high recoveries | share=25.0%
below_threshold | player count +0 | share +0.0 pp
Recorded open-play high recoveries attributed only to the recovering actor. Shares are not a player rating, per-minute rate, or evidence of tactical causality.
```

The 37 new test cases cover independent actor partitions and continuity, duel/
recipient exclusions, exact threshold/window boundaries, denominator shrinkage,
zero samples, invalid membership/policy/windows, forged evidence, actor corrections,
late availability, idempotent retransmission, historical API cutoffs, restart without
fixtures and CLI output/error handling. Existing 313 backend cases continue to pass.
No frontend code changed; the required GitHub Actions frontend job still runs
its tests and production build for this pull request.

Files added:

- `backend/counterpress/domain/contributions.py`
- `backend/counterpress/contributions.py`
- `fixtures/contributions/increase.json`
- `fixtures/contributions/control.json`
- `fixtures/contributions/actor_corrections.json`
- `tests/expected_contributions.json`
- `tests/test_contributions.py`
- `docs/contributions.md`

Files updated:

- `backend/counterpress/api/main.py`
- `backend/counterpress/api/snapshots.py`
- `README.md`
- `docs/progress.md`

Best next move: durable player-contribution publications and bilingual replay cards,
with actor-correction withdrawal/restoration and player-scoped cooldowns. The current
increment returns candidate evidence through CLI/API; it does not publish a player
story or change the existing viewer-card budget. Recaps and broader attribution
rules follow later. No dependencies, Azure resources, keys or endpoints changed.

## Stage 8 sixth increment — durable player-contribution cards

Added independent player publication streams, a source-count checkpoint and
historical backfill for existing SQLite files. Stable identity includes match,
team, player, metric, rule version and window pair. A 60-second cooldown scopes new
comparisons to the same player/team/match/rule; corrections to an existing comparison
always bypass it. Source and publication writes remain one atomic transaction.

The replay catalog now includes the original positive/negative contribution controls.
English and Simplified Chinese cards expose player counts, full team denominators,
source actor/revision attribution, thresholds and historical provenance. Contribution
stories share the one-card budget with recovery and pressure. Player preferences
select the actual subject, while stale/missing lifecycle streams and mismatched
narratives are rejected by the client. See [publication details](contribution-publication.md).

Exact local verification commands and output:

```console
$ UV_CACHE_DIR=.uv-cache uv run --frozen pytest -q
........................................................................ [ 19%]
........................................................................ [ 39%]
........................................................................ [ 58%]
........................................................................ [ 78%]
........................................................................ [ 97%]
........                                                                 [100%]
368 passed in 6.61s

$ npm --prefix frontend test

> counterpress-frontend@0.1.0 test
> vitest run

 RUN  v3.2.7 /Users/haydn/Documents/CounterPress/frontend

 ✓ src/api.test.ts (4 tests) 8ms
 ✓ src/WorkflowActivity.test.tsx (2 tests) 91ms
 ✓ src/PressureCard.test.tsx (5 tests) 419ms
 ✓ src/ContributionCard.test.tsx (4 tests) 672ms
   ✓ player choice, card budget, language, viewers and negative control keep their own presentation  343ms
 ✓ src/App.test.tsx (12 tests) 1078ms
   ✓ the local replay screen > opens the exact evidence records and hides them on reset, then replays again  340ms

 Test Files  5 passed (5)
      Tests  27 passed (27)
   Start at  10:42:02
   Duration  2.11s (transform 370ms, setup 0ms, collect 1.03s, tests 2.27s, environment 2.71s, prepare 318ms)

$ npm --prefix frontend run build

> counterpress-frontend@0.1.0 build
> tsc --noEmit && vite build

vite v7.3.7 building client environment for production...
transforming...
✓ 40 modules transformed.
rendering chunks...
computing gzip size...
dist/index.html                   0.53 kB │ gzip:  0.35 kB
dist/assets/index-3c30FPTv.css   17.64 kB │ gzip:  4.77 kB
dist/assets/index-BQ6rlB6o.js   265.02 kB │ gzip: 81.94 kB
✓ built in 419ms
```

The 18 new backend cases cover durable update/withdraw/restore, idempotence,
restart without fixtures, frozen evidence ID/version/cutoff scope, bilingual views,
player filtering, zero-card budget, independent controls, old-schema backfill,
atomic rejection, publication consistency, player/team/match cooldown isolation,
exact expiry, correction bypass and cross-metric ranking. Five new frontend cases
cover source attribution and denominator evidence, translations, independent
revision watermarks, stale/missing streams, visible withdrawal/restoration, player/
viewer/budget behavior, negative controls and invalid API narratives.

The Chrome review used a separate ignored SQLite database. Local server commands:

```sh
COUNTERPRESS_DB_PATH=var/contribution-ui-verification.sqlite3 UV_CACHE_DIR=.uv-cache uv run --frozen uvicorn counterpress.api.main:app --host 127.0.0.1 --port 8000
npm --prefix frontend run dev -- --host 127.0.0.1
```

Exact correction command and output:

```console
$ UV_CACHE_DIR=.uv-cache uv run --frozen python -m counterpress.ingest contribution-increase fixtures/contributions/publication_corrections.json --db var/contribution-ui-verification.sqlite3
Stored 16 new records; history version 64
58:02 | eastbridge/eb04 player_high_recovery_share | update r2 | 1/4 -> 3/4 | eligible
58:05 | eastbridge/eb04 player_high_recovery_share | withdraw r3 | 1/4 -> 2/4 | below_threshold
58:15 | eastbridge/eb04 player_high_recovery_share | create r4 | 1/4 -> 3/4 | eligible
```

Browser review confirmed the 25%→75% card, the four-source team denominator in
both windows, actor attribution labels, Chinese casual wording, no credit for the
duel winner, paused historical evidence after ingestion, revised `b1-recovery@r2`
at 58:02, withdrawal at 58:05, restoration at 58:15 and the negative control's empty
state. It caught a selected-player withdrawal label showing the generic empty
state; the UI now shows that player's withdrawal while other players keep their
own empty state, with regression coverage. The temporary tab and both servers
were closed. Screenshot: [player evidence](screenshots/contribution-evidence-en.png).

Files added:

- `backend/counterpress/contribution_publications.py`
- `backend/counterpress/contribution_views.py`
- `fixtures/contributions/publication_corrections.json`
- `tests/test_contribution_history.py`
- `frontend/src/ContributionCard.tsx`
- `frontend/src/ContributionCard.test.tsx`
- `docs/contribution-publication.md`
- `docs/screenshots/contribution-evidence-en.png`

Files updated:

- `backend/counterpress/history.py`, `backend/counterpress/api/snapshots.py`
- `backend/counterpress/api/main.py`, `backend/counterpress/audience.py`, `backend/counterpress/ingest.py`
- `tests/test_snapshot_api.py`
- `frontend/src/App.tsx`, `frontend/src/AudienceControls.tsx`, `frontend/src/types.ts`
- `frontend/src/api.ts`, `frontend/src/api.test.ts`, `frontend/src/playbackScope.ts`
- `README.md`, `docs/contributions.md`, `docs/audience.md`, `docs/progress.md`

The independent actor controls, detector thresholds, Event contract and dependencies
are unchanged. No Azure resources, credentials or model calls are needed. Existing
Azure wording/workflow remains specific to recovery stories. Best next move:
evidence-linked match recaps composed from available published stories and exact
revisions. Broader attribution rules and Azure deployment remain later work.

## Stage 8 seventh increment — factual segment recaps, 16 October 2026

The snapshot now includes a bounded recap of current eligible publications at its
cutoff. It selects latest revisions before filtering withdrawals, ranks using the
existing preferences, and carries exact citation identities and revisions. The
collapsed bilingual UI opens each frozen evidence revision and follows snapshot
scope, revision watermarks and the card budget. See `docs/recaps.md`.

The independent expectations cover pressure 3/6 → 6/6 and escape 3/3 → 1/6,
player recovery share 1/4 → 3/4, recovery 1 → 4, corrections without number changes,
withdrawal/restoration, historical rewind after restart, detector controls,
per-statement citation resolution, bounded deterministic selection and malformed
release contracts. Browser checks confirmed both languages and no warning/error
console entries. Initial visual review exposed a light-background contrast issue;
the final styles use the existing dark theme. The frontend test fixture was also
corrected to avoid shared-object mutation and to check the actual collapsed state
of a details element after a viewer switch.

Files changed:

- `backend/counterpress/recaps.py`: recap contracts and ledger composition.
- `backend/counterpress/api/snapshots.py`: same-read recap in snapshot responses.
- `frontend/src/SegmentRecap.tsx`: localized recap and exact revision links.
- `frontend/src/recapValidation.ts`, `frontend/src/api.ts`: transport validation.
- `frontend/src/App.tsx`, `frontend/src/types.ts`, `frontend/src/styles.css`: scoped UI, types and theme.
- `tests/test_recaps.py`, `frontend/src/SegmentRecap.test.tsx`: independent and lifecycle checks.
- `README.md`, `docs/recaps.md`, `docs/progress.md`: behavior, commands and next work.
- `docs/screenshots/segment-recap-en.png`, `docs/screenshots/segment-recap-zh.png`: browser captures.

Final local verification commands and output:

```console
$ UV_CACHE_DIR=.uv-cache uv run --frozen pytest -q
........................................................................ [ 18%]
........................................................................ [ 37%]
........................................................................ [ 56%]
........................................................................ [ 75%]
........................................................................ [ 93%]
........................                                                 [100%]
384 passed in 7.88s

$ npm --prefix frontend test
Test Files  6 passed (6)
     Tests  30 passed (30)
  Duration  2.06s

$ npm --prefix frontend run build
> counterpress-frontend@0.1.0 build
> tsc --noEmit && vite build
vite v7.3.7 building client environment for production...
transforming...
✓ 42 modules transformed.
rendering chunks...
computing gzip size...
dist/index.html                   0.53 kB │ gzip:  0.35 kB
dist/assets/index-Cie8pE97.css   18.51 kB │ gzip:  4.96 kB
dist/assets/index-DUXMj61y.js   269.28 kB │ gzip: 83.23 kB
✓ built in 420ms

$ git diff --check
(no output; exit 0)
```

This completes the factual recap increment, not the full build plan. Best next
move: bounded recap adaptation using Microsoft Agent Framework, with unchanged
citations, deterministic fallback and stale-result rejection. Stage 9 then adds
Container Apps/configuration, Cosmos DB durability, Event Hubs ingestion, Web
PubSub delivery/reconnect and deployed language polish. Stage 10 measures the
result and assembles the demonstration. No Azure action was needed in this turn.
The requested final architecture review remains a build-plan completion gate.

PR CI initially exposed a pre-existing cancellation-test timing assumption:
the 50 ms workflow budget expired during cold fixture projection on a shared
runner, correctly producing timeout before any provider invocation. The test now
prepares fixture history first and uses a 500 ms test budget, still requiring
exactly one cancelled provider request, timeout status, no model text and usable
match facts. The production eight-second ceiling is unchanged; the independent
exhausted-budget test still checks rejection before network/tool invocation.
`tests/test_workflow.py` is the additional changed file. The full backend suite
then passed locally: 384 tests in 7.88s. Both required CI checks must pass on the
updated commit before merge.

## Stage 8 eighth increment — bounded recap workflow, 16 October 2026

A Microsoft Agent Framework Analyst/Producer graph now adapts a frozen recap.
The Analyst must request the evidence and limitations tools, then accept, narrow
or reject the supplied stories. The Producer receives a fresh package and chooses
approved wording and a heading. Code validates identity, order, fingerprint and
language; model prose never becomes football facts. Both stages use the existing
hard transport/tool budgets and eight-second deadline.

A new append-only audit table is migrated additively. Atomic commit checks reject
intervening source/publication changes. Snapshot presentation checks source,
cutoff, preferences and expiry. The factual recap stays in every snapshot alongside
any accepted adaptation, and a browser timer restores it when the adaptation
expires. Replay polling does not invoke the model. No new Azure resource was
required; existing local configuration validated without revealing its values.

Files changed:

- `backend/counterpress/workflow/recap_contracts.py`, `recap_service.py`, `recap.py`: schemas, bounded graph and sanitized CLI.
- `backend/counterpress/recap_adaptation.py`: fingerprint, validated plan and factual fallback.
- `backend/counterpress/history.py`: additive audit persistence and append-only guards.
- `backend/counterpress/api/snapshots.py`: factual/adapted recaps and compact workflow view.
- `backend/counterpress/recaps.py`, `audience.py`, `workflow/contracts.py`: shared factual rendering, type-only history imports and activity labels.
- `frontend/src/SegmentRecap.tsx`, `App.tsx`, `types.ts`, `recapValidation.ts`, `WorkflowActivity.tsx`: validated presentation, expiry fallback and bilingual activity.
- `tests/test_recap_workflow.py`, `frontend/src/SegmentRecap.test.tsx`: real framework/SDK mock boundaries, lifecycle tests and browser-contract checks.
- `README.md`, `docs/recaps.md`, `docs/recap-workflow.md`, `docs/progress.md`: behavior, commands, scope and next milestone.
- `docs/verification/recap-workflow-live.json`, `docs/screenshots/recap-workflow-live-en.png`: sanitized live verification and browser capture.

Final local verification commands and output (result excerpts):

```console
$ UV_CACHE_DIR=.uv-cache uv run --frozen pytest -q
419 passed in 11.10s

$ npm --prefix frontend test
Test Files  6 passed (6)
     Tests  32 passed (32)
  Duration  2.29s

$ npm --prefix frontend run build
> counterpress-frontend@0.1.0 build
> tsc --noEmit && vite build
vite v7.3.7 building client environment for production...
transforming...
✓ 42 modules transformed.
rendering chunks...
computing gzip size...
dist/index.html                   0.53 kB │ gzip:  0.35 kB
dist/assets/index-Cie8pE97.css   18.51 kB │ gzip:  4.96 kB
dist/assets/index-BTCKEVKM.js   271.18 kB │ gzip: 83.82 kB
✓ built in 421ms

$ git diff --check
(no output; exit 0)
```

Live check command:

```sh
UV_CACHE_DIR=.uv-cache uv run --env-file .env --frozen python -m counterpress.workflow.recap pressure-increase --db var/recap-workflow-live.sqlite3 > /private/tmp/counterpress-recap-live.json
```

Sanitized result excerpt:

```json
{
  "status": "accepted",
  "reason": "supported_comparisons",
  "duration_ms": 7304,
  "provider_requests": 3,
  "analyst_requests": 2,
  "producer_requests": 1,
  "tool_invocations": 2
}
```

The live result retained both stories and their exact citations. Browser review
showed the accepted brief presentation and activity, then automatic expiry restored
the full factual wording with both evidence links intact. Browser warning/error
log was empty. The live latency is one sample, not P95 or a reliability claim.
Both languages and narrowed/rejected/failure cases are covered offline.

Best next move: Stage 9 container packaging and Azure runtime configuration,
followed by shared durability and streaming adapters. Before deploying new Azure
resources, establish the target subscription/resource group, region, cost limit
and access configuration. The application is still local; this increment verifies
Azure model use, not Azure hosting. Stage 10 evaluation and the user's final
as-built architecture/Microsoft-extension review remain outstanding.

## Stage 9 container foundation verification — 16 October 2026

Changed files: `Dockerfile`, `.dockerignore`, `infra/foundation.bicep`,
`infra/app.bicep`, `scripts/container_smoke.py`, `scripts/test_container.sh`,
`backend/counterpress/api/main.py`, `tests/test_container_serving.py`,
`.github/workflows/ci.yml`, `docs/deployment.md`, `README.md` and this progress log.
No dependencies, credentials or frontend behavior changed.

Commands ran from the repository root; long test/build progress is abbreviated
below, with the actual result lines retained. Durations vary.

```console
$ UV_CACHE_DIR=.uv-cache uv run --frozen pytest -q
422 passed in 11.04s

$ npm --prefix frontend test
Test Files  6 passed (6)
Tests  32 passed (32)
Duration  2.59s

$ npm --prefix frontend run build
vite v7.3.7 building client environment for production...
✓ 42 modules transformed.
dist/index.html                   0.53 kB │ gzip:  0.35 kB
dist/assets/index-Cie8pE97.css   18.51 kB │ gzip:  4.96 kB
dist/assets/index-BTCKEVKM.js   271.18 kB │ gzip: 83.82 kB
✓ built in 474ms

$ docker build --platform linux/amd64 -t counterpress:smoke . > /private/tmp/counterpress-docker-build.log 2>&1
(exit 0; build log ended with #26 DONE 0.7s)

$ bash scripts/test_container.sh
PASS: health, readiness, frontend/assets, 1-to-4 evidence, control, bilingual recap, private-path 404s
PASS: non-root runtime, writable ephemeral database, no Azure environment or source credentials

$ DOTNET_BUNDLE_EXTRACT_BASE_DIR=/private/tmp/counterpress-dotnet /private/tmp/counterpress-bicep --version
Bicep CLI version 0.48.1 (cec7951cf6)

$ DOTNET_BUNDLE_EXTRACT_BASE_DIR=/private/tmp/counterpress-dotnet /private/tmp/counterpress-bicep build infra/foundation.bicep --outfile /private/tmp/counterpress-foundation.json
$ DOTNET_BUNDLE_EXTRACT_BASE_DIR=/private/tmp/counterpress-dotnet /private/tmp/counterpress-bicep build infra/app.bicep --outfile /private/tmp/counterpress-app.json
```

Both final Bicep compilations exited 0 with no diagnostics. The official compiler
was downloaded temporarily and its SHA-256 verified against the release metadata;
CI verifies the Linux binary's pinned checksum too. Compilation is not an Azure
what-if or live deployment. The local Linux/amd64 image is 242,940,261 bytes.

The local image archive scan checked all 18 entries against configured private
values/hostnames: no private key or endpoint matches. The configured deployment
label overlaps a public model identifier in the third-party OpenAI SDK; this was
inspected and excluded only within those SDK files. No local environment was
passed into the build or runtime. The source publication scan is also required
before push. No new browser capture was necessary: UI code is unchanged and its
compiled assets plus same-origin API were exercised over real HTTP.

The container has temporary SQLite state and factual templates only. No new Azure
resources, registry uploads, model requests or deployment workflow ran. The best
next move is the hosted smoke check once the user supplies subscription, region,
resource-group preference and budget; the deployment guide makes that action
reviewable. Cosmos DB, Event Hubs, Web PubSub and Stage 10 remain subsequent work.


## Azure deployment target clarification — 16 October 2026

The user chose to reuse the existing model resource group. The Azure portal's
resource metadata was matched to the locally configured model endpoint without
printing the endpoint or key. Resolved target identifiers remain in ignored
`var/azure-target.json`, not in published source or screenshots. No Azure resources
were changed. The deployment runbook now uses an existing-group inventory,
explicit location, namespaced deployment names and incremental mode. Cleanup
must target only newly created CounterPress resources, never the shared group.
The next step is authenticated Azure what-if and a cost estimate within the
user's hosting budget, followed by the hosted smoke deployment.

Azure CLI 2.90.0 was installed through Homebrew and signed into the confirmed
tenant using the normal browser flow. No model credentials were used for CLI
authentication. Read-only preflight precedes any resource creation.

Read-only preflight found only the existing model account and Foundry project in
the target group. The incremental foundation preview completed successfully:

```text
What-if status: Succeeded
Create Microsoft.App/managedEnvironments
Ignore Microsoft.CognitiveServices/accounts
Ignore Microsoft.CognitiveServices/accounts/projects
Create Microsoft.ContainerRegistry/registries
Create Microsoft.Authorization/roleAssignments
Create Microsoft.ManagedIdentity/userAssignedIdentities
```

The command is the foundation `az deployment group what-if` in the deployment
guide, with the locally stored target, explicit region and `--mode Incremental
--no-pretty-print --only-show-errors --output json`. Raw preview results stay
under ignored `var/`; the lines above contain only change categories/types.
The app preview still requires the foundation and uploaded image. No resources
were created. The user approved USD 75 for the whole trial, with USD 20 reserved
for the initial hosting stage. Budget alerts are not a hard
spending cap. Current public East US retail rates were checked for this advice.

The approved budget is now deployed and read back as USD 75, Quarterly, ending
2026-11-14T00:00:00Z (through 13 November). Actual thresholds are 50%, 75%, 90%,
100%; forecast threshold is 100%. The subscription spending limit remains On.
Azure rejected the original `none` log-destination string during deployment
validation despite successful compilation and what-if. The environment template
now uses supported `azure-monitor` routing without a diagnostic sink or paid
workspace. Budget, corrected foundation and application templates compile without
diagnostics. The private registry, identity and AcrPull assignment are provisioned;
the environment is still provisioning. The tested image has been uploaded.

## Azure hosted demo verified — 16 October 2026

Foundation and application ARM deployments both completed with `Succeeded`.
The app uses the tested image built from `30753cf1f37c550ec726a9b95d7f210f20e52c09`,
pinned by digest; infrastructure is from PR #6, merged as
`eeba7905408065c9e942d4096e71aa370c8235b1`. All three post-merge CI jobs passed
in [run 38857255717](https://github.com/Haydnlee31/CounterPress/actions/runs/38857255717).
Read-back checks confirmed private registry authentication, disabled admin access,
managed-identity pulls, HTTPS-only ingress, minimum zero/maximum one replica,
no runtime model secrets, the USD 75 budget and trial spending limit On.

Exact hosted verification command and output:

```console
$ .venv/bin/python - <<'PY'
import runpy, sys, urllib.request
urllib.request.install_opener(urllib.request.build_opener(urllib.request.ProxyHandler({})))
sys.argv = ['scripts/container_smoke.py', 'https://counterpress.icyplant-0eb80d8e.eastus.azurecontainerapps.io']
runpy.run_path(sys.argv[0], run_name='__main__')
PY
PASS: health, readiness, frontend/assets, 1-to-4 evidence, control, bilingual recap, private-path 404s
```

Initial urllib runs through the inherited local proxy truncated response bodies
with `IncompleteRead`. Explicit direct HTTPS passed the unchanged smoke script;
no assertion or body-integrity check was relaxed. Unsetting proxy environment
variables alone did not resolve the issue because macOS proxy discovery remained.
A separate complete JavaScript download was 271,175 bytes and matched the local
build SHA-256 `2f7bfc5f5a4eff3216c71f98535ddf84b660a3b06f6254a82ebfbfbdddf98567`.
This is a verification-process workaround, not an application networking change.

The live browser displayed the 58:00 comparison, 1 baseline recovery versus 4
current recoveries, all five pitch markers, 89 source records and the expanded
evidence panel. [Screenshot](screenshots/azure-hosted-recovery-en.png) and
[sanitized verification record](verification/azure-hosted-smoke.json) are included.
The test tab was closed after capture to avoid continued polling. Raw Azure
responses, account identifiers and budget contact details remain ignored locally.
The published hostname is the public demo, not the private model endpoint.

This deployment serves deterministic factual templates with temporary SQLite.
It does not enable cloud model calls or promise journal survival after scale-down.
Best next move: implement Cosmos DB shared persistence and prove restart recovery,
then add Event Hubs/Web PubSub. The full build plan and final architecture review
remain incomplete until the remaining Stage 9 and Stage 10 work is verified.


## Cosmos DB adapter and infrastructure — 16 October 2026

Added shared Cosmos history behind the storage protocol, common append-only and
uniqueness validation, explicit API/ingestion storage selection and sanitized
cloud failures. A two-item atomic batch commits the version head and full bounded
history together, with ETag conflict retry. Polling reads the small version head
and reloads the body only after a change. Histories above 1,800,000 serialized bytes
are rejected before writing; larger feeds require segmented storage.

Added serverless Cosmos Bicep, a separate managed identity with container-scoped
read/create/replace rights, disabled key authentication and optional Cosmos wiring
in the app template. Added template compilation to CI and an isolated two-phase
live durability checker. No cloud model credentials or public ingestion API added.

```console
$ UV_CACHE_DIR=.uv-cache uv run --frozen pytest -q
444 passed in 10.87s
```

The resource preview succeeded with only new Cosmos resources and the history
identity; existing app/model resources were ignored. Cost Management returned
429 twice; its result is unavailable, not zero. The earlier budget read reported
USD 0.00 but is delayed billing data. Serverless storage stays inside the existing
USD 5 storage/monitoring/networking allocation and USD 75 total envelope. Azure
provisioning is underway; live managed-identity and revision-restart checks must
pass before claiming cloud durability. See [Cosmos design and runbook](cosmos.md).


Local restricted-container smoke passed both HTTP behavior and non-root/private-file
checks. The final image scan checked 18 archive entries against four configured
private values/hostnames; no key or endpoint matches were found. Cosmos and app
Bicep compilation exited 0 without diagnostics.

East US account creation failed with Azure `ServiceUnavailable` due to regional
capacity. The failed account was confirmed to have never reached database creation;
only that newly failed account was targeted for cleanup. The existing hosting,
registry, model and shared resource group are retained. A separate database-region
parameter allows the nearby East US 2 fallback without moving the app. Live
provisioning and restart verification remain pending in this implementation record.

## Cosmos deployment and live restart verified — 16 October 2026

[PR #8](https://github.com/Haydnlee31/CounterPress/pull/8) merged as
`e07c2ea3df68ab396c409ac02f38c1aad6ac4948`; all three post-merge jobs passed in
[run 38859791350](https://github.com/Haydnlee31/CounterPress/actions/runs/38859791350).
The exact tested image was uploaded privately and activated by digest.

East US 2 accepted the serverless account. Azure then rejected the original
role-assignment scope because data-plane paths require `dbs/.../colls/...`, not
ARM `sqlDatabases/.../containers/...`. Corrected that path in `infra/cosmos.bicep`;
compilation and the subsequent deployment succeeded. The scoped role retains only
metadata access and item read/create/replace. Key authentication is disabled.
The existing app now uses the dedicated history identity and Cosmos configuration;
no model secret is present. Latest-revision health was checked separately from
ARM deployment status, which can finish while the revision is still starting.

Actual commands executed inside the healthy Azure revision:

```console
$ python -m counterpress.cosmos_check seed --scope durability-20261016
PASS: 93 source records, create/update/withdraw/create, historical 4/3/none/2, immutable evidence, fixture-free recovery

# After an Azure revision restart and confirmed replacement replica:
$ python -m counterpress.cosmos_check verify --scope durability-20261016
PASS: 93 source records, create/update/withdraw/create, historical 4/3/none/2, immutable evidence, fixture-free recovery
```

The Azure CLI restart returned `Restart succeeded`. Comparing the replica lists
confirmed one old replica replaced by one new replica with no shared name; the
new container was Running/ready with restart count zero. Public `/ready` returned
200. The verification service deliberately used a nonexistent fixture directory,
so reseeding could not satisfy recovery. Its synthetic test partition is separate
from all publicly selectable demo scenarios and is retained for inspection.

The unchanged HTTP smoke script, SHA-256
`e29241b6ef2d5687a44d6e27160e6bce8323b8e78c3a5023b31e0e8fb61a2836`,
was fetched from the exact merged commit, hash-checked and run inside Azure against
the public HTTPS URL before and after restart. Local orchestration command/output:

```console
$ python3 /private/tmp/counterpress-cosmos-live-check.py http
PASS: health, readiness, frontend/assets, 1-to-4 evidence, control, bilingual recap, private-path 404s
Phase: http verified through the hosted managed identity.
```

The temporary orchestration helper uses authenticated Azure CLI exec; resolved
account/revision identifiers and raw logs stay under ignored `var/`. The committed
HTTP smoke script and two-phase durability checker contain the actual assertions.
Local urllib asset downloads intermittently truncated even after explicit proxy
configuration was disabled. The earlier proxy diagnosis is therefore not proven;
root cause remains unconfirmed. The identical strict smoke passed from Azure,
without changing assertions or ignoring incomplete reads.

The East US 2 retail serverless meter was checked at USD 0.25 per million RUs,
plus storage. The USD 75 total envelope and USD 5 storage/monitoring/networking
allocation are unchanged. The cross-region app/database arrangement adds latency
and potential transfer cost; it is a capacity fallback, not regional replication.
No paid upgrade or trial-spending-limit change was made.

See [sanitized live evidence](verification/cosmos-durability.json) and the updated
[deployed architecture](deployment.md). Cloud replica-restart durability is now
verified. Larger histories, Event Hubs ingestion, Web PubSub reconnect delivery,
OIDC deployment and Stage 10 evaluation remain subsequent work.

## Event Hubs and Web PubSub implementation — 16 October 2026

Added typed, match-keyed Event Hubs deliveries, a retrying consumer, atomic existing
Cosmos ingestion, durable Blob checkpoints and invalid-delivery quarantine. Current
revision heads publish through Web PubSub before checkpointing. The browser uses
receive-only scenario tokens and treats push as a hint to retrieve a validated
snapshot; reconnect and periodic reconciliation recover missed notices. Added an
isolated `stream-recovery` scenario without changing the original fixture history.

Infrastructure adds Basic one-TU Event Hubs, Web PubSub Free and LRS Blob storage,
with separate consumer/producer managed identities and a zero-to-one Event Hubs
scale rule. The checked Basic rate is USD 0.015/hour, approximately USD 10.08 over
28 days before ingress/storage/network costs, within the approved USD 20 streaming
allocation. The total trial envelope remains USD 75. Local mode remains cloud-free.

Validation commands and observed output:

```console
$ UV_CACHE_DIR=.uv-cache uv run --frozen pytest -q
459 passed in 13.14s
$ npm --prefix frontend test
Test Files  7 passed (7)
Tests  36 passed (36)
$ npm --prefix frontend run build
✓ 43 modules transformed.
✓ built in 441ms
$ bash scripts/test_container.sh counterpress:streaming
PASS: health, readiness, frontend/assets, 1-to-4 evidence, control, bilingual recap, private-path 404s
PASS: non-root runtime, writable ephemeral database, no Azure environment or source credentials
```

Both `infra/streaming.bicep` and the updated `infra/app.bicep` compiled. The image
archive scan passed against four configured sensitive values/hostnames. The Azure
what-if preview showed only new streaming resources; application activation and
live transport proof are separate from these offline implementation checks.
See [streaming design and operations](streaming.md).

### Event Hubs received partition-key compatibility

The first actual cloud delivery reached the consumer and was quarantined without
changing history: the Event Hubs SDK exposes the received partition key as bytes,
while the envelope uses a string. Normalize UTF-8 bytes before checking the exact
match identity. The regression now runs commit/notify/checkpoint and duplicate
replay with both representations. The invalid-delivery checkpoint remains retained;
resubmitting the valid source records after the fix is safe.

```console
$ UV_CACHE_DIR=.uv-cache uv run --frozen pytest -q
460 passed in 13.37s
```

The corrected image passed the restricted container smoke and private-configuration
scan. Live verification must be repeated against this corrected revision.


### Streaming deployment and live verification

Merged implementation [PR #11](https://github.com/Haydnlee31/CounterPress/pull/11)
and SDK compatibility [PR #12](https://github.com/Haydnlee31/CounterPress/pull/12).
The deployed image is built from `2a71e85188d6009fb58f6b7125e4a34a41aa7812`;
its [post-merge CI](https://github.com/Haydnlee31/CounterPress/actions/runs/38870163374)
passed all three jobs. The image was smoke-tested and scanned before registry push.
Both incremental Azure previews were reviewed before creating streaming resources
and activating the existing application with Cosmos and streaming enabled.

The corrected revision passed the actual Event Hubs → Cosmos → Web PubSub → Blob
checkpoint exercise. Two deliveries with different envelope IDs but identical
source revisions produced only 93 journal records (89 canonical events). Real
receive-only WebSocket messages carried history version 93 and the latest recovery
revision 4. Durable offsets advanced for both deliveries. The isolated live scenario
preserves historical counts 4, 3, withdrawn, 2, and original revision-1 evidence 4.
The original public recovery scenario remains unchanged.

Exact live-check commands and observed output (inside the configured Azure app):

```console
$ python -m counterpress.streaming.check --exercise
PASS: Event Hubs -> Cosmos -> Web PubSub, duplicate replay, durable Blob checkpoint
PASS: historical 4/3/withdrawn/2, frozen evidence, original scenario unchanged
```

The Azure revision was restarted. Before/after replica lists had no name in common,
and public readiness returned 200. The orchestration and subsequent checks were:

```console
$ python3 /private/tmp/counterpress-restart-stream.py
Revision restart accepted; waiting for a replacement replica.
PASS: previous replica replaced; public readiness returned 200 after restart
$ python3 /private/tmp/counterpress-stream-remote.py verify
PASS: historical 4/3/withdrawn/2, frozen evidence, original scenario unchanged
$ python3 /private/tmp/counterpress-stream-remote.py exercise
PASS: Event Hubs -> Cosmos -> Web PubSub, duplicate replay, durable Blob checkpoint
PASS: historical 4/3/withdrawn/2, frozen evidence, original scenario unchanged
$ python3 /private/tmp/counterpress-stream-remote.py http
PASS: health, readiness, frontend/assets, 1-to-4 evidence, control, bilingual recap, private-path 404s
```

These temporary helpers resolve private Azure target configuration and invoke the
committed `counterpress.streaming.check` module through authenticated CLI exec.
The HTTP phase fetches the unchanged smoke script from the exact deployed commit,
checks its SHA-256, then executes it inside Azure against the public HTTPS URL.
Actual identifiers, checkpoint offsets and raw diagnostic logs stay under ignored
`var/`. The initial rejected delivery is retained, not erased from the audit trail.

Chrome confirmed **Live revision updates connected**, the 58:00 historical 1 → 4
comparison with a **View latest corrections** action, then 1 → 2 at 58:15. The
evidence table identifies `p053` revision 3. The browser remained paused until the
latest-corrections button was clicked. The screenshot is in
[screenshots/streaming-live.png](screenshots/streaming-live.png); the test tab was
closed afterward. Reconnect/duplicate-notice/fallback behavior also has automated
frontend coverage; activation from zero has not been separately measured.

The [demo guide](demo-guide.md), [current architecture](deployment.md) and
[sanitized live record](verification/streaming-live.json) now reflect deployed
streaming. The USD 75 total envelope and USD 20 streaming allocation are unchanged;
these are not measured spend or a hard cap. No model credentials were added to the
hosted app. Next: protected OIDC deployment, cost-bounded operational telemetry,
then Stage 10 evaluation and the complete Microsoft-platform architecture review.


## OIDC deployment and operational telemetry — 16 October 2026

Added a manually dispatched GitHub deployment workflow restricted to `main` and
successful CI for the exact current commit. It builds/smoke-tests before Azure
login, pushes by commit, deploys by immutable digest and checks unchanged runtime
configuration plus public HTTPS and correction history. The dedicated federated
identity has app-scoped read/write, registry AcrPush/Reader and environment Reader;
no resource-group Contributor or role-assignment access. Model secrets are absent.

Added numeric streaming counters for successful/quarantined deliveries, retries,
publish/checkpoint/consumer failures, transport delivery age, pending duration and
observed backlog. One record per minute avoids per-request logging. The monitoring
Bicep template creates a 30-day Log Analytics workspace, 0.025 GB daily guard,
numeric-only workspace transformation and a saved operational KQL query. No
email/webhook notifications or recurring alert-rule charges are enabled.

```console
$ UV_CACHE_DIR=.uv-cache uv run --frozen pytest -q
466 passed in 12.64s
```

The new identity and monitoring templates and updated application template compiled.
The monitoring what-if initially rejected an `outputStream` intended for ingestion
DCRs; the corrected workspace transformation omits it and passed preflight. The
identity preview adds only the dedicated identity, federation, custom role and
resource-scoped assignments. The monitoring preview creates only its workspace,
table, transformation and saved query. Actual activation/deployment proof follows
separately; compilation and tests do not prove cloud delivery.

East US Analytics ingestion was checked at USD 2.30/GB. The nominal 0.025 GB daily
guard corresponds to about USD 1.61 over 28 days before other charges, within the
existing USD 5 storage/monitoring/network allowance and USD 75 total envelope.
Caps may overshoot and the actual-cost API remained unavailable. See the
[operations runbook](operations.md) for release, rollback, metric meanings and
limits. Live model adaptation remains disabled.

Azure's workspace API rejected the initial 0.01 GB guard because its minimum is
greater than 0.023 GB/day. The template now uses 0.025 GB/day (about USD 1.61
over 28 days at the checked ingestion rate, before other charges). This still
fits the existing monitoring allowance; no budget increase was made.

The first GitHub deployment stopped at OIDC login, before pushing or changing the
app: this recently created repository emits GitHub's immutable subject containing
owner/repository IDs. Azure federation initially expected the legacy name-only
format. The template now binds the exact immutable subject; no wildcard trust or
GitHub security downgrade is used. A separate regression requires the specifically
requested Azure revision to be ready, avoiding a stale previous-ready match.


### OIDC release verified

The complete [GitHub deployment](https://github.com/Haydnlee31/CounterPress/actions/runs/38875948320)
passed from `acf0a5dfc1fec1b4f43a2787854297de2d2a199b`. Its exact-commit
[CI](https://github.com/Haydnlee31/CounterPress/actions/runs/38875592294) passed
468 backend tests, 36 frontend tests, the container smoke and all Bicep compilations.
Observed CI output:

```console
$ uv run --frozen pytest -q
468 passed in 26.97s
```

Observed release commands/output:

```console
$ gh workflow run deploy.yml --repo Haydnlee31/CounterPress --ref main
https://github.com/Haydnlee31/CounterPress/actions/runs/38875948320
# Inside the successful workflow:
$ python3 scripts/deploy_azure.py deploy
PASS: protected main head has successful exact-commit CI
Deploy phase: updating the existing app image
Deploy phase: waiting for the requested revision
PASS: OIDC image deployment; Cosmos, streaming, identities and scaling preserved
PASS: public HTTPS smoke and historical streaming corrections
```

The federated login uses GitHub's exact immutable owner/repository subject and the
new main-only environment. No existing reviewer protections were changed. App
read/write and registry/environment roles retain their original narrow scopes.
The first post-login attempt exposed Azure's empty successful asynchronous PATCH
response: the image was accepted, but JSON parsing stopped verification. The fixed
script treats PATCH success separately and waits for the requested revision name.
An independent Azure state read confirmed the successful run's exact revision.
The public workflow log scan found no configured model credentials/endpoints or
JWT-like tokens.

The new runtime passed Event Hubs → Cosmos → Web PubSub and checkpoint checks with
duplicate deliveries, retained 4/3/withdrawn/2 history and unchanged original
scenario. Its console emitted numeric records with two processed deliveries and
zero retries. Monitoring collection uses the observed optional `F ` full-line
prefix. Normal Logs KQL accepted regex replacement, but the ingestion engine
rejected that function; the deployed filter uses supported `iff` and `substring`
instead. A real KQL test keeps plain/prefixed numeric records, removes an extra
synthetic field and discards an unstructured line. Retained-log verification is
separate from this query-engine test and console emission.


## 16 October 2026 — acknowledged monitoring and protected release verified

The [protected OIDC release](https://github.com/Haydnlee31/CounterPress/actions/runs/38878879739)
succeeded from `f0fff2cfffeb9fa055dddbd4b4a34489b3e27ff7`, after its
[exact-commit CI](https://github.com/Haydnlee31/CounterPress/actions/runs/38878763648)
passed. The requested revision became ready; public HTTPS, frozen evidence and
4/3/withdrawn/2 correction history passed. A new duplicate-delivery exercise passed
Event Hubs → atomic Cosmos history → Web PubSub → durable Blob checkpoint without
changing the original scenario.

The console-export diagnostic route did not produce retained rows. Its filter was
restored, then the route was removed after the replacement worked. The app now
uses the Azure Monitor Logs Ingestion API with its streaming managed identity,
Monitoring Metrics Publisher scoped only to the new Direct collection rule, and a
typed `CounterPressOperations_CL` table. An explicit live upload received HTTP 204.
Subsequent Log Analytics queries confirmed retained operational records, including
the processed exercise deliveries. This proof is separate from console output and
API acknowledgement. The workspace retained its 30-day retention and 0.025 GB/day
guard. No new budget allocation, application secret or model endpoint was added.

Exact local verification:

```console
$ .venv/bin/python -m pytest -q
471 passed in 12.15s
```

Exact backend CI command/output (frontend: 36 passed; container and Bicep checks passed):

```console
$ uv run --frozen pytest -q
471 passed in 27.71s
```

Release and live exercise commands/output:

```console
$ gh workflow run deploy.yml --repo Haydnlee31/CounterPress --ref main
https://github.com/Haydnlee31/CounterPress/actions/runs/38878879739
# Inside the release workflow:
$ python3 scripts/deploy_azure.py deploy
PASS: protected main head has successful exact-commit CI
Deploy phase: updating the existing app image
Deploy phase: waiting for the requested revision
PASS: OIDC image deployment; Cosmos, streaming, identities and scaling preserved
PASS: public HTTPS smoke and historical streaming corrections
# Inside the deployed container:
$ python -m counterpress.streaming.check --exercise
PASS: Event Hubs -> Cosmos -> Web PubSub, duplicate replay, durable Blob checkpoint
PASS: historical 4/3/withdrawn/2, frozen evidence, original scenario unchanged
```

Retained query:

```kusto
CounterPressOperations_CL
| where TimeGenerated > ago(1h) and schema == 'counterpress_ops_v1'
| summarize Windows=count(), Processed=sum(processed), Rejected=sum(rejected),
    Retries=sum(retries), PublishFailures=sum(publish_failures),
    CheckpointFailures=sum(checkpoint_failures), ConsumerFailures=sum(consumer_failures),
    ExportFailures=sum(export_failures), MaxAgeSeconds=max(max_delivery_age_seconds),
    LastRecord=max(TimeGenerated)
```

Observed output:

```json
{
  "Windows": 7,
  "Processed": 2,
  "Rejected": 0,
  "Retries": 0,
  "PublishFailures": 0,
  "CheckpointFailures": 0,
  "ConsumerFailures": 0,
  "ExportFailures": 0,
  "MaxAgeSeconds": 15.784,
  "LastRecord": "2026-10-16T09:20:14.297435Z"
}
```

Sanitized [release evidence](verification/operations-live.json) and the
[operations runbook](operations.md) capture the current behavior. The source and
successful public release log scans found no configured model credentials/endpoints
or credential patterns; the log also passed a JWT-pattern scan. Resolved cloud
configuration and raw Azure responses remain outside tracked files.

Metrics are best-effort windows; a failed upload is counted in a later window but
is not replayed. No email/webhook alert is enabled. Actual spend remains unverified;
the US$75 envelope and daily guard are not automatic spending shutdowns. The hosted
model remains off. Next: Stage 10 measured evaluation, final judge demonstration,
and the as-built Microsoft architecture with separately costed extension proposals.

## Fan-first redesign — Matchday implementation (2026-10-16)

The first redesign slice introduces a useful default at 58:00, inline catch-up,
readable event evidence, optional team/player following, persistent device-local
preferences, English/Chinese presentation and mobile layouts. Original fictional
names replace actor IDs in fan-facing copy; source identities and calculations are
unchanged. The previous analysis workspace remains at `#analysis`.

The interface exposes revision updates and withdrawals, keeps a paused viewer's
position, and removes future facts on rewind. Slow playback requests are coalesced
rather than repeatedly cancelled; displayed facts have an explicit cutoff.
The release introduces no new cloud resources. Hosted model adaptation stays off;
authenticated Studio, bounded editorial integration and user studies remain pending.
See the [delivery plan](redesign-implementation.md) and [identity register](identity-assets.md).

Local verification against an isolated SQLite backend:

```console
$ .venv/bin/python -m pytest -q
471 passed in 12.86s
$ npm --prefix frontend test -- --reporter=dot
Test Files  8 passed (8)
Tests  48 passed (48)
$ npm --prefix frontend run build
> tsc --noEmit && vite build
✓ 51 modules transformed.
```

Real-browser command (Playwright supplied by the local runtime; installed Chrome):

```sh
NODE_PATH=/Users/haydn/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules \
CHROME_EXECUTABLE='/Applications/Google Chrome.app/Contents/MacOS/Google Chrome' \
COUNTERPRESS_CHECK_CORRECTIONS=1 \
node scripts/test_matchday.cjs http://127.0.0.1:8010
```

```text
PASS: historical recovery 4/3/withdrawn/2
PASS: actual HTTP fan view, inline evidence, persistent bilingual preferences, all four story families, mobile widths, rewind and analysis navigation
```

The correction fixture was prepared in the isolated local history before this
check; the browser script itself performs no ingestion. Desktop/mobile screenshots
were visually reviewed. Layout checks cover 360, 390, 640 and 1365 pixels and 200%
text sizing. These checks do not constitute human user research or a complete
accessibility audit. Cloud promotion uses the existing protected PR/CI/OIDC path;
release-specific live evidence is recorded separately after deployment.


Matchday was subsequently deployed from `b18fbf34f7f6cfb95feef6435eedc33d26614de4`
through [release 38885974712](https://github.com/Haydnlee31/CounterPress/actions/runs/38885974712).
Exact-main CI, the requested Azure revision, the restricted-container smoke test
and public HTTPS/historical correction checks all passed. Cosmos, streaming,
telemetry, managed identities and scaling were preserved; no model credentials
were supplied to the hosted app.

The same browser command was rerun with the public demo URL, from a temporary
working directory so local screenshots were retained. Both PASS lines above were
observed against the live app. Live desktop/mobile screenshots were visually
reviewed and showed the revision channel connected. Source, 19 screenshot OCR
outputs and the successful release log passed configured-secret/private-model-
endpoint scans; the release log also passed a JWT-pattern check. Sanitized evidence
is in [verification/matchday-live.json](verification/matchday-live.json).

Next: benchmark templates, one agent and the existing Analyst/Producer workflow,
then integrate the smallest useful bounded editorial flow. Authenticated Studio
and human fan/producer evaluation follow. No Azure setup is required from the user
for the completed Matchday release.
