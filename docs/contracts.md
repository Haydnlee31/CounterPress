# Foundation contracts

The foundation fixtures described here are synthetic. IDs refer to fictional teams and players. The wider app also includes licensed adapted archives; see [data provenance](../README.md#data-and-scope). Version one
supports regulation periods, passes, carries, duels and controlled recoveries.
Additional actions and extra time require explicit future contract changes.
Unknown fields, coerced integer strings, invalid identifiers and out-of-bounds
coordinates are rejected. Models are frozen; event and evidence collections use
tuples to prevent accidental mutation.

## Identity, revisions and order

`Event` carries `schema_version`, `match_id`, `event_id`, `revision`,
`source_delivery_sequence`, `occurrence_order`, `occurred_at`, `available_at`,
`actor`, `position` and a discriminated `action` object. Actor references consist
of a team ID and player ID. Passes may identify a recipient, and duels identify
an opponent. A recovery explicitly names the previous controlling team.

An event's stable identity is `(match_id, event_id)`; a source record's identity
is `(match_id, event_id, revision)`. Revisions start at one. Each new revision
gets a new positive source delivery sequence within its match. A retransmission
preserves both that sequence and its payload. Conflicting payloads for the same
record identity are rejected by the in-memory journal. Transport offsets are
separate from this source sequence.

`occurrence_order` is a nonnegative tie breaker assigned once per event and
preserved across revisions. Canonical play order is
`(occurred_at.period, occurred_at.elapsed_ms, occurrence_order)`. Revisions may
correct occurrence time but must not silently reassign the tie breaker.
Cross-revision stability, deduplication and conflict handling are implemented in
the replay journal. Stage 5 persists those records through `HistoryStore` and SQLite. The fixture
validator still rejects duplicates and noninitial revisions; source update arrays
are accepted separately by replay.

## Match time and availability

`MatchTime` stores `period` (1 or 2) and nonnegative `elapsed_ms` since that
period's kickoff. Compare `(period, elapsed_ms)`; do not sort a displayed clock.
Stoppage time may exceed 45 minutes within a period. Period two still sorts
after all period-one events. A display minute such as 48:00 maps to period 2,
elapsed 180000 ms; 53:00 maps to 480000 ms; 58:00 maps to 780000 ms.

`occurred_at` describes the play; `available_at` describes when that revision
became available on the synthetic match timeline. Availability cannot precede
occurrence. Neither field is wall-clock UTC or a media playhead. Real-world
timestamps and an explicit media mapping can be added when their adapters exist.

Historical selection must first choose each event's highest revision available
at the requested cutoff, and then filter that revision's occurrence time.
Otherwise a correction moving an event outside a window could resurrect an old
revision. Stage 3 implements and tests this selection order.

`MatchState` records the cutoff, copied score, observed controlling team, applied
event/revision references and source delivery cursor. The cursor is the highest
available source sequence, not a safe transport checkpoint. Score remains the
declared initial score because the current action contract has no goals. Stage 5 snapshots add a committed history version outside MatchState and rebuild
from durable records. Active-player changes and incremental checkpoints remain later work.

## Pitch and controlled possession

The pitch is **105 × 68 metres**, with inclusive bounds `0 <= x <= 105` and
`0 <= y <= 68`. Every event is normalized to **its actor's team attacking toward
positive x**, regardless of the period or which team previously controlled the ball.
All positions within one action, including pass/carry endpoints, share that frame.
For a team attacking toward negative x in a fixed source frame, rotate both axes:
`x_normalized = 105 - x_source`, `y_normalized = 68 - y_source`.

The attacking third starts at **x = 70**, inclusive. A high recovery is an
open-play change into established controlled possession there. A duel or tackle
alone is not a recovery; repeated duel records cannot each be counted as one.
`origin=restart` is excluded from high recovery counts. An incomplete pass does
not itself establish opponent control; a subsequent recovery records that change.

The fixture declares a minimal initial score and controlling team at 48:00 and
registers its participating players, rather than inventing earlier events. The
validator checks team-level transitions only, not every player's movement or
full-match plausibility. e03 wins a duel; e04 establishes Eastbridge control.
e08 establishes Northport control. The points `(90,30)` for Eastbridge's incomplete
pass and `(15,38)` for Northport's recovery are the same place in opposing frames.

## Windows and evidence

Every `ObservationWindow` is **(start, end]**: start excluded, end included, with
end strictly later than start. The planned comparison is `(48:00,53:00]` versus
`(53:00,58:00]`; an event at exactly 53:00 belongs only to the first window.
The tiny fixture uses shorter adjacent windows `(48:00,48:30]` and `(48:30,49:00]`.

`EvidencePacket` includes an evidence ID and version, match ID, subject team,
metric and rule version, cutoff, and baseline/current window evidence. Each
window contains a count and exact `(event_id, revision)` references scoped to the
packet's match. References prevent a later correction from silently changing what
an earlier packet meant. Raw records hold the actors, times and coordinates.

This first contract deliberately supports only `high_recovery_count` with
`claim_type=count_comparison`. Values must match the number of unique references;
windows must be adjacent and end by the cutoff. An event cannot appear in both
windows. A count is not a pressure rate or proof of tactical effectiveness. Rate
metrics will need separate eligibility denominators and sample/exclusion fields.

A standalone packet cannot prove that its references exist, match the subject,
meet the rule or were available by the cutoff. The fixture tests resolve and
check those references against actual events. Replay now selects revisions and
computes window counts with exact references in a `RecoveryComparison`. Stage 4
uses these calculated values to create frozen EvidencePackets and Insight records
for eligible increases. Stage 5 persists the bundles with lifecycle publications.
The API returns those packets with the exact source Event records. Schema
validation alone is not verified evidence; the service resolves references against
the canonical replay before publishing a card.

`Insight` carries a stable comparison identity, revision, evidence identity/version, factual
claim/template, code-generated explanation, baseline/current values and windows,
subject team and eligibility time. It does not contain model-generated prose.
Stage 5 adds monotonic create/update/withdraw revisions, stable comparison identities
and immutable evidence versions. A withdrawal retains its revision as a client
tombstone. See [durable history](history.md) for availability, invalidation and
playback-scope semantics.
