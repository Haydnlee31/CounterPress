# Player and club data foundation

This backend branch supplies the data for profiles, favorites, club views and a future grounded assistant. It does not change the frontend or remove Studio. It adds read-only APIs under `/api/data/`; the existing match and voice routes keep their contracts.

The next [fan personalization layer](fan-personalization.md) now projects this data
for device-owned favorites, ranked feeds, bilingual audience views and player
focus. See the saved [Reactor review context](reactor-review-context.md) for product
decisions; the general Footie assistant and Azure ingestion bridge remain later work.

## What is available

- Four featured clubs: **Eastbridge**, **Northport**, **Southbank**, **Redhaven**.
- **44 featured players**, including the existing 22 display identities. Each club has two designated stars, a goalkeeper and ten outfield players with persistent broad roles and traits.
- Eight supporting clubs and four reserves per club: **12 clubs, 180 registered players** overall. `featured=true` returns the 44 profile leads; reserves and opponents remain discoverable.
- **840 historical fixtures**, spanning six completed seasons beginning in 2020 and eight rounds of 2026–27. These are the fictional players' careers in this universe; debuts are in 2020, at ages 18–21. Multi-year persistence is an authored assumption, not learned career development.
- **Four featured matches**: the three existing archive/synthetic fixtures plus Southbank **3–2** Redhaven on **19 October 2026**. Only these four belong in the full replay library.
- Three excerpts from the new fixture: Enzo Clarke's **20th career goal**, Dario Voss bringing Southbank level, and the winning goal. Read exact titles and scorers from the API rather than hard-coding this description.
- **1,050,765 canonical events**. Historical actions regenerate from stable seeds and must match committed event digests. Four featured feeds are materialized. The complete packaged foundation is approximately 3 MB, rather than a million duplicated JSON event objects.

Player and club totals are reductions of those events and appearance intervals. Highlights are references into parent matches, never additional career fixtures. A fixture can be hidden from the replay library while still appearing in a player's history; that does not require inconsistent totals.

## Research and calibration

Calibration uses the 2017/18 English league season from Luca Pappalardo and Emanuele Massucco / Wyscout: [Events](https://doi.org/10.6084/m9.figshare.7770599), [Matches](https://doi.org/10.6084/m9.figshare.7770422), and [Players](https://doi.org/10.6084/m9.figshare.7765196), licensed **CC BY 4.0**. Changes: aggregate fitting, original fictional identities, role-conditioned simulation, coordinate scaling and deterministic statistical reductions. Retain attribution when distributing the dataset or exposing its methodology.

The split is **304 fitting matches and 76 whole-match holdouts**, with a fixed seed. It is not the earlier score-stratified 15-match sample. Raw source events and real player names stay under ignored `var/personalization-source/`; only aggregate parameters, source hashes and split IDs are committed. Broad roles are source metadata, not measured positions at every moment.

The completion model uses pre-pass origin third and declared pass type. A failed pass's actual endpoint is not necessarily its intended target, so it is deliberately excluded from the model's predictors. Pass displacement distributions use geometry for simulation; that is a separate task. Simulated passes store the intended target and flight time explicitly. Difficulty is `1 − completion_probability`, and should be presented as a model estimate.

The shot model uses pre-shot distance and central/wide location, with shrinkage toward the global training rate. It is a simple CounterPress location model, not a provider's xG product. Neither model uses the result it is predicting.

Held-out Brier scores, where lower is better:

| Estimate | Model | Global-rate baseline | Held-out actions |
|---|---:|---:|---:|
| Pass completion | 0.11388 | 0.14075 | 66,176 |
| Shot conversion | 0.09524 | 0.10276 | 1,696 |

`calibration-report.json` includes reliability bins and holdout distributions. These results validate these particular estimates, not all aspects of football realism.

The simulator samples role-dependent involvement, passing and shooting from those distributions. Traits persist across matches; form, lineup rotation, substitutions, star selection, finishing multipliers and physical speeds are explicitly authored priors. A small tempo/shot-frequency search matches training-set moments using separate seeds. A fresh **100-match unselected population** evaluates the resulting simulator. It averages **801.3 passes, 22.98 shots and 2.60 goals** per match. Pass volume and its variability remain below the source distribution; this limitation is recorded rather than hidden by showcase selection.

The new showcase is selected from those untouched candidates for lead changes, equalizers and milestone opportunities. No events were rewritten to reach a target result or milestone. Selection seed **20022** produces the featured 3–2 match. Its events retain their original identifiers in each highlight.

## Metric and coverage contracts

The versioned [metric dictionary](../fixtures/personalization/metric-definitions.json), also served at `/api/data/metrics`, defines denominators and coverage. In particular:

- Goals and assists per 90 use appearance minutes; there is no ambiguous “assist percentage.” Direct assists require a completed pass to the scorer within 15 seconds, with no intervening shot or possession change. Rebound goals do not get a second assist.
- Pass accuracy excludes unknown outcomes. Passing above expected uses only passes for which the model returned a probability. Own goals contribute to the beneficiary club, not the player's scoring tally.
- Activity maps count actions on a **12 × 8 grid**, with a **105 × 68 metre pitch** and the subject club attacking positive x. These are event-location heatmaps, not dwell-time or tracking heatmaps.
- Ball and shot speeds come from **explicit synthetic flight durations**, not the interval until the next event. They are mean pitch-plane travel speeds, not measured launch speeds. The authoring priors are published in the metric dictionary.
- Player running distance, sprint speed, full tracking heatmaps and measured proximity pressure are **unavailable**. The data layer does not turn sparse event hops into fabricated tracking measurements. Existing duel-based pressure analysis remains separate.
- The two adapted archive matches lack direct pass-recipient and explicit save/recovery coverage. Assist, save and recovery coverage flags prevent those gaps from being interpreted as observed zeros. Source substitution timing has minute precision. Existing source results and own goals are preserved.
- Comparison windows **exclude the start and include the end**. Window evidence includes separate lead-in references needed for an assist whose pass preceded the window.

Full video ingestion/auto-eventing and continuous tracking are separate capabilities. The hackathon calls them features to consider; this data foundation does not claim to implement them. The licensed [DFL integrated dataset](https://github.com/spoho-datascience/idsse-data) is a researched future option for movement calibration.

## APIs for the UI colleague

Start the backend normally; no Azure credentials are required:

```sh
uv sync --locked
uv run --frozen uvicorn counterpress.api.main:app --host 127.0.0.1 --port 8000 --reload
```

The default index is in-memory SQLite. To persist local revision overlays, set `COUNTERPRESS_PROFILE_DB_PATH=var/personalization.sqlite3` when starting the server. A different dataset with existing corrections requires a fresh database instead of silently discarding them.

| Read | Endpoint |
|---|---|
| Club identities, seasons, dataset counts | `GET /api/data/catalog` |
| 44 featured player cards | `GET /api/data/players` |
| Search all players, including reserves | `GET /api/data/players?featured=false&q=Clarke` |
| Filter player cards | `GET /api/data/players?club_id=southbank&role=FW` |
| Career/season totals, form, activity map, evidence | `GET /api/data/players/sb09?season=2026-27` |
| Player history, including non-replayable matches | `GET /api/data/players/sb09/matches?offset=0&limit=20` |
| Club history and statistical profile | `GET /api/data/clubs/southbank` and `/api/data/clubs/southbank/matches` |
| League table, excluding showcase fixtures | `GET /api/data/standings/2026-27` |
| Exactly four featured fixtures | `GET /api/data/matches` |
| Search all fixtures | `GET /api/data/matches?featured=false&club_id=southbank` |
| Fixture metadata, appearances and full summary | `GET /api/data/matches/{match_id}` |
| Bounded event detail with metric enrichment | `GET /api/data/matches/{match_id}/events?limit=100&offset=0` |
| Generated fixture in existing `Event` v1 pitch format | `GET /api/data/matches/{match_id}/replay` |
| New highlight cards with parent links | `GET /api/data/highlights` |
| Highlight in existing pitch format | `GET /api/data/highlights/{highlight_id}/replay` |
| Causal state, career baseline and live milestones | `GET /api/data/matches/{match_id}/live?period=2&elapsed_ms=447225` |
| Revision-aware insight changes | `GET /api/data/matches/{match_id}/insight-changes?period=2&elapsed_ms=2700000&since_sequence=600` |
| Window metrics and evidence | `GET /api/data/matches/{match_id}/window?start_period=2&start_ms=0&end_period=2&end_ms=600000` |

The new match ID is `career-showcase-southbank-redhaven`. Enzo Clarke is `rh08`, Dario Voss is `sb09`. The live milestone becomes available at second-half **447225 ms**, and is absent one millisecond before that cutoff. Generated pass and shot outcomes become available only after their explicit ball flight plus 100 ms processing time.

Player and club profiles accept a `before=YYYY-MM-DDTHH:MM:SSZ` filter for historical comparisons. Only completed fixtures before that time contribute; later corrections to an older match are excluded as well. Mapping period clocks to UTC uses an explicit 15-minute halftime convention. Empty denominators produce `null`. Profiles include match/evidence references, coverage and a baseline digest. A future assistant should use these numbers and references rather than calculate from an unbounded prompt containing the whole dataset.

**Integration boundaries:** Keep Matchday limited to highlights. Use `featured`/`replay_available` for the four-match library; the full history remains accessible from profiles. Use fixture appearances to identify the 11 players active at a particular time, rather than rendering every reserve simultaneously. Source archive replays retain `/api/gi/matches/{id}`. The new replay route returns HTTP 409 if its source has corrections; use current events before rendering rather than replaying stale actions. No frontend components, club colors, routing or favorites UI were edited on this branch.

## Revisions and local ingestion

`DataStore.ingest(match_id, actions)` writes an atomic, append-only revision overlay. It accepts duplicates idempotently, accepts reordered deliveries with consistent provider ordering, rejects conflicting payloads/sequences and invalid roster membership, and preserves occurrence order. Revision selection is bounded by availability time and optional delivery sequence.

Live career baselines exclude the current match and all later fixtures. Current goals are added once. Milestones have stable identities and event-revision evidence; corrections can publish, update or withdraw them. `/insight-changes` compares two delivery states. No unauthenticated public write endpoint is installed. This module is an adapter boundary for later Event Hubs integration; the current Azure consumer is not changed by this branch.

## Reproduce and verify

Source downloads and build steps are local, with no paid inference calls:

```sh
# With the licensed local source files already downloaded:
.venv/bin/python -m counterpress.personalization.calibration \
  --source var/personalization-source --output fixtures/personalization
.venv/bin/python -m counterpress.personalization.build \
  --archive-metadata var/gi-research/wyscout/matches_World_Cup.json

.venv/bin/pytest -q tests/test_personalization_metrics.py tests/test_personalization_foundation.py
.venv/bin/python scripts/verify_personalization.py \
  --output docs/verification/personalization-data.json
```

The audit regenerates **every** historical fixture, verifies its event digest and statistics, reconciles player/club goals including own goals, checks 11 active players and 990 player-minutes in simulated matches, verifies flight-time continuity, checks all 44 careers and validates highlight replay contracts. Source data is not required to run the application, tests or audit. It is only needed to refit calibration or reimport source lineups.

The expected accounting fixture in `tests/expected_personalization.json` is written independently of the reducer. Tests also exercise cutoff boundaries, retractions/restoration, persistence, duplicate and reordered delivery, transaction rollback, API bounds and unavailable metrics.
