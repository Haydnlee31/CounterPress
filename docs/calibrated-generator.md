# Learning football patterns, generating new matches

CounterPress fits aggregate statistics from **15 licensed Wyscout matches** and generates new 90-minute, 22-player event feeds. It does not stitch together historical passages or fine-tune a language model. Source: Luca Pappalardo and Emanuele Massucco, [Events](https://doi.org/10.6084/m9.figshare.7770599) and [Matches](https://doi.org/10.6084/m9.figshare.7770422), **CC BY 4.0**. The source events are football observations; the generated fixture is new synthetic data.

## Selection and analysis

Use regulation-time 2018 World Cup matches, excluding the two existing archive showcases. A fixed selection seed chooses five matches with at most one goal, five with two or three goals, and five with four or more. Five additional whole matches are held out; no events from them enter fitting. This deliberately diverse sample is not representative of the tournament's scoring frequency. All 15 names, match IDs, the five held-out matches, hashes, summary statistics and calibration trials are in `fixtures/generator/calibrated/report.json`. There are **23,753 source events** across the fitting matches.

The model stores aggregates only: action frequencies by pitch third, distance from goal and central/wide location; pass displacement means/deviations by third; completion rates by third and short/long distance; shot outcomes by location; and average action pacing. Event-derived same-team action runs are measured for research, not claimed to be exact possession durations. No player identities, event trajectories or raw source sequences are stored in the model.

## Algorithm

A conditional possession state machine maintains ball position, player on the ball, score and period. It samples pass/carry/challenge/shot decisions from the fitted spatial probabilities. Sparse contexts borrow strength from broader empirical counts. Pass displacement uses truncated normal sampling to avoid artificially concentrating failed passes on the touchlines.

Completed passes name a different teammate; incomplete passes and lost duels lead to an opponent recovery. Turnovers rotate both axes into the new team's attacking frame. Shots resolve to goals, saves, misses or blocks; blocks can rebound. Goals lead to an opponent restart. Carry geometry, duel success, team directness and a modest increase in risk when trailing late are explicitly authored priors. They are not learned player abilities, measured pressure or causal estimates. Travel-time floors cap pass/carry displacement speeds at 25/7 metres per second between action anchors. These are coarse constraints, not physical tracking.

Twelve separate simulation seeds per candidate shot-frequency multiplier fit training-set shot/goal means through simulation-based moment matching. The held-out matches do not enter this optimization. A fresh batch of 100 seeds is then evaluated. Source shots exclude penalties and free-kick shots; shot-goal totals exclude own goals. The simulator simplifies on-target non-goals into saves and woodwork into off-target outcomes.

| Metric per match | 15 fitting matches | 5 held-out matches | 100 generated matches |
|---|---:|---:|---:|
| Passes | 891.3 | 808.4 | 821.1 |
| Pass completion | 85.6% | 83.0% | 85.8% |
| Open-play shots | 22.5 | 22.2 | 19.6 |
| Open-play shot goals | 2.27 | 1.60 | 2.42 |

These are descriptive checks, not proof of realism. The generated population has fewer shots than both source groups, higher scoring than the held-out group, and less pass-volume variation than the source sample. One international tournament cannot establish realism across leagues, levels or eras. There are no penalties, cards, substitutions, fouls or explicit corner/throw-in events yet, and no learned off-ball tracking. The pitch view supplies supporting formation movement.

## Keeping a showcase entertaining

First generate all matches without targeting a result. Then restrict candidates to 2–5 goals, 12–38 shots and 500–1,200 passes. Rank by lead changes, equalizers and late goals, with a penalty for a lopsided score. Break ties by seed. This selects a match without changing any of its events; the 100-match report retains the unselected distribution so selection bias is visible.

The selected seed is **74**: Eastbridge **2–2** Northport, **815 passes**, **700 completed**, **23 shots**, four goals. Northport score at 20:03; Eastbridge equalize at 34:54 and lead at 71:12; Northport equalize at 75:00. It is available locally in Match Centre as **Level again at 75′**. Its native fixture uses the existing `PossessionFixture`/`Event` schema, stable generated IDs, occurrence and availability times, delivery sequence and registered actors. No Wyscout event/player IDs are attached to generated actions.

## Reproduce

Generate another feed using the committed aggregate model, with no network or paid model calls:

```sh
.venv/bin/python -m counterpress.generator.calibrated --model fixtures/generator/calibrated/model.json --seed 74 --output /tmp/counterpress-seed-74.json
```

Refit from licensed local source files (the output directory must not exist):

```sh
.venv/bin/python scripts/calibrate_football.py --events var/gi-research/wyscout/events_World_Cup.json --matches var/gi-research/wyscout/matches_World_Cup.json --output var/new-calibration
```

The original ten-minute generator remains unchanged. The new feed can be passed through the existing event/replay pipeline; publishing it into Azure Event Hubs remains a separate deliberate operation. No cloud ingestion or deployment is performed by calibration.

## Match library and extracted highlights

The library uses fictional display dates 16–18 October 2026, separate from source provenance dates. The generated match is dated 18 October. Three Matchday highlights extract the original actions leading to its final three goals, preserving actors, geometry and parent event references in `fixtures/showcases/generated_manifest.json`. Run `.venv/bin/python scripts/extract_generated_highlights.py` to reproduce them. The snapshot fixtures use a rebased clock internally; presentation restores the original parent match minutes (34:54, 71:12 and 75:00). Cards identify the parent match and date; independent existing highlights are labelled Preloaded.

Match Centre selects a causal lead-in and follows the selected action through its resolution, stopping before a restart. A distance- and action-based presentation clock removes idle source timestamp gaps. Source times remain unchanged for statistics. All 22 players remain visible with continuous paths; observed action positions anchor the involved players and formation movement supplies supporting players. This remains event-based animation, not measured tracking.
