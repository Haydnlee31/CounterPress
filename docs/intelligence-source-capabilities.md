# Football intelligence: source capabilities and definitions

Audit date: 23 October 2026. Rules version: `football-intelligence-v1`.
Implementation: `backend/counterpress/assistant/intelligence.py`. This is a
local source audit, not evidence of hosted activation or football tracking.

## Featured sources

| Canonical match ID | Source | Events | Goals excluding own goals | Explicit start found for goal buildup | Important limits |
| --- | --- | ---: | ---: | ---: | --- |
| `wyscout-2058017` | Adapted archive | 1,462 | 5 | 1 (penalty) | No recipient IDs, recovery coverage or restart flags; provider-awarded assist links exist; carries are mapped source touches/accelerations with unknown outcome. |
| `wyscout-2058007` | Adapted archive | 1,682 | 5 | 0 | Same limits; neither teams' event adjacency nor a won duel proves possession was established. |
| `synthetic-32fe41c5d304ce68d7d9` | Legacy simulation | 1,267 | 4 | 3 | 700 recipient-linked completed passes and 195 recoveries; historical carry/recipient metric families remain excluded for compatibility with existing analytics coverage. |
| `career-showcase-southbank-redhaven` | Calibrated simulation | 1,448 | 5 | 2 | 773 recipient-linked completed passes, 215 recovery records, 116 controlled carry segments. Synthetic event geometry is available; continuous tracking is not. |

Counts reflect committed initial fixtures before revision overlays. All four
fixtures have stable canonical event IDs, occurrence order, actors, match/period
clocks, revision and availability fields. Archive availability equals occurrence
in the adapted dataset; it is not a measured original-provider delivery latency.

All listed sources support observed goal suffixes. A shot-only suffix is valid
but supplies no evidence of a longer buildup. Conservative partial coverage is
intentional: archive actions may not preserve enough semantics to establish
possession, even when a visual replay depicts a longer attack. Do not turn that
animation into observed evidence.

The fourth match's linked highlights are explicitly mapped in
`fixtures/personalization/highlights.json`; their `event_ids`, `goal_event_id`,
`match_id` and start/end clocks link to the canonical fixture. Other generated
highlights must use their existing canonical mapping rather than their display
titles. The standalone `last_gasp`, `one_touch` and `breakaway` preloaded
reconstructions are not imported by `personalization/imports.py`; they must not
inherit the career profiles or canonical match evidence merely because an alias
looks similar. Buildup inputs require one exact canonical match namespace.

## Reuse and compatibility

- `personalization.metrics.select_events` selects the latest available revision,
  removes retractions and orders occurrence time independently of delivery order.
  The new tools also enforce an occurrence cutoff and canonical actor/appearance
  validation, reject mixed matches and conflicting duplicates.
- Existing `reduce_record` owns assist credit, goal accounting and shot-assist
  definitions. Buildup contribution does **not** create, override or imply assists.
- `personalization.analytics` already supplies progression thresholds, continuous
  carry aggregation, heatmaps and coverage-family definitions. We do not introduce
  a competing progressive-pass threshold, touch count or continuous-carry metric.
- Existing analytics excludes incomplete source families. Involvement similarly
  returns null for archive recoveries and for noncalibrated carry/reception
  aggregates. Buildup can still describe explicitly observed individual segments,
  labelled as such.

## Buildup definition

`goal_buildup(fixture, events, event_id=..., cutoff=..., expected_revision=...)`
returns the currently visible selected goal and its observed same-team suffix.
It never silently chooses another goal. Own goals and non-goal selected events
return unavailable. A selected revision mismatch also returns unavailable.

Walk backward within the same period. A recorded established recovery or restart
is an explicit start. Earlier shots, challenges, opponent non-pressure actions,
unknown actions, uncertain carries and incomplete/unknown passes are barriers.
A known pass recipient or holder that differs from the next attacking actor also
breaks continuity: an unrecorded transfer is not invented.
A suffix after a barrier has an unknown start. Opponent pressure can remain in
the timeline as context but contributes neither an attacker nor possession loss.
A penalty is its own restart sequence. No pressure-based tactical causality is
inferred. `complete_possession` means the observed chain reaches such an explicit
start with known successful-pass recipients; it does not certify the source
captured every physical action. An explicit start can be known while the full
chain remains incomplete because recipients are missing.

- `completed_passes`: `complete` and `completed` outcomes in that suffix.
- `carry_count`: recorded carry segments, not continuous carries or touches.
- `participant_count`: distinct observed attacking actors and explicitly known
  successful-pass recipients; no inferred off-ball contributors.
- `observed_duration_seconds`: first attacking observation to shot release.
- `regain_to_shot_seconds`: that duration only when the explicit start is a
  recovery, never a restart or an inferred change in club possession.
- `net_progression_m`: shot-origin x minus first attacking observation-origin x,
  in attacking-direction-normalized metres on the 105 by 68 metre pitch. Null
  when either position is absent. Negative values are legitimate net retreat.

Occurrence is the release clock. Ball-flight time and delayed revision
availability never inflate buildup duration. The goal is visible only after its
outcome is available. Evidence includes stable match/event IDs, revision,
occurrence order, occurrence and availability clocks and original source reference.

## Involvement definition

`involvement(..., player_id=..., cutoff=..., window_start=...)` describes recorded
passes, completed passes, receptions with known recipients, carry segments,
shots and recoveries. It includes unlocated actions. It is not a physical touch
count, workload, distance run or positioning measure. Own goals are excluded from
shot counts. Restart recoveries and unsuccessful/unknown recovery outcomes are excluded from
recovery counts; confirmed outcomes are established, won, recovered or successful.

The team-share denominator is the same club's pass/carry/shot/recovery records
while the player was on the pitch within the chosen observation window. Pressure
and contested duels are not on-ball possession records for this measure. Null
share means there were no qualifying team observations. Missing recipient coverage
makes receptions unavailable rather than zero. Minutes use the fixture's declared
appearance basis (source minute precision for archive lineups); no estimated
tracking exposure is substituted. Rate comparisons must use compatible source
coverage and this definition, not the existing located-action denominator.

Completed-pass counts are **recorded successes**, not estimates for passes with
unknown outcomes. `coverage.pass_outcomes_complete` and
`coverage.unknown_pass_outcomes` describe the player's own passes;
`denominators.passes_with_known_outcomes` excludes unknowns. The response labels
this metric “Recorded completed passes.” Do not compare completion rates against
a baseline as though coverage were complete when this flag is false. Any team
pass with an unknown outcome also makes reception totals unavailable, since that
pass might conceal an unrecorded successful reception.

## Comparable windows

`compare_windows(..., club_id, period, start_ms, split_ms, end_ms, cutoff)` requires
adjacent equal-duration windows within a single period, with the end reached at
the availability/occurrence cutoff. Both windows are `(start, end]`. The default
minimum is five recorded on-ball actions per window; this is an eligibility
threshold, not a significance test. Insufficient observations return unavailable.

Counts and differences cover passes, completed passes, shots, recoveries and
recorded on-ball actions. Archive recoveries are null in both windows. No metric
is described as proof of a tactical change, improvement or causal mechanism.
Late corrections can alter a later observation of the same windows; every result
is explicitly scoped to its cutoff and evidence revisions.
Window coverage includes unknown-pass counts and completeness separately for
before and after. A difference in recorded successes with incomplete outcomes
does not establish a difference in actual completion totals or passing quality.

## Validation

`tests/test_intelligence_tools.py` independently authors a recovery, two passes,
a carry and a goal: ten seconds regain-to-shot, three participants, 66 metres net
progression. It includes duplicated deliveries, revisions/retractions, unknown
outcomes, restarts, source missingness, period boundaries and no-change window
controls, plus all 19 ordinary goals across the four featured fixtures.
Additional independent adversarial tests are maintained separately in
`tests/test_intelligence_adversarial.py`. No model or cloud calls are required.
