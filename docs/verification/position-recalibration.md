# Position recalibration — local verification, 20 October 2026

The v3 career population is promoted locally. All required acceptance gates and
the complete event-accounting audit pass. Two smaller-batch assist-share warnings
remain; this is a calibrated synthetic population, not certification of every
football metric or every individual career.

This is the earlier v3 result. The [spatial follow-up](spatial-recalibration.md) records the current local dataset and expanded review.

## Method and results

The reference is attributed Wyscout 2017/18 England event data: 304 fitting matches
and 76 held-out matches. Passes, set pieces, saves, shots, ground duels, draws and
minutes are reconciled to provider definitions. Rates are weighted by exposure,
with 400 whole-match bootstrap replicates. Individual distribution tails require
900 minutes; the short holdout has no eligible players, so these explicitly use
the training reference. See [the complete methodology](../position-calibration.md).

The final algorithm evaluated 18 candidates on 192 fixed fitting seeds. Candidate
11 was selected. The model was frozen before a fresh 3,000-match validation on
seeds 70000–72999. Both `model.json` and `ledger.json.gz` remain byte-for-byte equal
to the frozen artifacts. These validation matches do not enter user careers.

- **285 positional gates pass:** 57 each for the historical population, pooled
  validation and three independent 1,000-match batches.
- **20 population gates pass:** 10 each for historical and pooled validation.
- **All 844 fixtures audited:** 1,179,903 events, 2,514 goals, all 44 featured
  careers, four featured matches and three regenerated showcase highlights.
- Every event digest and summary reconciles; goals, assists, passes, shots,
  saves and duels reconcile across players and teams. Simulation lineups and
  player-minutes, ball-flight ordering and replay contracts pass.

Historical per-90 population means:

| Position | Pass attempts before → after | Ground duels before → after | Completion after |
| --- | ---: | ---: | ---: |
| Goalkeeper | 10.73 → 30.84 | 1.65 → 0.23 | 81.26% |
| Defender | 38.07 → 47.01 | 12.23 → 9.53 | 82.82% |
| Midfielder | 63.69 → 50.75 | 20.64 → 14.46 | 82.81% |
| Forward | 24.51 → 26.74 | 8.58 → 16.09 | 76.21% |

Leon Finch now has **437 saves in 141 matches (3.10 per match)** and **77.6% pass
completion from 4,344 attempts**. The main goalkeeper distribution issue was low
pass volume, not an inherently implausible three saves per match. Stable registry
IDs and all 44 portrait mappings are preserved.

Two archive fixtures also had source outfield players assigned goalkeeper aliases.
The mappings now identify their actual source goalkeepers, with checksums and
regression tests. Source events, results and provider assist awards are unchanged.
The regenerated Southbank–Redhaven showcase ends 2–2, with Mateo Cross's 80th career
goal in its three highlights. Drawn challenges replay without being called losses.
Explicit passing/defending preferences retain a relevant card even when several
milestones compete for one slot.

## Remaining warnings and limits

Batch 1 defender assist share is **23.40%** against a formation-standardized
reference of **12.80%**, exceeding the ±10 percentage-point diagnostic band by
0.60 points. Midfielder assist share is **33.68%** against **44.48%**, exceeding
the band by 0.80 points. Pooled assist-share gates and batches 2/3 pass.

Earlier rejected validation runs and the protocol revision are disclosed in the
methodology: rare population ratios are accepted on the larger pooled sample;
small-batch aggregates remain visible diagnostics. The source holdout was reused
during development, so it is not a pristine blind evaluation. Fresh simulation
seeds establish stability, not transfer to another league or season.

The external comparison covers four broad positions, not fine roles such as
wing-back versus centre-back. Tracking distances, sprint speeds, continuous player
locations and physical pressure are not verified by these sparse event records.
Recoveries and shot-assists reconcile internally but lack a like-for-like external
rate gate. Those limitations must remain visible in technical documentation.

## Commands and observed output

From the repository root:

```sh
.venv/bin/python scripts/verify_personalization.py --root var/position-audit-v3/verified --output docs/verification/personalization-data.json
```

Output: `status: passed`; `matches: 844`; `events: 1179903`; `goals: 2514`;
`position_checks: 285`; `independent_simulation_matches: 3000`;
warnings: `batch1.assist_role_share_DF`, `batch1.assist_role_share_MF`.
Elapsed: 127.13 seconds. [Full audit output](personalization-data.json).

```sh
.venv/bin/pytest -q
```

```text
689 passed, 1 warning in 74.69s (0:01:14)
```

The warning is the existing experimental evaluation-library notice.

From `frontend/`:

```sh
npm test
npm run build
```

```text
Tests  156 passed (156)
Duration  24.88s
✓ built in 3.97s
```

`git diff --check` returned no output. After restarting the local server, real HTTP
checks returned health 200 and a successful passing-focused match response with
one `player_passing` card and unchanged career goal count of 80. Both archive
endpoints, the showcase replay (including 35 drawn challenges), Leon's profile and
the 44-player directory had also returned 200 against the promoted dataset.

Local review: <http://127.0.0.1:8017/#football>. No push, deployment, Azure resource
change or paid model call was made. The original paid evaluation pilot is unchanged;
the offline/mocked source lock is `career-position-calibration-v3`.
