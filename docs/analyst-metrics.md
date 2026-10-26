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

## Grounded candidates and native agent packets

`build_candidates` connects typed, source-bound facts into a limited set of bilingual diagnostic readings. Supported families cover increased shots with box attempts, a shift to outside-box attempts, high event activity with little penetration, falling pass completion together with fewer final-third entries, recovered opponent passes with progression, recipient-linked recovery-to-shot sequences, and focused-player involvement. A transition goal uses the score **at that shot**, not a later replay score. An unknown finish is never described as a miss. Box membership never implies a measured increase in distance from goal. Candidate confidence is medium, and supported alternatives distinguish correlation from an invented tactical cause.

The native agents exercise selection and editorial judgment rather than writing unrestricted factual claims. Each of four role specialists chooses a supplied candidate ID or abstains; the Editor selects accepted roles and the lead. Both native runtime and product provider publish the exact canonical localized reading. Invented IDs, wrong-role selections, extra prose, or modified readings with otherwise valid references fail closed. This limits the range of novel language/insight to the implemented candidate families; it is not unconstrained video reasoning or a guarantee that model selection is optimal.

`build_dispatch_packet(snapshot)` includes at most two candidates per role (eight total), exactly their required metrics/events, score, meaningful metric labels, window definitions, method/basis metadata, language/depth/focus, and actual fixture period lengths. Supported cross-discipline references remain available—for example, a player contribution can cite recovery-to-shot duration. All citations must resolve. The full UI endpoint retains the broader metrics and spatial arrays. Proof-only derived scalars use `presentation=evidence_only` so they do not clutter the statistics grid.

The dispatch limit is24,000 characters and32,000 UTF-8 bytes. Required facts are never clipped to fit; overflow fails closed. The source snapshot retains no more than64 event references. Empty candidate sets abstain without a paid model call. Equivalent received-sequence ceilings normalize to the same snapshot identity, preventing unnecessary paid cache misses. Candidate text and facts are deterministic for English/Simplified Chinese and casual/analyst depth; player focus is honored only with real involvement evidence.

## Verification

`tests/test_analyst_candidates.py` adds independent semantic counterexamples: more shots does not establish better locations; a single final-third entry is not zero; a7.975-second equalizer must use its own score despite a later goal; the losing pass's intended recipient did not join the opponent attack; unknown shot outcomes and broken/restarted chains cannot invent a finish; language, complete comparison windows, actual period lengths and proof-only facts stay explicit. `tests/test_analyst_integration.py` exercises real packets through the native selector and product publication boundary, including invalid choices, changed prose, delayed corrections, source availability and stale sequence requests.

`tests/test_analyst_metrics.py` uses separately authored examples and expectations for 3–4–5 distance,50% known-outcome pass accuracy, authored108km/h flight, difficulty0.5875, period/window boundaries, duplicate delivery, delayed outcome/revision/retraction, own goals, opposing duel credit, unknown metrics, strict inputs, diagnostic thresholds, recipient-linked transitions, packet grounding and size. It also verifies real canonical full-time scores4–2,3–2 and2–2, both halves, and that no packet evidence exceeds its cutoff.

Continuous trajectory ingestion and calibrated physical tracking remain future work. Supplying a contract alone would not make the current archive measurements available; this release intentionally does not manufacture that data from animation.
