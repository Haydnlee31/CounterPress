# Observed pressure and build-up escape — Stage 8, second increment

This detector analyzes public Event records after canonical revision selection.
It measures defensive-third build-up episodes, a duel-based pressure-exposure
proxy, and controlled escapes from exposed episodes. It never reads hidden
generator settings, seeds, change times or evaluator outcome labels.

## Run it

```sh
UV_CACHE_DIR=.uv-cache uv run --frozen python -m counterpress.pressure fixtures/pressure/increase.json --windows 48:00 49:00 50:00
UV_CACHE_DIR=.uv-cache uv run --frozen python -m counterpress.pressure fixtures/pressure/control.json --windows 48:00 49:00 50:00
```

The controls use short, hand-authored two-minute segments. For a generated feed,
pass its path with `--team northport` or `--team eastbridge`. Default windows are
`48:00 53:00 58:00`. `--at MM:SS` sets the availability cutoff and must be at or
after the current window end. The analysis requires observed history and both
windows within one period. It rejects windows predating available history.

Use `--json` for the complete `PressureEvidence`: source records and revisions,
episode references, window membership, exclusions, sample counts, rates,
eligibility decisions and policy. The text report includes a SHA-256 fingerprint
of that packet. It changes when source revisions, cutoff, policy or evidence
change; it is a content identity, not a persisted ledger revision number.

`--updates path.json` accepts the same source Event revision array as replay.
`--publications path.json` supplies prior publication receipts for cooldowns.
No Azure credentials or model calls are required.

## Observable episode rules

Coordinates remain on the normalized 105 × 68 metre pitch. The subject team
attacks toward increasing x. Its defensive third includes x ≤ 35. For a duel
recorded from the opponent's perspective, x ≥ 70 maps to this region.

| Event evidence | Interpretation |
| --- | --- |
| Subject recovery at x ≤ 35, including a restart | Fully observed episode start |
| Subject carry or completed pass from x > 35 to an endpoint x ≤ 35 | Fully observed re-entry start |
| First subject possession observation already inside x ≤ 35 | Start unknown; left-censored and excluded from rates |
| Duel involving the controlling subject in its defensive third | Pressure-exposure proxy; repeated duels still count as one exposed episode |
| Subject carry or completed pass ending at x > 35 | Escape with observed control; episode resolves |
| Opponent established open-play recovery | Turnover; episode resolves without escape |
| Opponent established restart recovery | Restart resolution without escape |
| Lost duel or incomplete pass without a later resolution | Remains pending |

A won duel is not an escape. A subject player challenging for possession is not
yet building out; the following established recovery may start an episode.
The first qualifying event ID is the episode ID within its match. All records
from start through resolution are referenced, including exact source revisions.

The Event contract provides completed-action endpoints, not separate ball-arrival
times. Escape time is the occurrence time of the recorded completed pass/carry;
the event can only be used once its revision becomes available. There is no
duration-based timeout that silently turns an unfinished episode into a failure.

## Windows and rate denominators

Both the observed start and resolution must lie within `(start,end]`. A start
exactly at the window start is excluded; a resolution exactly at its end is
included if the episode began later than the start. Adjacent windows cannot
count the same completed episode twice.

Each intersecting episode belongs to one category per window, in this order:

1. **Left-censored:** the observed history did not include its true start.
2. **Pending:** no resolution is available within that window, including episodes
   which resolve after its end. A later-window resolution does not retroactively
   include it in the earlier window's denominator.
3. **Boundary-excluded:** the observed start is at/before the window start and
   resolution is inside the window.
4. **Included:** both observed start and resolution are inside the window.

Thus a crossing episode can be pending in the baseline and boundary-excluded in
the current window. The full evidence gives IDs as well as counts for every
category. Late delivery can subsequently resolve a pending episode whose
occurrence time belongs inside the window; historical cutoffs still exclude it.

| Metric | Numerator | Denominator |
| --- | --- | --- |
| Pressure exposure | Included episodes with a defensive-third duel | All included episodes |
| Pressured escape | Included exposed episodes resolving as an escape | Included exposed episodes |

Zero denominators produce `null` rates, never an assumed zero or success.
Each metric requires at least **three denominator episodes separately in each
window**. An eligible change is at least **25 percentage points** in either
direction. These are disclosed synthetic-demo thresholds, not a significance
test or real-football calibration. Episodes may share a possession sequence and
are not asserted to be statistically independent.

## Cooldown and corrections

The default cooldown is **60 seconds**, scoped to match, subject team and metric.
It suppresses a different comparison published within that interval. Exactly at
expiry it is eligible. Future receipts do not affect historical replay.
Re-evaluating the same window pair bypasses cooldown so a source correction can
refresh or invalidate an existing claim immediately.

The detector is pure and does not publish stories or persist cooldown state.
Its caller passes receipts only for actual prior publications. A receipt file
is a JSON array; one example for the positive control is:

```json
[
  {
    "match_id": "build-up-increase",
    "team_id": "eastbridge",
    "metric": "pressure_exposure",
    "baseline": {"start": {"period": 2, "elapsed_ms": 180000}, "end": {"period": 2, "elapsed_ms": 210000}},
    "current": {"start": {"period": 2, "elapsed_ms": 210000}, "end": {"period": 2, "elapsed_ms": 240000}},
    "published_at": {"period": 2, "elapsed_ms": 280000}
  }
]
```

Corrections rebuild episodes from the highest available revision of every event,
using the existing replay journal. Evidence includes canonical records only.
Tests correct a duel into a carry: exposure disappears, the pressured-escape
baseline falls below the minimum and that decision becomes ineligible. Replaying
before correction availability reproduces the old evidence exactly. Durable
create/update/withdraw publication for these new metrics is the next increment.

## Independently reviewed controls

`fixtures/pressure/increase.json` and `control.json` are hand-authored sequences,
separate from the procedural generator. The expected episode lists and fractions
are written independently in `tests/expected_pressure.json`; runtime code never
reads them. Each window has six build-up episodes beginning at seconds 2, 10,
18, 26, 34 and 42 relative to its start. Every start is a recovery at x=20.
An escape is a carry from x=20 to x=50; otherwise an opponent recovery at its
x=85 resolves a turnover. Each next attempt follows an opponent incomplete pass.

| Control | Baseline exposure | Current exposure | Baseline pressured escape | Current pressured escape |
| --- | --- | --- | --- | --- |
| Increase | 3/6 | 6/6 | 3/3 | 1/6 |
| Unchanged | 3/6 | 3/6 | 2/3 | 2/3 |

In the positive control, `b1-start`–`b3-start` are exposed and escape;
`c1-start`–`c6-start` are exposed but only `c1-start` escapes. In the negative
control, the first three episodes in each window are exposed and only the first
two escape. The negative still has actual duels, successes and turnovers; neither
rate changes. Geometry and possession continuity are independently checked.

The 37 new tests also cover exact x/time boundaries, repeated duels, challenger
perspective, incomplete samples, pending and censored episodes, late delivery,
revision changes, invalid evidence, cooldown isolation/expiry and generated
development feeds. Held-out generator runs have not been used to tune these
rules. All 273 backend tests pass; [progress](progress.md) records exact commands
and output. No frontend file changed in this increment.

## Scope and next step

The feed lacks tracking observations, so this detects recorded duel exposure,
not all pressure, pressure intensity, passing lanes or off-ball behavior. A
controlled escape is progression beyond the defensive third, not a claim of
tactical value. A rate change does not establish causal pressure effectiveness.
No pass-difficulty estimate is added without suitable release-time context.

The CLI and Python function provide typed evidence and eligibility decisions.
The following increment now adds [durable publication and replay cards](pressure-publication.md),
including independent revisions, correction/withdrawal and bilingual audience
handling. The existing recovery-count `EvidencePacket` and model workflow retain
their schema and behavior. Next: possession without progression, with independent
controls. Recaps and Azure application deployment remain later stages.
