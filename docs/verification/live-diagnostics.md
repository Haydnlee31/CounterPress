# Football explanations — local review, 26 October 2026

This revision addresses the feedback that the first observation cards only
restated statistics. A candidate now needs an additional football diagnostic
before publication. Its original counts remain supporting evidence. The earlier
[observation review](live-observations.md) describes the initial implementation.

## What changed

`fan/interpretation.py` evaluates shot location and outcomes, verified regain-to-shot
chains, failed-pass consequences, long-pass failures, and the contribution of a
followed player. It adds score context at the exact cutoff. Meaningful chance
consequences rank ahead of generic involvement. Unsupported candidates are silent.

The assistant's observation projection includes diagnostic facts, separate
evidence, player/opponent attribution and the correct observation window. Its
narrative validator requires the diagnostic explanation to survive model
selection. The UI opens with “What is driving this change?” and keeps its existing
compact layout. No data was regenerated and no new cloud service was added.

Two examples from the existing Eastbridge–Northport match:

- Around 14 minutes, two of Northport's three misplaced passes start in their own
  half. One is followed by Eastbridge's completed pass from that half, within five
  seconds and with matching mirrored endpoint/start positions. This supports a
  territorial consequence, without claiming an unobserved pressing tactic.
- Around 61 minutes, Eastbridge's increase in shots includes two attempts inside
  the penalty area, versus none in the preceding window. The explanation concerns
  the location of the chances, without inventing an expected-goals value.

## Verification

```text
.venv/bin/pytest -q
1730 passed, 1 warning in 336.55s (0:05:36)

.venv/bin/pytest -q tests/test_observation_interpretation.py
40 passed

.venv/bin/pytest -q tests/test_observation_interpretation.py tests/test_observation_assistant.py
65 passed in 22.20s

cd frontend && npm test
Test Files  37 passed (37)
Tests       243 passed (243)

cd frontend && npm run build
✓ built in 2.31s

.venv/bin/python scripts/verify_live_observations.py
676 snapshots checked; 133 qualified observations across four matches
85 player involvement; 32 passing decline; 16 shot increase
Local service median 15.63ms; p95 22.42ms
0 model calls; 0 cloud calls

NODE_PATH=/Users/haydn/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules node scripts/test_live_observations.cjs http://127.0.0.1:8017
PASS rolling insights browser: real fixture, one contextual card, paused/no-frame requests, exact observation handoff, rewind clearing, 2x full match, 1440/760/390/360px, no browser errors or Azure calls.
```

The cross-match audit independently recounts the original comparisons and checks
that every diagnostic source is a visible, unretracted revision. The 40 separately
authored diagnostic cases test the meaning: identical shot totals with different
locations, known versus unknown recipients, intervening actions, restarts, time
and spatial boundaries, missing locations, partial appearances, future goals,
goal retractions, diagnostic correction and preference-aware ranking.

The 133 observations include overlapping windows and two audiences; they are not
133 independent discoveries. Of these, 71 describe deeper player involvement,
11 link a player to shooting moves, 16 identify long-pass failures, 16 identify
more box shots, two link passing errors to opponent shots, 14 identify spatially
linked territorial handoffs, and three identify final-third entries.

The evaluation source lock is
`footie-intelligence-controls-v11-supported-football-diagnostics`. Numeric windows,
diagnostic evidence and earlier score context are all pinned before and after
inference. Unsupported tactical causes remain unsupported: this is an event-based
diagnostic layer, not learned video understanding or proof of off-ball intent.
No paid Azure canary or human usefulness study was run in this local revision.
