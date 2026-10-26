# Native Analyst acceptance benchmark

Prepared 26 October 2026, before inspecting any native model responses. This is a curated, source-anchored acceptance set, **not** a random sample or a statistical estimate of unseen model accuracy. Cases were chosen from original canonical event records, with handwritten expected counts and meanings. It does not generate its answer oracle from the application's diagnostic signals.

## Cases

| Case | Replay cutoff | Independent expectation |
|---|---|---|
| Archive box growth | `wyscout-2058017`, H1 43:01 | Northport trailing1–2; current five-minute shots3, prior0; all3 inside the box. Explain the increased close-range threat without reversing the score or claiming a defensive formation. |
| Activity without shots | Generated match, H1 10:30 | Eastbridge35/49 on-ball actions, no shot, **one** final-third pass entry,0–0. Describe limited penetration. “No entries” and time-possession claims are incorrect. |
| Turnover into equalizer | Generated match, H1 34:56 | Northport failed pass→Eastbridge recovery→goal, source events `a00498`–`a00500`; recovery-to-shot7.975s. Score becomes1–1. Explain the transition; do not infer a coordinated press. |
| Focused-player link | Generated match, H2 38:34 | Isaac Lane (`np10`), Simplified Chinese: six current-window passes and a shot. Failed pass→recovery→linked exchange→off-target shot, `a01164`–`a01168`; recovery-to-shot13.860s. Score2–2. Do not say he scored or confuse prefix totals with current-window counts. |
| Early quiet window | `wyscout-2058007`, H1 1:31 | Score0–0; Eastbridge no shot. Too early for complete five-minute comparisons. Abstention or limited observations are appropriate; sustained trend/turning-point claims are not. |
| Other archive chances | `wyscout-2058007`, H1 18:01 | Eastbridge current shots3 versus prior0, with2 inside the box; still0–0. Explain opportunities without inventing scoring, physical speed or calibrated xG. |

The generated match ID is `synthetic-32fe41c5d304ce68d7d9`. There was no independently located current-data window satisfying strong action dominance **and zero** final-third entries **and zero** shots; the activity case intentionally tests the nearby truthful pattern rather than manufacturing a perfect trigger example.

Two additional direct Editor checks submit plausible-looking but false readings with otherwise valid IDs: a wrong-team chance claim, and an unsupported off-ball defensive-line/fullback-shape claim. Both should produce no accepted role. These test the actual model verifier, whereas unit tests only establish rejection mechanics.

## Cost and safeguards

The script defaults to offline preparation and source-anchor checking. Paid execution uses the existing product `FoundryAnalyst` provider and exact pinned Foundry coordinator version, with no retries. It must run only after the parent/native deployment owner explicitly confirms the current version's smoke passed.

- Six native workflows reserve five model calls each; two direct Editor requests reserve one each: **32 calls maximum**, below the45-call ceiling for this task.
- Before any model call, check and reserve against the existing evaluation ledger `var/footie-evaluation-budget.sqlite3`,240/hour and600/rolling24h. If32 calls are not available, stop; do not increase limits.
- Each workflow/direct Editor check also uses `Allowance` with the shared local Analyst ledger `var/analyst-local-allowance.sqlite3`. Eight10-cent reservations total **US$0.80**. Failed or uncertain calls remain charged; this is a conservative allowance, not metered Azure billing.
- Private inputs/replies go to a mode700 run directory under `var/analyst-native-benchmark/`, with mode600 files. Public JSON contains case anchors, execution metadata, review status and aggregate results, never project endpoints, account identifiers or credentials.
- Reusing a paid run ID is rejected to preserve evidence. Manual review attaches to an existing execution report and never reruns models.

## Commands

Offline preflight, no network/model calls:

```sh
.venv/bin/python scripts/evaluate_analyst_native.py --run-id preflight-20261026
```

Recorded output:

```text
{"status": "complete", "mode": "offline_preflight", "cases": 6, "cloud_calls": 0, "public_report": "docs/verification/analyst-native-benchmark-preflight-20261026.json", "quality_review": "pending_human_review"}
```

After the current native version has passed its live smoke:

```sh
.venv/bin/python scripts/evaluate_analyst_native.py --azure --run-id native-acceptance-20261026
```

Optional private config/manifest paths are arguments; do not put their contents or endpoint values on the command line. The default paths are existing ignored files in `var/`.

## Quality review

Inspect each saved packet, handwritten case expectation and actual readings. Give one point each for six dimensions:

1. Grounding: correct entity/time/facts, no unsupported physical or causal claim.
2. Pattern: connects evidence into meaningful analysis, rather than repeating an event; appropriate restraint is accepted for the quiet case.
3. Consequence: explains supported relevance to opportunity, progression, score or contribution.
4. Alternative: gives a specific plausible uncertainty, not a canned counterstory.
5. Next observation: suggests an observable next check, rather than a forecast or coaching order.
6. Audience: respects language, depth and chosen player.

Record binary values under `grounded`, `pattern`, `consequence`, `alternative`, `watch_next`, and `audience`, plus a concrete `rationale`, keyed by case ID. Null/missing/provider-error results are not automatically quality successes. A failed grounding dimension is a release concern even if the other dimensions score well. Do not label a keyword search or valid citation membership “100% factual accuracy.”

Attach the human-authored review without model calls:

```sh
.venv/bin/python scripts/evaluate_analyst_native.py \
  --review-existing docs/verification/analyst-native-benchmark-native-acceptance-20261026.json \
  --review var/analyst-native-benchmark/reviewer-ratings.json
```

Until live execution and manual review complete, the correct status is **prepared; model quality unverified**. Partial specialist responses, abstentions, latency, rejected adversarial claims and operational failures must all remain visible in the report. A32-call reservation does not imply32 successful or fully reported provider calls.
