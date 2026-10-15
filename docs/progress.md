# Progress

Current milestone: Stage 8 fourth increment — possession without progression now
has independent controls, durable correction/withdrawal handling and bilingual
episode evidence. Pressure/escape and recovery stories share the one-card audience budget. Seeded generation,
independent controls and whole-match development/holdout splits remain complete.
Player-contribution detector expansion and recaps remain outstanding.
Stage 7 analyst/casual views, preferences and English/Simplified Chinese variants
remain complete. Stage 6 single-call adaptation and
bounded Analyst/Producer workflow remain verified against live Azure. Stage 5
durable history remains complete. Foundation contracts and the local
FastAPI health endpoint remain in place. Startup and validation commands are in
the README. After each task, report the result and the best next move.

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
Best next move: add possession-without-progression detection with independent
episode controls and the same durable evidence lifecycle. No Azure
action is needed for that increment. Recaps and Azure application deployment remain
later work. Never request API keys in chat.

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
