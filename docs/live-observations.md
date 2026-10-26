# Playback-synchronised match observations

Match Centre now offers one contextual insight beneath the pitch when the
recorded action supports it. It works in selected sequences and full-match
playback. The original replay footer remains when no observation qualifies.
The feature does not add navigation tabs or playback toggles.

## How it works

```text
Canonical events + revision journal
                ↓
Completed replay action → exact source-match cutoff
                ↓
POST /api/fan/matches/{match_id}/observations
                ↓
Visible revisions → rolling windows → supported football diagnostics → ranking
                ↓
One card in the replay footer
                ↓ only when the viewer opens Footie and sends a question
Pinned observation → existing grounded assistant → verified explanation
```

Calculation uses the latest visible revision of each event, subject to both the
source delivery ceiling and revision availability time. Retracted and future
events cannot contribute. Each comparison excludes the window start and includes
its end. Windows end at the exact completed-action cutoff and never cross
half-time. There must be six minutes of the current half before a complete
comparison is possible.

Candidate detection starts with these descriptive changes:

| Observation | Admission rule |
| --- | --- |
| Increase in shots | At least three shots in the current three minutes, at least two more than the preceding three minutes; own goals excluded. |
| Drop in pass completion | At least ten passes in each window, every pass outcome known, and a fall of at least 15 percentage points. Counts and denominators accompany the percentage. |
| Followed-player involvement | At least five recorded on-ball actions now, at least three more than before; only a followed or explicitly focused player is considered. |

Each club must also have at least five recorded on-ball observations in each
window. Favorite clubs, focused players, and metric preferences influence the
ranking. These thresholds are reviewed product heuristics, not significance tests
or learned measures of momentum. The card states the actual change without
inventing a tactical cause.

### Explaining the football behind the change

The count thresholds now nominate candidates; they no longer suffice to publish
an insight. A second evidence pass must explain a consequence or distinguish
different kinds of change. Its explanation leads the card and the Footie answer;
the original counts and exact windows remain supporting evidence.

- A shooting surge can mean more attempts inside the penalty area, shots still
  coming entirely from outside it, more efforts on target, or a verified series
  of recoveries followed by quick shots. These receive different explanations.
- A passing decline can be traced to failures on long passes, failed passes
  followed by an opponent's regain and shot, or deep errors followed by a
  spatially linked opponent pass in the attacking half.
- A followed player's increased involvement can be connected to shooting moves,
  completed passes entering the final third, or activity concentrated in their
  own half. A substitute's partial exposure is not compared with a full window.
- The score at the selected cutoff provides match context. Corrections to an
  earlier goal invalidate that context even if the goal lies outside the rolling
  windows.

Shot chains require known pass recipients and confirmed carries/recoveries, stop
at opponent actions or uncertain transfers, and span at most 15 seconds. A failed
pass must precede the opponent recovery by at most three seconds, and the whole
failed-pass-to-shot path by at most 15 seconds. Restarts do not become regains.
The simpler territorial handoff requires the very next non-pressure action to
be an opponent completed pass within five seconds, with its start within five
metres of the failed pass's mirrored endpoint. Unknown carries and intervening
actions break that link.

“Long” means at least 30 metres between observed pass endpoints, not intended
distance. Final-third entries cross x=70 through a completed pass. The penalty
area uses x≥88.5 and 13.84≤y≤54.16 on the existing 105×68m attacking-normalized
pitch. More shots inside the area are not presented as a measured improvement in
expected goals. Concrete chance consequences outrank increased activity alone.

Each diagnostic supplies its own facts and evidence references, including the
opponent when relevant. The assistant must retain the diagnostic claim when
selecting a narrative; it cannot reduce the answer back to a restated count.
Candidates without this additional support are suppressed.

Every observation has a stable semantic ID and a fingerprint covering its exact
windows, evidence, wording, preferences, and rule version. Results replace the
previous snapshot, including replacement with an empty list. A disappearing or
corrected observation is not kept as an append-only claim.

## Timing and interaction

- Fetch on completed source-event changes and relevant revision notifications,
  not on animation frames. Rapid changes are coalesced for 120 ms.
- Preserve a labelled earlier card during a short forward refresh (no more than
  15 seconds of source time). Backward seeks, half changes, match changes,
  preference changes and revisions invalidate the displayed context immediately.
- Abort obsolete requests and ignore late responses. Hidden playback does not
  fetch. Paused playback makes no periodic observation requests.
- “Ask Footie why” pauses playback and freezes the exact cutoff, delivery ceiling,
  preferences, observation ID and fingerprint. Opening the drawer does not submit
  a question. The assistant checks the pin before inference and again before
  returning an answer; changed records require a fresh observation.
- A question about the selected observation uses its three-minute comparison.
  Unrelated questions retain their normal tools and scope; the old ten-minute
  comparison must not silently replace the selected passage.

## Local verification

No new Azure resources or production limits are required. The feed uses
deterministic accounting and makes no model calls. The existing user-initiated
assistant remains the optional explanation path.

```sh
.venv/bin/pytest -q tests/test_live_observations.py tests/test_observation_assistant.py
.venv/bin/python scripts/verify_live_observations.py
cd frontend
npm test
npm run build
```

`scripts/verify_live_observations.py` checks every featured match at minute
intervals for two audiences and independently recounts all emitted evidence. Its
local output is `var/live-observations-audit.json`. Browser validation is in
`scripts/test_live_observations.cjs`; run against a local preview with Azure
inference disabled, using the installed Playwright runtime. It covers actual
fixture data, narrow screens, the assistant handoff, rewind, and request behavior.

For a same-origin preview of the built interface, run from the repository root:

```sh
.venv/bin/python scripts/run_footie_local.py --port 8017
```

Open `http://127.0.0.1:8017/?match=wyscout-2058017#gi`, then choose **Moments**.
Around 14 minutes, Northport's deep passing errors and Eastbridge's next action
are one useful example; the exact counts follow the completed-action time. Use **Watch
full match** to see observations appear as the replay advances. Opening minutes
and uneventful passages intentionally remain quiet. The command above uses local
structured answers, with no Azure inference. Keep the same-origin preview for
assistant testing rather than changing the assistant's origin protection.

## Boundaries of this increment

The source remains the application's canonical event datasets and supported
revision ingestion. This is replay-synchronised event analysis, not automatic
analysis of uploaded or live broadcast video. The existing Match Centre pitch
still animates its preloaded event payload; revision-aware observation refresh
does not turn that legacy payload into a live tracking feed.

No tracking-derived positioning, physical pressure, off-ball runs, measured player
speed, trained expected-threat model, or causal tactical diagnosis is introduced.
Recorded actions are not all player touches. A sparse or unchanged passage can
correctly produce no card. The local checks verify accounting, timing and
integration; they do not establish tactical predictive accuracy or production
load capacity.
