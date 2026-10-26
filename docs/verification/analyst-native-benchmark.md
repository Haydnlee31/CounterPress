# Native Analyst acceptance benchmark

Prepared 26 October 2026, before inspecting any native model responses. This is a curated, source-anchored acceptance set, **not** a random sample or a statistical estimate of unseen model accuracy. Cases were chosen from original canonical event records, with handwritten expected counts and meanings. It does not generate its answer oracle from the application's diagnostic signals.

## Original v7 regression cases

| Case | Replay cutoff | Independent expectation |
|---|---|---|
| Archive box growth | `wyscout-2058017`, H1 43:01 | Northport trailing1–2; current five-minute shots3, prior0; all3 inside the box. Explain the increased close-range threat without reversing the score or claiming a defensive formation. |
| Activity without shots | Generated match, H1 10:30 | Eastbridge35/49 on-ball actions, no shot, **one** final-third pass entry,0–0. Describe limited penetration. “No entries” and time-possession claims are incorrect. |
| Turnover into equalizer | Generated match, H1 34:56 | Northport failed pass→Eastbridge recovery→goal, source events `a00498`–`a00500`; recovery-to-shot7.975s. Score becomes1–1. Explain the transition; do not infer a coordinated press. |
| Focused-player link | Generated match, H2 38:34 | Isaac Lane (`np10`), Simplified Chinese: six current-window passes and a shot. Failed pass→recovery→linked exchange→off-target shot, `a01164`–`a01168`; recovery-to-shot13.860s. Score2–2. Do not say he scored or confuse prefix totals with current-window counts. |
| Early quiet window | `wyscout-2058007`, H1 1:31 | Score0–0; Eastbridge no shot. Too early for complete five-minute comparisons. Abstention or limited observations are appropriate; sustained trend/turning-point claims are not. |
| Other archive chances | `wyscout-2058007`, H1 18:01 | Eastbridge current shots3 versus prior0, with2 inside the box; still0–0. Explain opportunities without inventing scoring, physical speed or calibrated xG. |

The generated match ID is `synthetic-32fe41c5d304ce68d7d9`. There was no independently located current-data window satisfying strong action dominance **and zero** final-third entries **and zero** shots; the activity case intentionally tests the nearby truthful pattern rather than manufacturing a perfect trigger example.

For the historical v7 run, two additional direct Editor checks submitted plausible-looking but false readings with otherwise valid IDs: a wrong-team chance claim, and an unsupported off-ball defensive-line/fullback-shape claim. Both were expected to produce no accepted role; both failed, as recorded below. After the structural correction, arbitrary Editor prose is no longer a publication input. The fresh benchmark tests invalid candidate IDs and altered prose against the actual deterministic publication gates.

## V8 fresh source cases and structural acceptance

The six original windows are now **regressions**, not blind tests. Two additional windows were selected and their source counts frozen before any v8 paid benchmark output; both align with the API's minute clock:

| Fresh case | Cutoff | Independent source expectation |
|---|---|---|
| Outside-box shift | `wyscout-2058017`, H2 23:00 | Eastbridge current1 shot, outside the box; previous3 shots including2 inside. Score4–1. Describe the category change, not a proven increase in Euclidean distance, tactical cause, or calibrated xG. |
| Passing and progression | `wyscout-2058017`, H2 31:00 | Northport completed24/28 passes in the previous window versus11/18 current; final-third entries5→2. Score4–2. Link reliability and penetration without inventing defensive pressure or individual causes. |

The new native architecture selects immutable, source-bound bilingual candidates. Two **offline** adversarial probes test the real native selector/product provider: an invented candidate ID cannot publish, and unsupported off-ball prose with valid IDs cannot pass exact-reading equality. These establish boundary behavior, not a general model factual-accuracy estimate. Source-based semantic tests and manual review remain necessary to assess candidate correctness and usefulness.

V8 reserves at most40 evaluation calls for eight workflows and US$0.80 admission allowance; quiet/no-candidate windows can use zero actual model calls. It keeps the existing240/hour and600/rolling24h shared evaluation limits and stops if fewer than40 reservations remain. The previous32-call budget description below refers to the historical v7 run. Both runs' raw receipts and public summaries are retained separately; v7 is never overwritten.

Offline v8 command: `.venv/bin/python scripts/evaluate_analyst_native.py --run-id preflight-20261026-v8`.
Paid v8 command after explicit native smoke approval: `.venv/bin/python scripts/evaluate_analyst_native.py --azure --run-id native-acceptance-20261026-v8`.

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

## Director v7 live results — activation blocked

The current-version technical/manual smoke passed before this fixed run. The benchmark then executed once using directorv7, four GPT-4.1-mini specialists and the GPT-5-mini Editor v4. No prompts or cases were tuned during the run.

| Check | Result |
|---|---|
| Native workflows completed | 6/6, all `partial` |
| Readings published | 12 across the six workflows; this is availability, not accuracy |
| Workflow latency | 20.736–24.381 seconds; median21.413 seconds |
| Actual reported workflow calls | 30, plus2 direct Editor calls |
| Evaluation reservations | 32 calls |
| Analyst allowance reservation | US$0.80; not actual Azure billing |
| Direct adversarial rejection | **0/2**; both false readings accepted |
| Source-based qualitative review | **17/36 points**, reviewed by the assistant, not human participants |
| Core grounding dimension | Passed only the recovery/equalizer case; other cases have material qualification, actor, temporal or provenance errors |
| Activation decision | **Do not enable v7 for users** |

The six workflows report127,647 input tokens and4,461 output tokens; the two direct Editor checks add14,906 input and72 output tokens. These are provider-reported counters, not a billing statement or model-price breakdown.

Concrete failures retained in the private raw records:

- A drop in `verified_turnovers` was interpreted as improved retention by the named club. The metric actually counts **opponent failed passes recovered by that club**. The actor/direction was reversed.
- Event action share was promoted to “possession dominance,” and uncalibrated shot-location estimates were called xG without qualification.
- The focused-player input demonstrably contained `language=zh-Hans`, `focus_player_id=np10`, `depth=analyst`; the output was entirely English, used a raw player ID, and retained no player-specialist reading.
- The early1:31 case produced high-confidence dominance language from55.56% event share. An18:01 case invented an “early second quarter.”
- Some alternatives invented tactical posture or intent; one defensive reading inferred pressing success without pressure evidence.
- The explicit wrong-team and unsupported off-ball-shape adversarial readings were both accepted by the actual Editor. The Azure specialist subsequently confirmed the returned model, agent version and instructions matched GPT-5-mini Editor v4: this was not simply a stale-definition explanation.

The correct recovery→goal→equalizer facts show the plumbing can deliver useful evidence, but the explanation mostly repeats an event and cumulative totals. Structural grounding and usefulness need improvement before activation.

### Focused remediation, before another paid acceptance run

1. **Make metric semantics unambiguous.** Rename or explicitly bind recovered-opponent-pass counts to the recovering actor; include human labels, basis and window definitions in each compact fact rather than relying on an ambiguous metric ID.
2. **Require actor-scoped, typed factual claims.** Agents should select claim IDs with club/player/window/basis bindings and permitted comparisons. Validate the selected claims deterministically; do not accept arbitrary prose solely because IDs exist or a second model approves it.
3. **Keep strict output provenance.** Event-share facts cannot become possession-time facts; geometric chance estimates must retain the estimate label. Unknown tracking cannot support defensive-line, width or pressing-shape claims.
4. **Bind real phase metadata.** Use actual fixture period lengths and explicit boundary flags. No invented quarters; no fixed45-minute boundary when the replay includes stoppage time.
5. **Enforce the requested language and player focus.** Include them in the verifier proof, validate output script/language, and reject untranslated/default-English responses for Simplified Chinese. Resolve player IDs through the roster before display.
6. **Assess usefulness separately from correctness.** Require a pattern, consequence, bounded alternative and specific next observation; correct event narration alone is not a useful analyst result.
7. **Retest without overclaiming.** Treat these now-seen cases as regression tests; choose additional unseen windows for the next acceptance check. Record abstentions/partial roles rather than making every specialist speak.

Reviewed public report: `docs/verification/analyst-native-benchmark-native-acceptance-20261026-v7-reviewed.json`. Raw evidence stays in ignored `var/analyst-native-benchmark/native-acceptance-20261026-v7/`. Attaching this review made no additional model calls.

## Director v8 live results — bounded selection passes

The v8 native smoke passed before the new run. Six previously seen windows were replayed as regressions; two additional minute-aligned windows had source expectations frozen before execution. During this run no cases, candidate wording, or prompts were tuned.

| Check | Result |
|---|---|
| Meaningful windows | 7/7 `complete`; ten specialist readings in total |
| Quiet early window | `insufficient_evidence`, no reading and zero model calls |
| Workflow latency | 11.652–17.719 seconds; median16.032 seconds |
| Actual reported model calls | 17; only specialists with candidates plus the Editor run |
| Conservative evaluation reservations | 40 calls, with existing daily/hourly guards unchanged |
| Analyst allowance reservation | US$0.80; not actual Azure billing |
| Provider-reported tokens | 32,372 input;499 output |
| Publication attacks | 2/2 rejected, offline: fabricated candidate ID and modified prose with valid IDs |
| Assistant source-based usefulness review | 41/48; no material factual errors found in these eight curated windows |
| Fresh held-out cases | Both complete and source-correct: outside-box shift and passing/progression decline |
| Focus/language | Chinese Isaac Lane case retains the player reading and selects it as lead |

Public receipts: `analyst-native-benchmark-native-acceptance-20261026-v8.json` and the explicitly assistant-attributed `...-v8-reviewed.json`. The historical v7 reports remain separate and unchanged.

The41/48 score is **not** a claim of85% factual accuracy, a human usability result, or a statistically representative model benchmark. The safe quiet-window abstention receives zero for three absent analysis dimensions. Two simple chance readings lose points because they repeat a location/shot pattern without enough match consequence and use generic short-window caveats. A blocked-shot alternative still says “closer positions”; “box positions” would be less ambiguous in a later copy pass. The regains-to-equalizer and focused-player chains provide stronger concrete significance.

The principal architectural change is constrained publication: native agents select and edit among deterministic, source-bound candidates instead of originating unrestricted factual prose. This eliminates the specific unchecked-prose failure path measured in v7, but limits novel insight to implemented candidate families. It does not provide camera-derived defensive shape, measured running/sprint distance, or video auto-eventing. Model selection quality and coverage still warrant broader evaluation and real user review.

Recommendation: the observed source/publication gates support enabling the bounded implementation after the parent integration/UI checks pass. Preserve explicit unavailable metrics and do not market it as unrestricted live tactical video analysis. No further model calls were made to attach this review.
