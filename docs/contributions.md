# Player contribution evidence — Stage 8, fifth increment

The first player-contribution rule detects an increase in a player's recorded
share of their team's high recoveries. Attribution goes only to the recovering
actor. A duel winner, nearby participant, or subsequent pass recipient receives
no recovery credit. This is a descriptive event count, not a player rating or a
claim that the player caused a team outcome.

## Run the independent controls

```sh
UV_CACHE_DIR=.uv-cache uv run --frozen python -m counterpress.contributions fixtures/contributions/increase.json --player eb04
UV_CACHE_DIR=.uv-cache uv run --frozen python -m counterpress.contributions fixtures/contributions/control.json --player eb04
```

Both controls have four Eastbridge high recoveries in each five-minute window.
The positive control assigns `eb04` one baseline and three current recoveries
(25% → 75%). The negative control assigns one in each (25% → 25%). `eb08` accounts
for the remaining recoveries. `eb09` wins all eight preceding duels but has zero
recoveries. Each feed has 48 events with independently tested ball and player
possession continuity. Expected actor IDs, fractions and eligibility are written
separately in `tests/expected_contributions.json`, which production never reads.

Add `--json` for typed evidence with full canonical source records and exact
event/revision references. `--team`, `--player`, `--windows START SPLIT END`, and
`--at` choose the subject and observation. The CLI accepts any valid public feed;
it does not consume generator evaluation labels.

## Rule and limitations

`player-high-recoveries-v1` reuses the existing high-recovery definition: established
open-play control at normalized attacking x ≥ 70 m on the 105 × 68 m pitch. Duels,
restarts and recoveries below that boundary do not count. All team events are in
the denominator; only the selected actor's events are in the numerator.

Default eligibility requires all of:

- At least three team high recoveries in each window.
- At least three selected-player high recoveries in the current window.
- An increase of at least two selected-player recoveries.
- An increase of at least 25 percentage points in the player's team share.

The policy is typed and included in evidence. Counts and shares must both rise;
a shrinking denominator alone cannot create an eligible result. A zero denominator
has an undefined share, not a zero share. Small samples return `insufficient_sample`;
other nonqualifying results return `below_threshold`. This first rule detects
increases only, not player decline or relative rankings.

Windows must be adjacent, equal in duration, fully observed, and in one period.
They exclude the start and include the end. Default windows are `(48:00,53:00]`
and `(53:00,58:00]`. Player/team membership is checked against the feed roster.
Canonical revisions are selected by availability before attribution. Evidence
validation recomputes actor attribution, fractions and eligibility from its source
records and rejects inconsistent summaries or future/mismatched records.

Roster membership does not establish minutes played. No substitution, tracking,
off-ball activity, role adjustment, causal credit, or per-minute normalization is
inferred. Repeated observations in a deliberately small control are not population
calibration. The reported thresholds are explicit demonstration policy.

## Corrected actors and historical evidence

```sh
UV_CACHE_DIR=.uv-cache uv run --frozen python -m counterpress.contributions fixtures/contributions/increase.json --player eb04 --updates fixtures/contributions/actor_corrections.json --at 58:10
```

| Availability cutoff | `eb04` baseline → current | Decision |
| --- | --- | --- |
| 58:00 | 1/4 → 3/4 | Eligible |
| 58:05 | 1/4 → 2/4 | Below threshold |
| 58:10 | 1/4 → 1/4 | Below threshold |
| 58:15 | 1/4 → 3/4 | Eligible |

Corrections transfer the actor of `c3-recovery`, then `c2-recovery`, to `eb08`,
and finally restore both. Paired pass actor/recipient and subsequent actor changes
preserve player possession continuity. The team total stays four; shares are
recomputed for each player. Exact retransmissions do not double-count events.
Seeking to 58:00 still uses original actors and revision 1.

## API integration

For any existing replay scenario, use its persisted source history:

```sh
curl -sS 'http://127.0.0.1:8000/api/scenarios/increase/players/eb04/contribution?team_id=eastbridge&at_ms=780000'
```

The response is `PlayerContributionEvidence`, with `Cache-Control: no-store`.
Unknown scenarios return 404; unknown player/team combinations, unfinished
comparisons and cutoffs beyond the available history return 422. History failures
return 503 without exposing internal configuration. The original recovery scenario
has only one baseline team recovery, so this example correctly reports insufficient
sample under the new policy; it does not substitute the new positive control.

The two control feeds are also available as browser scenarios through
[durable contribution publication](contribution-publication.md). The candidate API
recomputes from the durable source journal, including corrections, and works after
restart without fixture files once history is seeded. Its response is candidate
evidence, rather than a frozen publication or viewer card. The publication and
snapshot routes expose those separately. Existing recovery and possession stories
keep their current behavior.

## Verification and next work

The new tests check independent actor partitions, continuous controls, exact
coordinate/window/policy boundaries, denominator effects, zero samples, membership,
forged evidence, late corrections, historical API cutoffs, restart durability and
CLI parsing. The complete backend suite and both required GitHub Actions checks
must pass before merge. Exact local output is recorded in [progress](progress.md).

Durable player-contribution publications, bilingual replay cards and per-player
cooldowns are now implemented in [the next increment](contribution-publication.md).
Best next move: evidence-linked match recaps. No Azure action is needed.
