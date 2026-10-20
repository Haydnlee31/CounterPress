# Positional calibration and verification

The v3 audit covers the four **broad source roles**: goalkeeper, defender,
midfielder and forward. It does not establish separate benchmarks for centre
backs, fullbacks, defensive midfielders or wingers. Identities, clubs and portrait
IDs are retained; synthetic match events and their derived statistics are rebuilt.

The later spatial calibration extends this protocol to the expanded analytics catalogue. See [the current spatial report](verification/spatial-recalibration.md) for the final dataset, revised club-style adjudication and retained coverage limits. The v3 procedure below remains the historical record.

## Reference and scope

The reference is the licensed Wyscout 2017/18 English league season: 380 matches,
split by whole match into 304 fitting matches and 76 comparison matches. The
[dataset paper](https://www.nature.com/articles/s41597-019-0247-7) describes the
collection and CC BY 4.0 release. Original download hashes and the exact split
are retained in `calibration.json`. These benchmarks describe that competition,
era and provider; they are not universal laws of football.

Definitions are aligned before comparison:

- CounterPress counts recorded pass deliveries, including set pieces, excluding
  throw-ins. The audit therefore adds goal kicks, corners, free kicks and free
  kick crosses to the source's ordinary `Pass` records. This differs from the
  provider's narrower [pass statistic](https://dataglossary.wyscout.com/pass/).
  Unknown outcomes, notably source goal kicks, count as attempts but are excluded
  from the completion denominator. Source completion coverage is consequently
  narrower than synthetic completion coverage; this remains a limitation.
- Passing length is compared on **completed, located passes**, using a common
  32-metre threshold. An unsuccessful pass's endpoint is not treated as its
  intended destination. High-pass labels alone do not define long distance.
- Ground attacking and defending duels count each participant once. Wins use
  tag 703, draws 702 and losses 701; accuracy tag 1801 alone does not mean a win.
  Aerial and loose-ball duels are excluded from this comparison. Imported
  archives retain their original broader duel coverage.
- Saves use successful source `Save attempt` records, including reflex saves.
  Conceded goals do not count as saves. Synthetic saves are reconciled against
  the opposing team's saved shots. See the [save definition](https://dataglossary.wyscout.com/save/).
- Shots include penalties and direct free kicks. Player goals exclude own goals.
  Source assist awards and CounterPress's direct-pass assist rule are similar
  but not identical; no missing source assist is invented.
- Source appearance minutes use lineup/substitution metadata, dismissals and a
  nominal 90-minute clock. Source stoppage events remain included; stoppage and
  substitution precision differ from the simulator's exact 90-minute intervals.

The previous 18.5 goalkeeper pass benchmark described ordinary pass events only.
Including restart deliveries makes the fitting benchmark approximately **29.6
attempts per 90**. The revised audit uses this aligned denominator.

## Method

1. Retain a pre-change dataset and baseline audit locally under
   `var/position-audit-v3/before` and `baseline.json`.
2. Fit source probabilities and role benchmarks using **training matches only**.
   Match-cluster bootstrap intervals resample entire matches, preserving the
   dependence between players and both teams within each match (400 replicates,
   fixed seed, 95% percentile intervals).
3. Calibrate participation, ground-duel frequency, pass length and completion,
   shooting involvement and finishing jointly. Drawn duels and role-conditioned
   non-goal shot outcomes are fitted from source tags. Goalkeeper pass endpoints
   are constrained to build-up/middle zones to prevent routine Gaussian draws
   from creating direct passes into shooting positions. That geometry constraint
   is an authored simplification, not tracking evidence.
   Chance creation is an explicit causal effect of a completed pass on the next
   shot opportunity, conditioned on the provider's role and creation trait.
   Its starting scale uses training assists per pass; its calibration uses only
   training assist rates. Duels, turnovers, restarts, excessive carries and the
   15-second limit invalidate this setup, matching the accounting definition.
4. The final fitting run uses 18 candidates and 192 fixed simulation seeds,
   10000–10191. Selection prioritizes passing all declared position and population
   gates, then the normalized training error. Development iterations are not
   described as independent validation.
5. Freeze the candidate before evaluating 840 historical matches and a fresh
   **3,000-match population, seeds 70000–72999**, split into three 1,000-match
   stability batches. No highlight or
   showcase selection is used for these populations. Showcase selection remains
   confined to 20000–20099. The earlier 40000–40719 validation rejected a
   development candidate. A subsequent 50000–50719 run passed all 228 position
   gates but failed one aggregate defender-assist-share gate. Both results are
   retained locally and those seeds are not described as fresh validation of
   the final candidate. Advanced-area involvement was then smoothed spatially,
   and rare assist rates received more weight in the **training loss**. The
   validation tolerances were not widened.
   The 60000–60719 run then passed all position gates but flagged midfielder
   assist share in two 240-match batches; its 840-match history passed. The model
   was frozen at that point. Before examining seeds 70000–72999, the protocol
   was revised to assess rare aggregate ratios on a larger **pooled** population,
   keeping batch aggregate results as explicit diagnostics. Historical, pooled
   and each batch's position gates remain mandatory. This is a disclosed
   protocol revision, not a claim that every earlier acceptance gate passed.
6. Rehydrate every published career fixture, compare event digests and reduced
   summaries, reconcile player/team totals, verify active lineups, and reconcile
   all 44 featured career profiles with their match histories. Recheck causal
   goal boundaries and correction/retraction behavior after dataset replacement.

The 76 source matches were already used for earlier development comparisons.
They are a **reused source holdout**, not a pristine blind test. The new simulation
seeds test stability within this model; they cannot establish generalization to
another league or season. Bootstrap intervals quantify sampling variability, not
all model uncertainty, and do not account for dependence across matches involving
the same club.

## Acceptance envelopes

`positions.position_checks` contains the engineering thresholds. They are fixed
before the final validation run. Intervals are reported separately and never used
to silently widen a failing threshold.

| Metric | Position-average tolerance |
|---|---|
| Pass attempts per 90 | Larger of 20% or 2 passes |
| Shots per 90 | Larger of 25% or 0.15 shots |
| Goals per 90 | Larger of 30% or 0.04 goals |
| Assists per 90 | Larger of 35% or 0.04 assists; GK absolute 0.015 |
| Ground duels per 90 | Larger of 25% or 0.20 duels |
| Passing completion | 6 percentage points |
| Completed long-pass share | 8 percentage points |
| Outfield shot accuracy / conversion / duel win rate | 8 / 5 / 9 percentage points |
| GK saves / goals conceded per 90 | Larger of 20% or 0.25 / 0.20 |
| GK save rate / clean-sheet rate | 8 / 9 percentage points |

Player variation uses the 10th and 90th percentiles of pass and shot rates among
players with at least **900 minutes**. The tolerance is the larger of 40% or
3 passes / 0.4 shots per 90. Population rates pool numerators and denominators;
they do not average individual percentages. These are broad plausibility gates,
not equivalence tests or a requirement that every player resemble the average.
The 76-match split has no individual reaching 900 minutes. Its individual tails
are unavailable, not zero: the audit explicitly uses the **training cohort's
900-minute distributions** for those gates, while aggregate rate gates use the
source holdout. No minimum-minute threshold was lowered to populate the sample.

Match-volume, role-share and scorer-concentration checks remain active. Goal and
assist role shares and the assisted-goal ratio are **directly standardized to simulated positional minutes**:
source per-90 rates multiplied by each simulated role's minutes, then normalized.
This permits a 4–3–3 to be compared with a league having different role exposure
without forcing its three forwards to have two forwards' combined output. No
simulated goal or assist counts enter that reference. Scorer concentration uses
the longer training sample; the short holdout inflates leading-scorer shares.
All references are retained in the report. Scoring form starts from the training
team-goal variance through a Poisson/lognormal moment estimate, then its scale
is calibrated on training clean-sheet rates. This is a distribution model, not
a claim to recover real team strength.

## Evidence and reproduction

`fixtures/personalization/position-validation.json` contains source benchmarks,
bootstrap intervals, historical statistics, independent batch statistics and each
acceptance result. `manifest.json` records fitting trials, selection and hashes.
`docs/verification/personalization-data.json` records the complete ledger audit.
Failed candidates cannot be loaded by the app. Batch aggregate warnings are
retained separately and do not silently change the pooled acceptance thresholds.

```sh
.venv/bin/python -m counterpress.personalization.calibration \
  --source var/personalization-source --output fixtures/personalization
.venv/bin/python -m counterpress.personalization.build \
  --archive-metadata var/gi-research/wyscout/matches_World_Cup.json
.venv/bin/python scripts/verify_personalization.py \
  --output docs/verification/personalization-data.json
.venv/bin/pytest -q
```

Build into a staging directory before replacing an active dataset. A persistent
career database with live corrections requires a new database path; the loader
deliberately refuses to discard corrections to reconcile a changed fixture set.

## What this does not verify

Running distance, sprint speed, continuous occupancy and physical pressure cannot
be verified from sparse events. Ball flight speeds remain authored physics.
Recoveries and shot-assists reconcile internally but do not have a like-for-like
external rate gate in this audit. Exact real player ratings, cross-season aging,
transfers, injuries, own-goal frequency and fine positional roles are not fitted.
Four featured matches include imported/legacy material; the statistical realism
benchmark concerns the regenerated career population, while accounting checks
cover all four featured matches as well.

The archive audit also found source outfield players assigned to `eb01`/`np01`.
The two archived matches now swap those aliases with their actual goalkeepers,
in both Match Centre and career imports. Source events, scores and provider
assist awards are preserved. Alias files are checksummed. Outfield aliases remain
fictional match-scoped identities, not a reconstruction of real careers.
