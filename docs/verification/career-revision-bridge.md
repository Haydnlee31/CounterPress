# Career revision bridge verification — 21 October 2026

Local implementation only. No hosted deployment, new resources, Azure requests
or paid model calls were made for this verification. The broad Azure question
rerun remains pending: the persistent evaluation ledger still held 20 attempts
within its hourly window. It was not reset or bypassed.

## Commands and observed results

```text
$ .venv/bin/python scripts/check_career_bridge.py
{
  "status": "passed",
  "profile_and_footie_goals": [
    75,
    74,
    75
  ],
  "durable_generations": 2,
  "duplicate_deliveries": "ignored",
  "restart": "passed",
  "azure_calls": 0,
  "model_calls": 0
}

$ .venv/bin/pytest -q tests/test_career_streaming.py
28 passed in 32.74s

$ .venv/bin/pytest -q
886 passed, 1 warning in 146.61s (0:02:26)

$ npm --prefix frontend test
Test Files  30 passed (30)
     Tests  176 passed (176)
```

The backend warning is the existing experimental editorial evaluator warning.
The final dataset-replacement refresh refinement was then checked with:

```text
$ npm --prefix frontend test -- --run src/football/revisions.test.tsx src/assistant/Footie.test.tsx src/football/FootballHub.test.tsx src/App.test.tsx
Test Files  4 passed (4)
     Tests  32 passed (32)

$ npm --prefix frontend run build
✓ 305 modules transformed.
✓ built in 835ms
```

`git diff --check` passed. The editorial source lock matches the reviewed backend
files (`grounded-footie-career-revisions-v1`). Comparing changed/new deliverable
files against private key/token/endpoint values in local configuration found no
matches; no private values were printed.

## What was exercised

- Independent writer and reader instances, SQLite restart, and per-instance
  materialized career indexes.
- Cosmos transactional double with concurrent creation/ETag conflict and rebuild
  from the winning revision; failed atomic writes cannot partially alter the index.
- Two concurrent SQLite writers without lost commits.
- Duplicate and out-of-order revisions, later restoration, causal milestone
  withdrawal, roster/identity/routing/dataset rejection, and atomic invalid batches.
- Commit-before-notify-before-checkpoint; retries after publish failure without
  double-counting. Storage outage retries without quarantining valid data.
- Fail-closed API reads after shared storage failure; sanitized errors.
- Independent API/Footie views update together, including a correction committed
  during narrative selection. Original-source replay returns 409 after correction.
- Receive-only dataset-scoped Web PubSub negotiation.
- Bounded journal capacity and refusal to silently discard local-only revisions
  when connecting an existing index to the shared journal.
- Browser push is only a hint; a successful durable version read is required.
  Wrong scopes, older versions and late responses after cleanup are ignored.
- Stale resource requests are aborted, unaffected replay resources stay mounted,
  and an actual dataset replacement refreshes registry metadata too.
- Footie clears stale answers/cancels pending replies without automatically asking
  the model again.

## Actual browser check

An isolated local server on port 8018 used
`var/bridge-browser-20261021.sqlite3`, separate from the ordinary preview index.
Headless Chrome loaded Clubhouse and Footie through the real HTTP API. The script
changed the shared journal using a separate Python process and waited for the
normal browser revision heartbeat; it did not inject a fake UI revision event.

```text
{
  "status": "passed",
  "answer_goals": [75, 74],
  "restoration": 75,
  "automatic_assistant_requests": 0,
  "profile_tab_preserved": true,
  "page_errors": []
}
{"restored_goals":75,"analytics_loaded":true,"mobile_horizontal_overflow":false}
```

Confirmed the restored Clubhouse tile displays 75, statistics widgets finish
loading, and the 390px viewport has no horizontal page overflow. Screenshots and
the browser script/results are local ignored artifacts under `var/`.

This verifies real browser polling and offline lookup behavior. Cloud Web PubSub
and Cosmos/Event Hubs availability/RBAC are not proven by these checks. No claim
is made that legacy Matchday or Match Centre animations have been regenerated
from career corrections; those are still separate source contracts.

## Post-integration question regression

```text
$ .venv/bin/python scripts/evaluate_footie.py --output var/footie-after-career-bridge.json
Evaluation status: passed. Model cases: 0/0.
Model attempts: 0. Report: var/footie-after-career-bridge.json
```

All 58 authored cases passed final intent/evidence/narrative/anchor checks. Raw
local intent was 57/58; the intentionally incompatible career-in-replay question
was correctly rejected by the server scope validator. This is an offline
regression, not a replacement for the pending fresh ten-question Azure sample.
