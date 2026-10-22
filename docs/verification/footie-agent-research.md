# Footie bounded research — 23 October 2026

## Latest release gate — passed

The queued full version 5 Azure sample completed at **00:21 Singapore time on
23 October 2026**, after the existing rolling allowance renewed. The
[final sanitized report](footie-agent-v5-final-azure.json) records **10/10 overall
cases passed**, **9/9 eligible agent workflows completed without fallback**, and
correct handling of the unsupported tracking question without a model call.
All evidence and temporal-anchor checks passed. It used 18 provider requests;
median latency was 4.475 seconds and sample p95 was 5.526 seconds.

All evaluated source hashes match the reviewed implementation. This closes the
small authored-sample release gate; it does not establish accuracy on unseen fan
questions. The earlier failed runs below remain part of the verification record.

PR #56 CI passed all **981 backend tests**, the reproducible career-ledger audit,
container smoke checks and Azure template compilation. The frontend passed all
204 tests, adapter checks and its production build on retry. The initial CI
attempt had two intermittent replay-position test failures; both the full local
suite and the focused Node 24 check passed. Those failures are retained in the
PR/CI history. The PR is now being prepared for merge and exact-commit deployment;
this paragraph is not a hosted deployment confirmation.

## Scope and status

This records the **research and shared-admission stage** of the Reactor-inspired agent roadmap. It does
not change hosted Azure configuration, activate career ingestion, create cloud
resources, or publish a new release. The dashboard Tools entry points were removed
in the preceding local change; the operator routes and backend remain available.

Implemented:

- Up to three explicit metrics for player/club statistics, comparisons, recent
  form, season comparisons and club rankings. All measures share the selected
  entities and period. Follow-ups retain the metric set unless replaced explicitly.
- Separate chart scales for each metric. Missing values remain unavailable; they
  are never presented as zero. Desktop cards become stacked cards on narrow screens.
- A real Microsoft Agent Framework `Agent` with the typed
  `read_football_records` function tool. Its operation dispatches to the existing
  deterministic statistics, comparison, recent-form, season, ranking or match
  reducers. This is one agent and one bounded query bundle, not a multi-agent swarm.
- Two provider requests maximum, one tool invocation, up to three metric reads,
  a 12-second research deadline, no provider retries, and a durable shared
  allowance of 20 reserved provider slots per rolling hour. Each admitted job
  reserves two slots; failed or unused slots are not refunded. The HTTP envelope allows 14 seconds
  including semaphore wait. Tool calls cannot supply SQL, code, URLs or writes.
- Strict first-turn query schema using the actual metric catalog. The second-turn
  schema enumerates sentence IDs from the completed tool receipt and disables
  further tool calls. Python still validates the selection and reconstructs text.
- API commit rereads every fact under one revision snapshot. A correction during
  inference discards the stale narrative. Source IDs, scope and coverage remain
  visible through the existing response/evidence contract.
- Durable SQLite/Cosmos admission for runtime agent mode: two concurrent leases,
  60-second reuse of identical completed reads, failure retry suppression, revision
  and preference isolation, and fresh fact validation before displaying cached prose.
  Cosmos reuses the existing histories container in a separate control partition.
  Only hashed request keys, typed plans and sentence IDs are persisted; no user
  questions, free-form answer text or credentials. Storage failure returns a
  calculated answer without paid inference. This does not add fan authentication;
  anonymous traffic can exhaust the shared allowance. The older structured-lookup
  path retains its existing process-local limits.
- Sanitized request counts, cache hits and known/unknown token-usage accounting in
  operational logs. No prompt/answer logging was enabled. Full Application Insights
  spans and managed-identity model authentication are still later work.

## Local review

```bash
npm --prefix frontend run build
.venv/bin/python scripts/run_footie_local.py --port 8021
```

Open `http://127.0.0.1:8021/#assistant`. This mode exercises the new compound
answers without paid model calls. Try:

- `How many goals and assists does Mateo Cross have?`
- `Compare Rory Ellis and Dario Voss goals and assists last season`
- Follow with `And this season?`
- `Show Leon Finch saves and pass completion`
- `Show Rory Ellis goals and saves` (saves must stay unavailable)

The opt-in agent path is:

```bash
.venv/bin/python scripts/run_footie_local.py --azure --agent --port 8022
```

It uses existing server-only local model configuration. No credentials belong in
source control or the browser. The full version 5 live evaluation passed; activation is an explicit deployment
choice through `assistant_workflow=agent`. Without this flag the
existing planner/narrator path remains selected when Azure is enabled.

## Evaluation evidence and unresolved gate

The authored corpus grew from 58 to 72 cases. The existing multi-metric case was
intentionally relabelled from clarification to a grounded two-metric answer;
14 new cases cover compound comparisons, rates, clubs, recent form, follow-ups,
missingness and out-of-scope requests. Intent labels are authored separately from
the parser. The numeric oracle still uses existing reducers; this is not an
independent audit of the synthetic dataset or a population accuracy estimate.

Validation commands and observed results:

```text
.venv/bin/pytest -q
932 passed, 1 warning in 161.80s

# After final narration wording and request-accounting edits:
.venv/bin/pytest -q tests/test_assistant.py tests/test_assistant_research.py tests/test_assistant_narrative.py tests/test_assistant_evaluation.py
159 passed in 35.37s

npm --prefix frontend test
35 test files passed; 204 tests passed

npm --prefix frontend run build
TypeScript and Vite production build passed
```

The offline corpus passed 72/72 effective answers. Browser checks exercised the
actual local API at 1440, 768, 390 and 320 px, including a two-metric follow-up,
missing values, separate scales and no horizontal page overflow.

Live Azure findings (all against local evaluation apps, not hosted user traffic):

1. Initial compound pilot: correct query, but the agent authored prose in the
   sentence-ID fields. The validator rejected it. The first report's overall
   `passed` status was too permissive because it counted factual fallback success.
2. Evaluator corrected: an agent run requiring fallback now fails the agent gate.
   A second pilot confirmed the same narrative problem.
3. Dynamic ID-enumerated output schema added. A fresh compound pilot passed with
   two provider requests, one read tool and no fallback (about 4.6 seconds).
4. Seven broader cases: 7/7 final factual answers were correct, but only **3/7 were
   completed through the agent**, so the run **failed**. Invalid extra metric,
   malformed/omitted query arguments and a follow-up operation mismatch were
   rejected and fell back safely. They must not be reported as successful agents.
5. The strict, fully required query schema improved recent-form and follow-up
   questions, but a fresh four-case check still failed comparisons and match
   arguments. Removing the irrelevant first-turn prose schema fixed the match
   query. The comparison still asked for an unrequested denominator metric.
6. Explicit measure names now constrain the output schema using the same metric
   binding enforced by the service validator. Invalid plans stop before a second
   model request. A fresh targeted check passed **4/4 through the agent**:
   comparison per 90, season follow-up, goals plus assists, and a match cutoff.
   All factual/evidence checks passed, no fallback, eight model requests, about
   3.7–4.7 seconds per answer. This is a targeted regression, not a full release gate.
   A sanitized copy is [retained in the repository](footie-agent-targeted-azure.json).
   This run exercised the inner agent before the shared-admission wrapper was
   added; the wrapper has separate local checks and has not passed a live write check.
7. A new full live sample remains pending. The three follow-on runs used 19
   provider requests (72,444 input + 689 output = 73,133 reported tokens), leaving
   insufficient allowance for a complete two-turn question. The allowance was
   not reset or bypassed. Across the earlier four live runs, the provider reported
   64,851 input tokens and 902 output tokens (65,753 total). These are usage
   counts, not an Azure billing statement.

Ignored evidence files are in `var/footie-agent-azure-pilot*.json`,
`var/footie-agent-azure-review.json`, `var/footie-v2-offline.json` and
`var/footie-agent-review/`. Follow-on results: `var/footie-agent-strict-query-review.json`,
`var/footie-agent-query-boundary-review.json`, `var/footie-agent-constrained-query-review.json`.
Preserve failed reports as well as successful ones.
Run a fresh report after the allowance renews:

```bash
.venv/bin/python scripts/evaluate_footie.py --azure --agent \
  --output var/footie-agent-fresh-review.json
```

The default live sample has ten cases, including one locally rejected unsupported
request. `--case` selects authored cases for targeted checks; `--max-attempts`
can reduce the allowance. An incomplete budget-limited run is not a pass. Record
raw interpretation, final factual accuracy, agent completion, latency and fallback
separately. A repeated post-fix sample is needed before cloud activation.

## Shared admission checks

The new admission tests cover independent SQLite connections, Cosmos ETag/create
conflicts with a transactional service double, restart-persistent quotas, old lease
owners, exact duplicates, failure suppression, receipt recovery, preferences and
release namespaces, correction invalidation, and storage-outage fallback.

```text
.venv/bin/pytest -q tests/test_assistant_admission.py
19 passed in 31.54s

.venv/bin/pytest -q tests/test_workflow.py
26 passed in 7.96s
```

The first broader run returned 953 passed and one timeout in an existing workflow
correction-race test (expected stale evidence; the eight-second deadline expired).
The complete workflow file then passed separately. The initial failure log is
retained at `var/footie-agent-v3-backend-tests.log`; it must not be described as a
clean full-suite pass. A serial confirmation run is recorded separately.

```text
.venv/bin/pytest -q > var/footie-agent-v3-backend-confirmation.log 2>&1
955 passed, 1 warning in 227.74s (0:03:47)
```

The warning is the existing Agent Framework experimental evaluator warning.
The final source lock and `git diff --check` passed, and a scan of changed/new
files found no literal private values from the local model configuration.
The restarted offline preview on port 8021 returned `Health: ok` and passed a
real HTTP compound comparison plus season follow-up with zero model calls.

An actual isolated Cosmos seed check on 22 October failed with **HTTP 403** at
the write boundary. Read-only investigation confirmed that the local Azure CLI
user has the account-scoped built-in **Cosmos DB Data Reader** role. Point reads
work (the uncreated test record returns 404); network access is enabled with no
IP allowlist or VNet filter. No permissions were expanded, and no production
control item or match data was changed. This is **not a cloud durability pass**.
Run under the existing application identity or another explicitly authorized writer:

```bash
.venv/bin/python scripts/check_assistant_cosmos.py seed \
  --scope <fresh-test-scope> --output var/assistant-cosmos-seed.json
.venv/bin/python scripts/check_assistant_cosmos.py verify \
  --scope <same-test-scope> --output var/assistant-cosmos-verify.json
```

The script requires existing private `COUNTERPRESS_COSMOS_*` settings and
`COUNTERPRESS_STORAGE=cosmos`. It uses an isolated `verify-assistant-*` partition,
retains the small test record for audit, and makes zero model calls. The fresh
process check uses recorded test timestamps to verify quota persistence.

## Final schema checks and real Cosmos verification

The subsequent broader Azure sample is preserved in
[the broad evaluation report](footie-agent-broad-azure.json). All ten factual
outputs matched the expected results, but only **7 of 9 eligible cases completed
through the agent** (8 of 9 raw query routes matched). Correct fallback answers
are not agent successes. Recent assists exceeded the casual answer sentence
limit, and a season comparison invented extra metrics not requested by the user.

Version 4 fixes these at the provider schema boundary: casual answers allow one
supporting sentence (analyst answers allow two), and extra metrics require an
explicit request or an inherited follow-up metric set. The independent intent
fixture stays unchanged. The evaluation's canonical reference questions now
include the authored metric labels so they satisfy the stricter read contract;
the numeric oracle still shares reducers and is not an independent data audit.

```text
.venv/bin/pytest -q tests/test_assistant_research.py tests/test_assistant_evaluation.py
113 passed in 21.84s

.venv/bin/pytest -q tests/test_assistant*.py
191 passed in 54.02s

.venv/bin/python scripts/evaluate_footie.py --azure --agent --case season_relative --max-attempts 2 --output var/footie-agent-v4-season-review.json
1 eligible agent case passed; 2 provider requests
```

The complete backend suite was rerun after the version 4 changes:

```text
.venv/bin/pytest -q > var/footie-agent-v4-backend-tests.log 2>&1
958 passed, 1 warning in 369.03s (0:06:09)
```

The warning is the existing Agent Framework experimental evaluator warning.
The version 4 source lock, remote Cosmos source hashes, `git diff --check`, and
literal private-configuration scan all passed. No frontend source changed in
this verification pass.

The [season pilot report](footie-agent-season-azure.json) is a targeted regression,
not a fresh full-suite pass. The broader sample used 18 requests and the pilot
used two; the persistent rolling-hour cap was reached and was not reset or
bypassed. A fresh version 4 broad live evaluation is still required before
hosted activation.

The local CLI account's earlier Cosmos 403 was resolved for verification by
using the **existing app managed identity**, without changing role assignments.
A temporary source overlay inside the existing app container ran the seed and
verification scripts in separate Python processes. Uploaded source hashes were
checked against the local files. The temporary files were removed; the running
server and app configuration were unchanged. An isolated verification record
is retained, and no production match/control records were changed.

[The real Cosmos report](footie-agent-cosmos.json) records:

- A real HTTP 409 create conflict; the duplicate was admitted once.
- Typed receipt restoration, including in a fresh process.
- Twenty reserved provider slots and persistent quota enforcement.
- Zero external model calls.

This closes the Cosmos admission durability gate. It does **not** verify model
managed-identity authentication, hosted agent inference, or the Event Hubs career
correction bridge. No new release has been published.

## Version 5 follow-up boundary and release preparation

After the evaluation allowance renewed, the [version 4 full Azure sample](footie-agent-v4-full-azure.json)
completed **9/9 eligible agent workflows**, but only **9/10 overall cases matched
the factual/intent oracle**. The remaining case, “And last season?”, became a
two-season comparison instead of changing the period of the previous statistic.
It produced a grounded answer to the wrong operation. This is a failed release
gate, not a passing fallback or an acceptable completion.

Version 5 constrains explicit period-only follow-ups to the previous operation in
both the provider schema and Python validation. This applies to statistics,
player comparisons, recent form and club leaders, including relative/named
seasons and the supported Chinese equivalents. Explicit new comparison requests
remain available. Tests also confirm rejection before a second paid request.

```text
.venv/bin/pytest -q tests/test_assistant_research.py tests/test_assistant_evaluation.py
135 passed in 24.32s

.venv/bin/pytest -q tests/test_deployment_guard.py
11 passed in 0.07s

.venv/bin/python scripts/evaluate_footie.py --azure --agent --case followup_season --max-attempts 2 --output var/footie-agent-v5-followup-review.json
Evaluation status: passed. Model cases: 1/1.
Model attempts: 2.
```

The [version 5 targeted Azure report](footie-agent-v5-followup-azure.json) verifies
the regression; it does not substitute for a fresh broad run. The full sample and
pilot consumed the renewed allowance (18 + 2 requests); it was not bypassed.
The Cosmos admission implementation is unchanged from its successful live test;
the earlier complete uploaded-package hashes apply to that earlier source state.

The manual deployment workflow now has an `assistant_workflow` input, defaulting
to `preserve`. Selecting `agent` requires Azure inference and Cosmos storage;
`structured_lookup` provides an explicit rollback to the previous workflow.
No workflow has been dispatched and no hosted configuration changed in this pass.
The final local backend run had one existing expiry test hit its real-time
deadline. The full workflow file passed on an isolated rerun; the failed full
run is preserved and is not reported as a clean pass:

```text
.venv/bin/pytest -q > var/footie-agent-v5-backend-tests.log 2>&1
1 failed, 980 passed, 1 warning in 337.73s (0:05:37)
# test_expiry_unconfigured_incomplete_and_historical_do_not_publish:
# expected expired; received timeout

.venv/bin/pytest -q tests/test_workflow.py
26 passed in 6.00s
```

A draft review PR can run CI while the live gate remains open. Do not merge and
enable agent mode on the strength of the targeted check alone.

## Remaining roadmap

1. The authored live-agent sample passed. Extend evaluation with unseen fan
   phrasing and human review; preserve failures and avoid population accuracy claims.
2. Add useful new tools (e.g. player contribution shares and explicitly defined
   club-wide form rankings) only with independent labels and coverage tests.
   Vague “best player”, tactical causes and unrestricted multi-step research remain
   unsupported; this release does not claim to answer them.
3. Exercise the already implemented career correction bridge in an isolated Azure
   test scope before enabling it in the main app. Verify durable correction,
   duplicate delivery, restoration and push/poll recovery end to end.
4. Live Cosmos admission verification is complete (see below). Move
   model authentication toward managed identity and add sanitized distributed
   traces. Runtime agent admission is implemented; legacy planner/narrator quotas
   remain process-local.
5. Deploy through exact-commit GitHub CI and the existing manual release workflow;
   verify desktop/mobile and revision invalidation on the hosted app. Stay within
   the existing US$75 project budget; no new Azure service is required by this stage.

## Reading map

- `backend/counterpress/assistant/research.py`: Agent Framework loop, transport
  bounds, runtime schemas and receipt validation.
- `admission.py`: shared quotas, leases and revision-aware receipt cache;
  `scripts/check_assistant_cosmos.py`: isolated real-service verification.
- `contracts.py`, `service.py`, `narrative.py`: typed query, deterministic reads,
  compound visuals and evidence-bound sentences.
- `api.py`: mode selection, admission, fallback and final revision check.
- `fixtures/assistant/questions.json`, `scripts/evaluate_footie.py`: authored
  intent cases and persistent, capped evaluation.
- `tests/test_assistant_research.py`: real framework with simulated Azure;
  invalid subjects, scope, metrics, repeated tools, narratives and correction race.
- `docs/reactor-review-context.md`: saved video analysis.

Microsoft's [function tool overview](https://learn.microsoft.com/en-us/agent-framework/agents/tools/?pivots=programming-language-python)
informed the tool boundary; implementation is checked against the locked SDK and
its actual request/response loop. The Reactor recording is design context, not
training footage or an imported backend.
