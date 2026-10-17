# Deterministic replay and metrics

Stage 3 reads the validated fixture and computes state and metrics from its
events. Runtime modules never load `tests/expected_*.json`; these remain
independent test oracles.

## Console commands

Run from the repository root after the README's setup command:

```sh
UV_CACHE_DIR=.uv-cache uv run --frozen python -m counterpress.replay fixtures/recovery_increase.json --speed 60
UV_CACHE_DIR=.uv-cache uv run --frozen python -m counterpress.replay fixtures/recovery_control.json
UV_CACHE_DIR=.uv-cache uv run --frozen python -m counterpress.replay fixtures/recovery_increase.json --at 54:00
UV_CACHE_DIR=.uv-cache uv run --frozen python -m counterpress.replay fixtures/tiny_possession.json --windows 48:00 48:30 49:00 --updates fixtures/faults/event_correction.json
```

Reports include the cutoff, canonical event count, declared score, observed
controlled possession, completed/attempted passes, total attempted pass distance,
and high-recovery counts. A completed comparison includes the exact source event
IDs and revisions. Counts are location/count facts, not a pressure interpretation.

The default comparison windows are `(48:00,53:00]` and `(53:00,58:00]`. `--at`
reports an earlier point without completing the comparison prematurely. `--windows`
declares the observation interval; for the tiny fixture it must be supplied as
shown above. `--team northport` changes the comparison subject. `--updates` accepts
a JSON array of Event records, including the duplicate and correction fixtures.

The CLI advances directly through the virtual elapsed duration without sleeping.
Its `--speed` does not change event timestamps. It demonstrates replay and prints a
report; it is not an interactive terminal player or a measured live ingestion path.

## Programmatic playback controls

```python
from pathlib import Path
from counterpress.fixture import load_fixture
from counterpress.replay import ReplaySession

session = ReplaySession(load_fixture(Path("fixtures/recovery_increase.json")))
session.clock.play()
session.clock.advance(30)       # 30 real elapsed seconds supplied by the caller
session.clock.pause()
session.clock.advance(10)       # paused: no movement
session.clock.set_speed(2)
session.clock.play()
session.clock.advance(15)       # 30 additional seconds of match time
snapshot = session.snapshot()  # 49:00, current events/state/metrics
session.clock.reset()          # 48:00, paused; speed remains 2
```

The clock uses fractional milliseconds internally to avoid losing sub-millisecond
increments between ticks. It exposes integer-millisecond cutoffs, clamps at the
declared end, and pauses when that end is reached. Invalid/negative elapsed time
and zero, negative or nonfinite speeds are rejected. Callers supply elapsed time;
no wall-clock thread, sleep or API transport is involved.

`snapshot(cutoff)` reads a historical point within the declared interval without
moving the clock. Reset also preserves the source journal, so the same data can be
replayed again. Results at the same cutoff are identical at all tested speeds.

## Revision and late-record semantics

1. Validate match identity, source identity, unique source sequences and occurrence
   tie breakers. Exact repeated deliveries are ignored. Different payloads for the
   same `(match_id,event_id,revision)` are errors. A rejected batch leaves the journal intact.
2. Require stable occurrence order across revisions. Newer revisions require newer
   source sequences and cannot become available before older revisions.
3. At a cutoff, choose the highest available revision for each event, then apply
   occurrence-time filtering. Sort by period, elapsed milliseconds and occurrence order.
4. Rebuild state from the declared initial state, then calculate metrics and windows.
   Never choose revisions separately inside a window: that can resurrect an old
   record when its correction moves outside the window.

`session.deliver(records)` appends schema-valid records and checks registered actors.
It accepts out-of-order deliveries; canonical play order comes from occurrence time.
Availability remains the declared source availability, not the time Python received
the object. Historical snapshots therefore represent source knowledge at a cutoff.
Snapshots are recomputed rather than incrementally repaired for these small fixtures.

The tiny correction changes e04 from x=72 to x=69.9 at 49:00. It qualifies before
that availability cutoff and no longer qualifies at or after it. Replaying the old
delivery later does not overwrite revision 2. A separate test moves an event
outside the comparison interval and verifies that revision 1 does not reappear.

## Metric definitions and state limits

Only confirmed recovery records change the observed controlling team. A duel alone
does not change it; incomplete passes do not establish a new team until recovery.
Contradictory possession sequences raise an error instead of returning misleading
metrics. Missing or delayed possession transitions may therefore prevent a snapshot
until enough consistent evidence is available; automated gap repair is not implemented.

Pass attempts include completed and incomplete passes; completions include only
completed ones. Each pass distance is the straight-line distance between recorded
start and end coordinates. The metrics object exposes both attempted and completed
distance sums; this is not ball trajectory distance or player running distance.
High recoveries require established open-play control at normalized x >= 70.
Restarts, duels and below-threshold locations are excluded.

Canonical goal shots increment the declared initial score. Rewinds and later
shot corrections rebuild that score. Substitutions and active-player changes still
need explicit future event types. The local clock supports one period per replay. MatchTime ordering
supports periods, but multi-period clock traversal requires declared period lengths
and halftime/media mapping; the clock rejects such intervals for now.

The standalone console ReplaySession remains in memory. The API now wraps replay
with SQLite history and lifecycle publications; see [durable history](history.md).
The source cursor is the maximum available sequence, not a guaranteed contiguous
or durable checkpoint. Records beyond a standalone session's declared horizon are
not played by that session. The API extends its horizon to newly ingested revision
availability. Stream transports and cloud delivery remain later milestones.

## Verification

`tests/test_replay.py` covers positive/control expected IDs, tiny manually calculated
pass distances, reset/repeatability, pause/resume, speed changes and fractional ticks,
cutoffs, duplicates, corrections, out-of-order/late records, stable tie breaking,
conflicting revisions, threshold/restart exclusions, invalid actors and bad control
transitions. It also runs the console command and checks its output.


## Clip reconstruction source coverage

These are independently authored synthetic sequences, viewed against official
footage on 18 October 2026. Coordinates estimate visible pitch landmarks and lanes;
no camera calibration, provider event records or tracking measurements are used.
All 22 identities persist. Positions outside the camera view and intermediate
movement are illustrative. The action order, ball endpoints and role mapping live
in `fixtures/showcases`; separate expected results live in `tests/expected_replay_gallery.json`.
Short showcase IDs are explicitly excluded from five-minute insight publications.

| Sequence / source | Visible action coverage | Fictional role mapping |
| --- | --- | --- |
| Watford–Leicester, 12 May 2013: [official Watford clip, 9:20 onward](https://www.youtube.com/watch?v=ETXv-SvOk9g&t=560s) | Penalty, rebound save, outlet, right-wing break, cross, header, finish. Existing reconstruction retained. | Ashford saves; Mercer breaks; Hart crosses; Vale heads down; Ellis shoots. |
| Brazil–Korea Republic, 5 December 2022: [FIFA highlights, about 0:48–0:55](https://www.youtube.com/watch?v=c0-ZhEkEFtA&t=48s) | Initial control under pressure; wide view around 0:51 shows Marquinhos on the right edge of the area, defensive line and support; around 0:52 shows Thiago Silva near the arc and Richarlison running through. Finish follows, with alternate-angle replays later. The opening juggling touches are abstracted as one control/carry event. | Richarlison → Ellis (`eb09`); Marquinhos → Rowan (`eb04`); Thiago Silva → Vale (`eb06`); Kim Seung-gyu → Wells (`np01`). |
| Argentina–France, 18 December 2022: [FIFA extended highlights, about 2:54–3:05](https://www.youtube.com/watch?v=agrGb25mJzs&t=174s) | Wide build-up at 2:54; through-ball and central runner near halfway around 2:59; square ball and far-side finish around 3:02–3:04. Visible recovering defenders and keeper constrain the illustrative shape. The reconstruction starts at Messi's release, after the earlier build-up. | Messi → West (`eb10`); Álvarez → Ellis (`eb09`); Mac Allister → Mercer (`eb08`); Di María → Hart (`eb07`); Lloris → Wells (`np01`). |

Each of the three replays has eleven authored starting and finishing slots per side in
`frontend/src/matchday/replayGallery.ts`. Touch anchors from the canonical events
control participants; other players interpolate between their illustrative slots.
All positions share a 105 × 68 m stadium view. The source event model still uses
each actor team's positive-x attacking direction; Northport is mirrored on both axes.
The match clocks are rebased to end at 58:00 and the names, timings and positions
are deliberately authored, so this is not a frame-synchronised recreation.
No original video, audio, crest, screenshot or provider dataset is shipped.

Public StatsBomb event/360 data was considered but not incorporated. Its
[published licence](https://raw.githubusercontent.com/statsbomb/open-data/master/LICENSE.pdf)
restricts modification/redistribution and commercial exploitation. No such records
were used to author the shipped fixtures. Source videos remain external links.

Verification covers independent action/score expectations, strict fixture validation,
ball-path continuity, all 22 identities, player bounds, adjacent-action continuity,
sub-12 m/s sampled player speeds at normal playback, score correction/rewind, and
no five-minute publications. This verifies internal consistency, not positional
accuracy against a tracking ground truth that the footage does not supply.
