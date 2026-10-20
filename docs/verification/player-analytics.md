# Player analytics verification — 20 October 2026

Local implementation complete. The calibrated model, ledger and player registry
are byte-for-byte unchanged from the verified position-calibration release.
No push, deployment, Azure resource change or paid model call was made.

## Exact commands and results

From the repository root:

```sh
.venv/bin/python scripts/build_player_analytics.py
```

```text
Indexed 200 matches
Indexed 400 matches
Indexed 600 matches
Indexed 800 matches
{"status": "built", "matches": 844, "compressed_bytes": 7159180}
```

Every historical match is reproduced through `DataStore.original`, which checks
its canonical event digest before deriving the analytics. All 844 matches are
indexed. The materialized artifact is 6.83 MiB compressed and has a separate
manifest; original career fixtures are not overwritten.

```sh
.venv/bin/pytest -q
```

```text
702 passed, 1 warning in 77.35s (0:01:17)
```

The warning is the pre-existing experimental evaluation-library notice. The
source lock is versioned `player-analytics-v1` for offline/mocked controls; the
original paid pilot is unchanged.

From `frontend/`:

```sh
npm test
npm run build
```

```text
Test Files  27 passed (27)
Tests  162 passed (162)
Duration  8.61s
✓ built in 953ms
```

```sh
git diff --check
```

No output; exit 0.

## Meaningful checks

The thirteen new backend tests use independent hand-written event sequences for:
progression/box boundaries; matched xG-goal accounting; xA chain interruption;
unknown pass denominators; coverage-aware per-90 values; opposing challenge
coordinate rotation; drawn challenges; first-half added time; continuous carries;
restart exclusion; and withholding unsupported shot classifications.

Integration checks cover all 44 featured players: goals, assists, passes, completed
passes, shots and challenges reconcile with existing career totals. Heatmaps sum
to located-action counts, shot maps reconcile with spatial shot counts, timing
bins reconcile with goals, and percentage/percentile bounds hold. Further tests
cover season/date scopes, no future-match leakage, revision/retraction effects,
historical availability, checksum failures, API validation and no-store headers.

Six frontend tests cover shot filtering and keyboard selection, route filtering,
per-90 counts versus unchanged percentages, coverage explanations, search/category
empty states, stale-response withdrawal, retry, and goalkeeper-first ordering.
Existing profile/favorites/history/comparison tests continue to pass.

## Actual browser and HTTP checks

The local production build was tested in Chrome at its normal **1470px viewport**
and at **390×844px**. Neither had horizontal document overflow; the temporary
viewport override was reset. The mobile pass caught a select-colour conflict,
which was fixed and rechecked (light text on dark green).

Verified in the UI:

- Mateo Cross's career view: 140 matches, 80 goals, 466 located shots, 63 visible
  statistics. The goals filter reduces the map and shot picker to 80 attempts.
- Selecting the 19 October goal displays its minute, date and xG 0.24. The picker
  provides keyboard/touch access when map markers overlap.
- Selecting 2026–27 changes both the map and statistic scope to nine matches.
- Searching passing statistics and switching to per 90 normalizes counts while
  keeping completion percentages and percentage-point differences intact.
- Heatmap, exact zone counts, ball-winning and passing views load; route filters
  change the mapped volume together with the displayed count.

Real localhost GETs to `/api/data/players/{id}/analytics` returned 200 for each role:

| Player ID | Role | Matches | Visible statistics | Request time |
| --- | --- | ---: | ---: | ---: |
| eb01 | GK | 143 | 68 | 0.325s |
| eb05 | DF | 141 | 63 | 0.566s |
| rh08 | MF | 140 | 63 | 0.493s |
| rh09 | FW | 140 | 63 | 0.506s |

These are local observed request timings, not a production load benchmark.

## Scope and limitations

The registry defines 71 metrics; headed shots, headed goals and woodwork remain
unavailable and are omitted from the visible library. Outfield players also omit
five goalkeeper metrics. All added numbers are derived from existing events;
continuous tracking and additional event categories have not been generated.
Internal consistency checks do not establish external realism for every newly
exposed spatial or estimated metric. See [definitions, references and coverage](../player-analytics.md).

Main files: `backend/counterpress/personalization/analytics.py`, the additive route
in `personalization/api.py`, `scripts/build_player_analytics.py`,
`fixtures/analytics/`, `frontend/src/football/PlayerInsights.tsx`, `insights.css`,
the profile integration in `FootballHub.tsx`, and matching backend/frontend tests.
