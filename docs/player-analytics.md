# Clubhouse player analytics

Open <http://127.0.0.1:8017/#football>, choose a player, and stay on **Overview**.
The period selector applies to every chart and statistic. These charts are computed from the data layer and do not require model calls.

## What a fan can explore

- **Heatmap:** smoothed action density, an optional exact zone-count view, and
  involvement split between the defensive, middle and attacking thirds.
- **Shooting:** all located attempts, goals or on-target attempts; select a marker
  or use the keyboard-accessible shot picker for date, time, outcome and xG.
- **Passing:** aggregated routes, filtered by completion or progression. The top
  32 routes are drawn; the displayed percentage says how much of the selected
  volume they represent.
- **Ball winning:** the locations of successful ground challenges and recoveries.
- **Position profile:** six role-relevant percentile bars against players in the
  same library, position and selected period, with at least 900 minutes.
- **Recent form:** the last ten appearances, selectable between goals, assists,
  xG, passing or challenges; goalkeepers start with saves.
- **Player statistics:** categories, text search, total/per-90 selection, and
  expandable definitions and coverage. Percentages and means stay percentages
  and means when per-90 mode is selected.

## Product references

[FotMob's player profile](https://www.fotmob.com/en-GB/players/862608/kaoru-mitoma)
combines shot maps, heatmaps and role-relative traits. That informed the separation
between pitch activity and a compact position profile.

[Sofascore's map introduction](https://www.sofascore.com/news/introducing-sofascores-new-maps-a-smarter-way-to-read-the-game)
shows how separate passing and defending maps can make spatial information easier
to read. Its [player comparison guide](https://www.sofascore.com/football/player/compare)
also groups statistics by football responsibility. We use an original interface,
our existing fictional identities and our own event ledger; no assets or player
records were copied from these sites.

[Wyscout's progressive-pass definition](https://dataglossary.wyscout.com/progressive_pass/)
informs the 30/15/10-metre thresholds. Our implementation compares Euclidean
distance to the centre of goal and explicitly documents intended versus recorded
endpoints. [Shot assists](https://dataglossary.wyscout.com/shot_assist/) informed the
creation view; CounterPress's direct-assist chain rules remain authoritative.

## Data and accounting

`backend/counterpress/personalization/analytics.py` is an additive reducer over the
existing validated ledger. It does not regenerate matches, modify goal/assist
counts, add fake tracking, or change stable player IDs. Initial per-match reductions
are stored in `fixtures/analytics/players.json.gz`, with compressed-file checksum,
ledger checksum, reducer checksum and per-match event digests. The API refuses a
stale or tampered artifact. This keeps profile requests from re-simulating whole
careers.

`GET /api/data/players/{player_id}/analytics?season=2026-27&before=2026-10-20T00:00:00Z`
is read-only and returns `Cache-Control: no-store`. The same date/season semantics
as career profiles apply. A revised match or an availability cutoff before all
initial deliveries bypasses its cached reduction. Peer cohorts receive the same
filters and corrections. Unknown IDs return 404; invalid timestamps return 422.

Definitions that matter:

- All coordinates use a **105 by 68 metre pitch**, attacking right. The opposing
  participant's challenge location rotates both axes before entering their map.
- Heatmaps count **recorded action origins**, not off-ball occupancy or every
  physical touch. Smoothing is presentation over a 12×8 grid; the exact-count view
  retains those bins. Box actions are therefore not labelled conventional touches.
- Pass routes use 6×4 origin/destination zone centres. Lines represent aggregate
  routes, not the exact path of any individual pass. Unknown outcomes remain
  separate and do not count as failed passes.
- Long passes are at least 32m. Final-third and box entries require a completed pass
  crossing into the area. Forward/backward passes use a ±5m longitudinal threshold.
- Contiguous carry segments join only for the same player and period, within ten
  seconds and matching endpoints. Restarts and intervening non-carry actions end
  the run. Progressive carries use the same distance-to-goal thresholds as passes.
- Shot assists require a direct completed-pass link, at most 15 seconds, no
  intervening challenge/restart/turnover, and no more than 10m of carrying. xA is
  the sum of the linked shots' xG (expected assisted goals), not Opta's distinct
  pass-based xA model. Imported provider-awarded assists remain authoritative.
- Goals above xG use **goals on the xG-covered shots** minus xG. Expected completion
  and completion above expected likewise share the same covered pass set.
- Rates use covered minutes, not minutes from matches where the underlying metric
  was unavailable. Save percentage excludes own goals from its shot denominator.
- Speed averages use authored ball-flight geometry and are labelled **estimated**.
  They are not measured player speed, radar shot speed or tracking telemetry.
- Percentiles use pooled exposure-based rates, same-position peers, a 900-minute
  minimum and at least five eligible players. Ties use midrank. They are not a
  global professional-player ranking or overall quality rating.

## Coverage and limits

The registry defines 71 statistics. Three definitions—headed shots, headed goals
and woodwork—are withheld because the current generator/imports do not classify
those reliably. Outfield profiles omit the five goalkeeper statistics. Thus the
usual visible library has **63 outfield statistics or 68 goalkeeper statistics**;
empty scopes show no available observations rather than fabricated zeroes.

Continuous running distance, sprint counts, aerial duels, fouls/cards, distinct
interceptions/tackles/clearances, and post-shot xG/goal prevention remain future
telemetry work. The [extended audit](verification/player-position-audit.md)
originally found eight positional flags and 16 club-share flags. The subsequent
[spatial recalibration](verification/spatial-recalibration.md) rebuilds the
population and maps: all 136 eligible position/metric checks and all independent
cohorts now pass. One original club-share flag remains explicitly adjudicated as
source-supported team style; it has not been hidden or changed to a numerical
pass. Model diagnostics, source-limited goalkeeper comparisons and unsupported
metrics retain their coverage limits. Internal accounting does not establish
external validity for every statistic.

The interface keeps definitions behind expandable statistics and a small footer
section. It does not show raw JSON or synthetic-data banners in the main view.

## Build and verification

From the repository root:

```sh
.venv/bin/python scripts/build_player_analytics.py
.venv/bin/pytest -q
npm --prefix frontend test
npm --prefix frontend run build
```

Rebuild the analytics artifact after changing the ledger or reducer. Verify the new
artifact before restarting a server; the running service caches its initial index.
Do not silently use a stale artifact. The generator and calibrated ledger remain
separate and unchanged by this command. See the [verification report](verification/player-analytics.md).
