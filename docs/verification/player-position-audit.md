# Extended player-position review — 20 October 2026

**Result: needs recalibration.** The original 57 headline position checks pass,
but several newly exposed spatial statistics and team role shares do not meet
the extended review's engineering envelopes. The app, generator and dataset were
not changed by this audit. This report supersedes any inference that passing the
original gates validates every statistic in the expanded Clubhouse catalogue.

This is the pre-change audit. Follow-up work and the current outcome are recorded
in [the spatial recalibration report](spatial-recalibration.md).

## Scope and method

- Reconciled 22,870 player-match rows across all 844 fixtures. Positional reference
  comparisons use the 841 calibrated simulations; the three imported fixtures
  retain their different source coverage and are checked for internal accounting.
- Classified all 71 metric definitions: 43 have an external comparison, seven
  are model diagnostics, and 21 are bookkeeping, unsupported or not comparable.
  A classification is not a pass: source coverage and denominators further limit
  which position/metric combinations can be assessed.
- Used the provenance-locked Wyscout England 2017/18 reference: 304 fitting
  matches and 76 held-out matches. This holdout was already used in calibration;
  this is an independent audit implementation, **not a new blind holdout**.
- Pooled counts over minutes for per-90 rates and pooled numerator/denominator
  counts for percentages. Compared GK, DF, MF and FW separately. For each featured
  club, standardized expected role shares to that club's minutes by position.
- Bootstrapped whole source matches 400 times with a fixed seed for descriptive
  95% reference intervals. These intervals describe sampling uncertainty, not
  engineering acceptance limits or prediction intervals for individual players.
- Used rate envelopes of ±max(35%, 0.30 per 90), percentage envelopes of ±10
  percentage points, mean-distance envelopes of ±max(25%, 3 metres), and team role
  share envelopes of ±12 percentage points. These are review heuristics, not a
  universal definition of realistic football. Numeric tolerances were fixed
  before the first run and were not widened after seeing its results.
- Reviewed featured individuals with at least 900 minutes against source-player
  1st–99th percentiles plus 25% of that interval's width (five points for
  percentages). Ratios require at least 30 denominator observations and ten
  eligible reference players. Small samples cannot validate penalty conversion.

The source definitions follow Wyscout's [progressive pass definition](https://dataglossary.wyscout.com/progressive_pass/)
and [pass definition](https://dataglossary.wyscout.com/pass/). Cross comparisons
include source corners ending in the box to approximate the generated corner
classification; this remains an approximation. Broad roles conceal differences
between fullbacks, centre-backs, wingers and central attackers. One competition
and season cannot represent every tactical style or career era.

## Results by position

All 57 original positional gates passed. Of 136 eligible extended position/metric
comparisons, 128 were within their envelope and eight were flagged:

| Position | Within envelope | Flagged | Findings |
| --- | ---: | ---: | --- |
| Goalkeeper | 25 | 0 | Several passing comparisons are ineligible; this is not an all-clear for goalkeeper distribution. |
| Defender | 33 | 4 | Too many box entries and backward passes; too few crosses; long-pass completion marginally below the envelope. |
| Midfielder | 36 | 1 | Too many completed progressive passes. |
| Forward | 34 | 3 | Too many completed progressive passes and final-third entries; long-pass completion marginally below the envelope. |

| Metric | Position | Generated | Reference holdout |
| --- | --- | ---: | ---: |
| Completed progressive passes /90 | MF | 10.90 | 6.67 |
| Completed progressive passes /90 | FW | 4.76 | 2.44 |
| Completed final-third entries /90 | FW | 3.13 | 1.77 |
| Completed box entries /90 | DF | 1.39 | 0.86 |
| Long-pass completion | DF | 53.13% | 63.13% |
| Long-pass completion | FW | 46.15% | 56.16% |
| Backward passes /90 | DF | 12.12 | 8.71 |
| Crosses /90 | DF | 1.01 | 1.83 |

The two long-pass percentage differences exceed the ten-point threshold by less
than 0.02 percentage points. Treat these as borderline diagnostics, not evidence
of a large realism defect. The progression and crossing discrepancies are more
substantial and recur across related measures.

There are 16 flags among 392 eligible club/role-share comparisons:

- All four clubs allocate too many outside-box shots to forwards and too few to
  midfielders. Forward shares are 57–61% versus roughly 40% in the standardized
  reference; midfielder shares are 25–32% versus roughly 45%.
- All four allocate too few crosses to defenders: 21–23% versus roughly 36%.
  Eastbridge also flags for defenders' share of completed crosses.
- Northport's defenders receive 32% of assists versus 13% in the reference, while
  forwards receive 25% versus 43%. Its forwards also take too small a share of
  inside-box shots: 51% versus 66%.

Two featured players, `np02` and `eb08`, narrowly exceed their role's expanded
individual envelope for completed progressive passes. Their excesses are about
0.03 and 0.17 per 90, respectively. These are review signals, not proof that an
individual performance is impossible. Multiple related checks are correlated;
the flag count is not a count of independent defects or a statistical error rate.

## Source quality and limits

The first audit exposed source-quality problems that would otherwise create
misleading goalkeeper failures. All source goal kicks lack completion tags, and
their origin coordinates are corner values `(0, 0)` or `(100, 100)` in the raw
0–100 coordinate system. They are unusable as actual goal-kick origins.

Protocol v1.1 excludes those coordinates, preserves unknown outcomes as unknown,
requires 95% source coverage for relevant pass count/geometry comparisons, and
adds minimum-denominator eligibility. Numeric acceptance envelopes are unchanged.
The initial run is retained locally at `var/player-position-audit-initial.json`.
Known-outcome pass accuracy remains conditional on recorded outcomes; it cannot
establish completion accuracy for the missing goal kicks. Unknown ground-duel
outcomes likewise do not become lost duels.

Continuous movement, carries, recoveries, intended targets of failed passes,
receipt identities, provider-aligned key passes/xA and measured ball speeds are
not externally validated by this source. Heatmap bins reconcile to recorded
actions, but their spatial realism is not established by this audit. xG and
expected passing are model-derived diagnostics, not independent provider truth.
Headers and woodwork remain withheld. Appearance/start/minute counts are schedule
bookkeeping. The machine-readable matrix explicitly records these limitations.

## Accounting and reproducibility

Zero row-level arithmetic errors and zero team reconciliation errors were found.
Checks include pass/shot/duel partitions; map and timing totals; nonnegative
counts; subset bounds; score conservation; assist and xA bounds; and, for generated
fixtures, pass receipts, opponent duel symmetry and saves versus shots on target.

The audit binds its result to hashes of the model, ledger, registry, analytics
artifact and original position report. It exports no raw real-player identities.
See [the complete pre-recalibration machine-readable report](player-position-audit-before-spatial.json) and
[the audit implementation](../../scripts/audit_player_distributions.py).

Run from the repository root:

```sh
.venv/bin/python scripts/audit_player_distributions.py --strict
```

Strict mode intentionally exits **1** while these findings remain unresolved.
Successful execution of an audit is different from passing its statistical gates.
Exact final command output and regression results are recorded below.

```text
{"matches": 844, "player_match_rows": 22870, "metrics": 71, "arithmetic_errors": 0, "team_reconciliation_errors": 0, "core_position_passed": 57, "core_position_checks": 57, "external_role_checks": 136, "population_flags": 8, "team_role_share_flags": 16, "individual_flags": 2, "report": "docs/verification/player-position-audit.json", "status": "needs_recalibration"}
```

```sh
.venv/bin/pytest -q tests/test_player_distribution_audit.py tests/test_position_calibration.py tests/test_player_analytics.py
```

```text
29 passed in 33.76s
```

```sh
.venv/bin/pytest -q
```

```text
710 passed, 1 warning in 71.90s (0:01:11)
```

The warning is the existing experimental evaluator warning. Eight new tests cover
catalogue completeness, source eligibility boundaries, missing observations,
small penalty samples, pooled rates, own-goal denominators, progressive-pass
thresholds, corner sentinel geometry, unknown duel outcomes, bootstrap
reproducibility and fixed acceptance envelopes. Passing tests verify the audit's
behaviour; they do not override its statistical findings.

SHA-256 checks confirmed all 13 personalization fixture files match the prior
verified calibration snapshot, the analytics artifact matches the initial audit,
and report input hashes match disk. `git diff --check` completed with no output.
No application/UI files changed during this pass, so no frontend rebuild or cloud
deployment was needed.

## Recommended next change

Recalibrate pass origins/endpoints, role-specific crossing, shot location ownership
and creation chains together. Introduce finer tactical roles where supported and
test on fresh simulation seeds, while preserving the existing goal, save, passing
and assist accounting. Do not patch profile totals or tune solely to silence
individual flags. Obtain a better-covered reference before claiming goalkeeper
spatial accuracy or continuous tracking realism. Re-run this audit after rebuilding
the event ledger and derived analytics, then review the resulting maps in Clubhouse.
