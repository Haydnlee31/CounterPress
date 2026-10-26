# Rolling match observations — local review, 26 October 2026

Implemented and reviewed locally. No deployment, new Azure resource, or Azure
model call was made for this change. The source control lock is now
`footie-intelligence-controls-v10-pinned-rolling-observations`; only the nine
reviewed backend additions/changes have different hashes. Dataset and evaluation
case files are unchanged.

## Changes reviewed

- `backend/counterpress/fan/observations.py`: exact trailing windows, evidence,
  admission thresholds and audience ranking.
- Fan service/API: bounded read-only observation snapshots, delivery ceilings,
  and graceful cancellation while buffering an aborted request body.
- `backend/counterpress/assistant/observation.py` and assistant contracts, API,
  service, planner and specialist context: recomputed source pins before/after
  inference; exact windows and comparison facts; unrelated questions retain their
  own scope.
- `frontend/src/gi/LiveObservation.tsx`, stylesheet and PlaySequence integration:
  completed-event requests, stale-response protection, one inset card, persistent
  dialog ownership and malformed-response handling.
- Frontend assistant context, request payload and launcher: pinned preferences
  and observation identifiers, with no automatic submission.
- New calculation/assistant/UI regressions, cross-fixture audit and browser check;
  README and feature guide.

## Verification commands and results

```text
.venv/bin/pytest -q
1684 passed, 1 warning in 381.62s (0:06:21)

cd frontend && npm test
Test Files  37 passed (37)
Tests       243 passed (243)

cd frontend && npm run build
tsc --noEmit && vite build
✓ built in 1.31s

.venv/bin/python scripts/verify_live_observations.py
status: passed
snapshots_checked: 676
observations_checked: 292
passing_decline: 116
player_involvement: 156
shots_increase: 20
local service median: 14.03ms; p95: 20.88ms
model_calls: 0; cloud_calls: 0

git diff --check
(no output; exit 0)
```

The backend warning is the existing experimental evaluation SDK notice. The
cross-fixture audit uses all four featured canonical matches and two audiences;
it independently reconstructs visible revisions and recounts the emitted facts.
Its latency figures measure this machine's local service calls, not production
network or concurrent-user performance. Observation totals include overlapping
windows and both audiences; they are not 292 independent tactical discoveries.

Browser checks use an isolated installed Chrome, the built interface and a
same-origin local server without Azure inference:

```sh
NODE_PATH=/Users/haydn/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules node scripts/test_live_observations.cjs http://127.0.0.1:8017
NODE_PATH=/Users/haydn/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules node scripts/test_footie_context.cjs http://127.0.0.1:8017
```

```text
PASS rolling insights browser: real fixture, one contextual card, paused/no-frame requests, exact observation handoff, rewind clearing, 2x full match, 1440/760/390/360px, no browser errors or Azure calls.
PASS Footie context: profile season, no automatic questions, source-time highlight handoff, Match Centre event revision, pause/return, focus restoration, mobile layout, no browser errors.
```

Screenshots are retained locally at `var/live-observation-desktop.png` and
`var/live-observation-mobile.png`. Checked widths: 1440, 760, 390 and 360 pixels.
Card text and controls stay inside their widget; the card replaces the visible
footer action, preserving both underlying conversation owners during updates.

The review found and fixed four integration issues: observation IDs initially
rejected their colon separators; an open dialog could unmount when cards changed;
malformed card data could crash rendering; and an aborted request body could
raise through the outer HTTP header middleware. Each now has a regression test.

## Remaining limits

The heuristics identify descriptive recorded changes, not tactical causes or
statistical significance. Analysis follows the replay's completed source events;
late outcomes can enter at the next completed-event cutoff. There is no video
perception or off-ball tracking. Corrections refresh insight evidence, but the
legacy Match Centre pitch payload does not rebuild corrected geometry. Live
Azure model routing for these new observation questions still needs a bounded
canary before publication; local tests exercise the structured path and fake
provider workflows. See [the feature guide](../live-observations.md).
