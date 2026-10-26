# Analyst Mode evidence and metric definitions

Analyst Mode is a separate read-only consumer of canonical event history. `build_snapshot(career, match_id, AnalystRequest)` returns team totals, comparable windows, player totals, spatial views, diagnostic signals, and bounded event citations. It calls no model. The three initial supported IDs are the same matches as Match Centre; the fourth career showcase is not silently converted to GI tracking.

## Time, revisions and identity

The request contains a strictly typed integer period (1 or 2), milliseconds within that period, optional received-delivery ceiling, English or Simplified Chinese, casual/analyst depth, and an optional player in this match's roster. Invalid periods, out-of-period clocks, outside players and delivery ceilings beyond received history are rejected.

The service takes a consistent store snapshot, applies the delivery ceiling **before** selecting the latest available event revision, removes retractions, and excludes occurrence times after the playback clock. A late correction cannot leak into an earlier view. All selected canonical events, their revision contents, the fixture, request and metric version contribute to the SHA-256 snapshot ID. Future unobservable deliveries do not change that identity.

`prefix` is everything visible through the clock. `current` is the trailing five minutes in this half, and `previous` the five minutes immediately before it. Windows exclude their start and include their end. Early-half windows are shorter and never borrow events from the previous half. Trend signals require complete comparison windows. Shot/pass geometry uses 105×68 metres with the acting club attacking positive x.

## Metric coverage

Every row has a stable ID, key, window, club/player scope, label, unit, method, basis, value and availability. Coverage numerator/denominator accompanies quantities whose input can be missing. Missing values remain `null`, not zero. Team goals include opponent own goals; individual scorer goals do not. Existing canonical reducers supply assists, key passes, saves and both sides' duel wins.

| Family | Output and interpretation |
|---|---|
| State | As-of score, period, clock, canonical roster and delivery watermark. |
| Team/player actions | Passes/completions/unknown outcomes, shots/on target, goals, duels won, recoveries, pressure events, assists, key passes and saves where source coverage permits. Recorded actions/on-ball actions are not actual ball touches. |
| Accuracy | Completed passes divided by **known-outcome** passes; unknown outcomes stay in a separate count and lower coverage. |
| Progression | Completed-pass distance and positive forward progression; completed passes crossing x=70; passes entering the 16.5m penalty area; signed forward carry progression from controlled segments. No whole-player distance estimate. |
| Possession | Share of pass/shot/controlled-carry event actions. Explicit `event_share_proxy`; not elapsed possession time. Possession seconds unavailable. |
| Spatial views | 12×8 event-location heatmaps, pass endpoints/distances/progression, and shot locations/distances/technique. These are on-ball events, not off-ball occupancy or camera measurements. |
| Chances | Authored source xG and a **separate uncalibrated** location-only estimate. The latter uses goal angle, distance and header indicator, with versioned documented coefficients; it is not fitted to a scoring dataset. Missing authored xG is never filled with this estimate. |
| Pass difficulty | Authored `1-completion_probability`, separately from a versioned length/progression heuristic. The heuristic has no pressure input and is not a fitted completion probability. |
| Speed | Fastest pass/shot speed only when explicit authored flight time and endpoints exist, visible after arrival. Basis `authored_physics`; no player speed or measured camera speed claim. |
| Rhythm | Distinct on-ball actions per minute in each window. Does not double-count the reference implementation's internal contributions. |
| Momentum | Uncalibrated threat balance from forward completed passes, controlled carries and geometric shot estimates. Recomputed per immutable window; no hidden mutable smoothing state. |
| Turnovers/chaos | Only immediate incomplete pass→opponent recovery within three seconds, same half and no restart. Chaos is a bounded heuristic from these verified turnovers per minute. Archives without recovery coverage remain unavailable. |
| PPDA/discipline | Tackles, interceptions, fouls, cards, corners and conventional PPDA remain unavailable: canonical generic duels/unknown events do not establish them. |
| Running | Player distance, top speed, sprints and off-ball occupation remain unavailable. Animated replay positions are not consumed as tracking. |
| Ratings | No fabricated cross-position player performance rating; individual statistics are available instead. |
| Auto-event evaluation | Precision/recall unavailable because no video detector or labeled detection run feeds this endpoint. Runtime agent latency/cost/status belong to orchestration monitoring, not match evidence. |

The actual existing archive `other` events are unknown outcomes (plus an explicit own goal in one match), so they cannot safely be decoded as cards or fouls. Archive `on_target` shots also cannot automatically be assigned as a goalkeeper save.

## Insight signals and reference trigger coverage

Signals combine observations: increasing shot volume **and** box locations; repeated outside-box attempts; action dominance without shots/final-third entries; a significant pass-completion decline across adequately sampled complete windows; or an opponent pass loss→recovery→recipient-linked shooting sequence. Focused-player activity must include a shot. Text describes a supported consequence and a next observable check, not a coach's intention or guaranteed future outcome.

All 15 reference trigger families are represented in `triggers`. Goals, pass combinations, geometric difficult passes, authored-xG big chances, period boundaries, threat/tempo/control/turnover changes, stat checks and match-pass milestones have explicit conditions. Cards/substitutions/pressure-spike subtype triggers are unsupported where canonical evidence cannot establish them. Trigger availability is separate from active status, and an active trigger never itself authorizes a model call. No career milestone is inferred from match-only counts.

## Agent packets

`build_agent_packet(snapshot, role)` provides one specialist's supporting context. `build_dispatch_packet(snapshot)` provides a single bounded all-role packet for the native Foundry workflow. It explicitly pairs current/previous measurements, includes player statistics, score and window definitions, and carries concise heuristic definitions. One strongest signal per role is prioritized; all its metric/event citations remain resolvable. Most spatial arrays stay in the full UI snapshot. Normal packets contain approximately48 scalar/supporting metrics and32 event records; no more than64 event references exist in the source snapshot. Serialized dispatch context is limited to24,000 characters; optional uncited event context can be removed, but required citations/values cannot. Overflow fails closed rather than clipping facts.

Roles are `chance`, `defence`, `control`, and `players`. Player rows belong to `players`; the dispatch selects up to three recently involved players, including a chosen focus. This selection is not a performance rating. Neither language nor model-generated commentary changes the deterministic numeric facts.

## Verification

`tests/test_analyst_metrics.py` uses separately authored examples and expectations for 3–4–5 distance,50% known-outcome pass accuracy, authored108km/h flight, difficulty0.5875, period/window boundaries, duplicate delivery, delayed outcome/revision/retraction, own goals, opposing duel credit, unknown metrics, strict inputs, diagnostic thresholds, recipient-linked transitions, packet grounding and size. It also verifies real canonical full-time scores4–2,3–2 and2–2, both halves, and that no packet evidence exceeds its cutoff.

Continuous trajectory ingestion and calibrated physical tracking remain future work. Supplying a contract alone would not make the current archive measurements available; this release intentionally does not manufacture that data from animation.
