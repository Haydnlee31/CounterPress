# Reviewed synthetic fixtures

Stage 2 adds two fixed, hand-authored ten-minute sequences to the original tiny
fixture. Both start at 48:00 with Eastbridge trailing Northport 0–1, Northport in
controlled possession, and finish at 58:00. Each has 89 events, 15 possession
changes and no score-changing action. Their players and match IDs are fictional.

| File | Purpose | Eastbridge baseline | Eastbridge current |
| --- | --- | --- | --- |
| `fixtures/tiny_possession.json` | Small contract/possession check | 1 | 0 |
| `fixtures/recovery_increase.json` | Ten-minute positive scenario | 1 | 4 |
| `fixtures/recovery_control.json` | Ten-minute no-increase control | 1 | 1 |

The tiny fixture uses `(48:00,48:30]` and `(48:30,49:00]`. Both new fixtures use
the planned `(48:00,53:00]` and `(53:00,58:00]` windows. Neither fixture supplies
expected values, tactical labels or hidden scenario settings to runtime code.
There is no procedural generator: these JSON files contain fixed authored plays.

## Manual recovery review

The following lists every Eastbridge recovery. The opponent recovery between
each pair explicitly returns controlled possession to Northport. Completed passes
identify their recipients, and pass/carry endpoints agree with the next event's
location after converting opposing team coordinates to the same pitch frame.

| Event | Time | Positive x | Control x | Window | Qualification |
| --- | --- | --- | --- | --- | --- |
| p008 | 49:00 | 45 | 45 | Baseline | Neither: below attacking third |
| p020 | 50:30 | 62 | 62 | Baseline | Neither: below attacking third |
| p030 | 51:30 | 55 | 55 | Baseline | Neither: below attacking third |
| p043 | 53:00 | 70 | 70 | Baseline only | Both: boundary included |
| p053 | 54:00 | 72 | 65 | Current | Positive only |
| p064 | 55:15 | 77 | 60 | Current | Positive only |
| p075 | 56:30 | 80 | 69.9 | Current | Positive only |
| p086 | 57:45 | 74 | 74 | Current | Both |

All recovery y coordinates are 38. Every listed event is an open-play recovery
with established control. p041 and p042 record opposite sides of the same duel
before p043; neither is another recovery. The control preserves the event types
and timestamps, but moves three recoveries below x=70. It also adjusts the prior
pass endpoint, duel position and next pass origin to preserve ball continuity.

`tests/expected_recovery_scenarios.json` records these reviewed IDs, counts,
locations, all 15 possession transitions, initial score and final controlling team.
It was written separately from the event files. Tests independently select
qualifying records from those files and compare the results with that oracle.

The fixtures are deliberately modest football sequences: circulation, carries,
duels and turnovers, with no shots or substitutions in this passage. They test
location/count comparisons. They do not establish a pressure-rate interpretation,
full-match realism, or eight completed eligible possessions per window. A future
pressure detector needs exposure, build-up outcomes and its own sample controls.

## Time and publication

Event timestamps retain period 2 and milliseconds since its kickoff. Publication
is immediate (`available_at == occurred_at`) for these two fixtures, so every
record through 58:00 is available at the 58:00 cutoff. This is an explicit source
assumption, not a measured latency claim. Delayed arrivals are future replay tests.

## Fault fixtures

| File under `fixtures/faults/` | Shape | Expected validity |
| --- | --- | --- |
| `invalid_player.json` | One-event fixture | Reject: np99 is absent from the roster |
| `invalid_coordinate.json` | One-event fixture | Reject: x=106 exceeds 105 metres |
| `duplicate_delivery.json` | Array of two Event records | Each record valid; identical identity, sequence and payload; ordered fixture rejects repetition |
| `event_correction.json` | Array of two Event records | Each record valid; revision 2 preserves event ID/order/time, updates x=72 to 69.9, sequence 4 to 11, and availability to 49:00 |

The two record arrays use e04 from the tiny fixture. They are isolated source
delivery cases, not complete match sequences. `tests/expected_faults.json` states
their intended validity. It also reserves future processing expectations: a
duplicate must leave one canonical recovery, while the correction should change
the eligible high-recovery count from one to zero. Stage 3 now verifies both
outcomes in the in-memory replay journal, including historical cutoffs before the
correction. The fixture-audit checks still verify record shape, identity and
revision semantics, and ordered-fixture rejection reasons.

## Validation

```sh
UV_CACHE_DIR=.uv-cache uv run --frozen pytest -q
```

This includes schema checks, exact oracle comparisons, possession transitions,
player-to-player continuity, physical ball-position continuity in a common frame,
and all four fault cases. Individual valid fixtures can also be loaded with the
existing `python -m counterpress.fixture <path>` command.
