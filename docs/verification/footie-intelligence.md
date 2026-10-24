# Footie intelligence verification

Status: local implementation and independent acceptance work in progress, 23 October 2026.
No results here establish human usability, unseen model accuracy or hosted delivery.

## Independent expectations

`tests/test_intelligence_adversarial.py` uses a separately authored six-action sequence:

| Time | Recorded observation |
| --- | --- |
| 1 s | Home player h1 establishes control at x=20 m |
| 2 s | h1 passes to h2, x=20→45 m |
| 3 s | Away player a1 applies pressure; no recovery is recorded |
| 4 s | h2 passes to h3, x=45→75 m |
| 7 s | h3 carries from x=75→90 m |
| 9 s | h3 shoots from x=90 m and scores; outcome becomes available at 9.5 s |

Expected results were written independently of the reducer: two completed passes,
one recorded carry segment, three participating attacking players, eight seconds
from recovery to shot and 70 m net progress to the **shot origin**. There is no
inferred assist. Defending pressure neither breaks control nor counts as a regain.

Additional checks cover missing possession starts, restarts, uncertain pass outcomes,
opponent control, prior shots, period boundaries, missing coordinates and recipients,
archive metric coverage, duplicate deliveries, stale revisions, corrections,
retractions and availability cutoffs. Window checks independently verify `(start,end]`
boundaries, equal durations, sample eligibility and a no-change control.

The existing library supplies a separate real-data regression: event `e01178` in
`career-showcase-southbank-redhaven` is a free kick following restart `e01177`.
Its observed buildup is 1.2 seconds, zero passes and one player. The earlier
keeper recovery must not make it a counterattack. These figures were established
by reading the canonical records, not by accepting the new function's result.

## Baseline preserved

Before new integration changes, the existing assistant tests ran:

```sh
.venv/bin/python -m pytest -q tests/test_assistant.py tests/test_assistant_moments.py tests/test_assistant_multiagent.py tests/test_assistant_research.py tests/test_assistant_narrative.py tests/test_assistant_evaluation.py
```

Output:

```text
240 passed in 61.57s (0:01:01)
```

The independent 48-case question corpus contains 32 supported requests, eight
clarifications and eight unsupported requests. It includes all three intelligence
journeys, existing career anchors, English and Simplified Chinese, viewer preferences,
unavailable data and misleading premises. The expected facts are authored constants,
not answers produced by the same analytical functions under test.

The old backend was extracted from commit `7ce9b8` into a temporary directory.
The same scorer ran against that frozen code via `PYTHONPATH`:

```sh
PYTHONPATH=/tmp/footie-intelligence-baseline-7ce9b8/backend .venv/bin/python scripts/evaluate_footie_intelligence.py --label baseline --output var/footie-intelligence-baseline-7ce9b8.json
```

Results: **8/32 supported**, **7/8 clarification**, **4/8 unsupported**. No model
calls. This establishes the old deterministic lookup's capability boundary;
it does **not** measure the old Azure model workflow or prove multiagent superiority.

## Evaluation rules

- Preserve the first outcome, source fingerprints, corpus fingerprint and call usage.
- Score supported requests separately. Refusals must not inflate useful completion.
- A local lookup test cannot demonstrate model interpretation quality.
- Questions used to fix code or prompts become regression cases on repeat. Do not
  describe their later pass rate as fresh unseen accuracy.
- Automated factual and scope anchors do not judge every explanatory sentence.
  Human review of helpfulness, implied causality and audience differences is still required.
- Paid evaluation is explicit (`--azure`), uses the existing shared persistent
  admission ledger and allows at most 80 provider requests per invocation.
- Unfinished or source-changing runs are reported as incomplete. Reports cannot
  overwrite existing files.
- Hosted event delivery, correction recovery, narration, browser interaction and
  Foundry trace linkage require separate checks; they are not established by this CLI.

## Findings during independent review

1. The initial buildup reducer rejected the canonical carry outcome `controlled`,
   truncating chains at the last carry. This affected both the authored sequence
   and the library free-kick case. The outcome support was corrected; the 28-case
   independent suite then passed in 0.51 seconds.
2. Recovery counters must distinguish confirmed control from unknown outcomes.
   An additional adversarial assertion has been added for this boundary.

Candidate integration results and live evaluation will be appended after the
implementation and scorer contracts are stable.

## First candidate — preserved, local lookup only

```sh
.venv/bin/python scripts/evaluate_footie_intelligence.py --label first_holdout --output var/footie-intelligence-first-local.json
```

First recorded outcome with corpus v1: **22/32 supported**, **8/8 clarification**,
**4/8 unsupported**, **zero model requests**. Source fingerprints were unchanged
during this run. This is the first deterministic lookup outcome, not a live-model
result. Its report has not been overwritten.

An independent label audit then found **one oracle error**: `performance_08` asks
about Enzo Clarke at 72:12.996, but his canonical appearance starts at 78:00. The
application correctly returned clarification. Corpus v2 moves this unchanged
question to clarification (31 supported / 9 clarification / 8 unsupported).
The original corpus is preserved as `var/footie-intelligence-questions-v1.json`.
Under this corrected classification the unchanged first output is **22/31**
supported, **9/9** clarification and **4/8** unsupported; this is a relabelled
interpretation of the same run, not a second result or model improvement.

Observed implementation gaps included unsupported intent falling into unrelated
match answers (running-distance and future-winner questions), plus natural-language
variants not recognized by local lookup. The latter require a separate live-model
interpretation test; adding a regex for every held-out sentence is not evidence of
better AI reasoning. Once these outcomes inform changes, this corpus is regression
material. A fresh later corpus is required for a renewed unseen-quality claim.

The independent/tool/integration checks also ran:

```sh
.venv/bin/python -m pytest -q tests/test_intelligence_adversarial.py tests/test_intelligence_tools.py tests/test_assistant_intelligence.py
```

```text
85 passed in 15.59s
```

This includes the repaired explicit-unknown-player boundary: asking about an
unregistered named player while a different profile is selected must clarify,
not substitute the selected player's statistics.

## Independent follow-up corpus and comparison protocol

A separate 40-question corpus is frozen at
`fixtures/assistant/intelligence_fresh_questions.json` with SHA-256
`2a20b63cd165da5e8d03fef108ebed37e75d70cb2076250a314a08bb261fe12d`.
It has 30 supported questions, five clarifications and five unsupported questions.
The supported set covers ten buildup questions, six player-performance questions,
six window comparisons, four career questions and four compound requests.
Question text was not sent to implementation agents. Request-schema validation
ran before model evaluation; one preference envelope was corrected to include the
favorite club required by its primary-club choice. No answer was executed during
that preflight.

Numerical oracles include independent raw-event clock/coordinate arithmetic for
several different goal sequences and direct raw-ledger tallies attached to exact
club/window scopes. Assertions distinguish observed partial chains from established
regains and retain null metrics where observations cannot establish a value.

The evaluator accepts `--corpus PATH` and captures synthetic question text,
rendered text, narrative blocks and visuals for subsequent human explanation review.
All backend assistant modules, the shared Azure authentication module, manifest,
corpus and evaluator are fingerprinted. Corpus IDs `fresh_01`–`fresh_20` and
`fresh_21`–`fresh_40` form two batches within the 80-provider-call invocation limit.

`--azure --single-agent` runs the existing `ResearchAgent` through the same service,
typed Plan catalog, model configuration, cases and factual scorer. Its production
limit remains **two provider calls / one tool invocation / 12 seconds**, compared
with the multiagent workflow's **four provider calls / 24 seconds**, delegation and
optional follow-up. This is a comparison of existing workflow configurations,
**not an equal-budget causal ablation**. Compound tasks also expose the existing
single-agent's one-query expressiveness limit. Role-neutral scoring tests ensure
a correct answer is not penalized merely for using one agent.

The user approved increasing the persistent evaluation ceiling to 600 provider
requests per day; the existing ledger is retained and each invocation remains
limited to 80 calls. This approval does not establish any evaluation result.
The fresh core-quality gate remains **unmet until the actual live results and
prose review are recorded**.

The repaired unsupported-intent boundary received a separate local regression:

```sh
.venv/bin/python scripts/evaluate_footie_intelligence.py --label regression --case unsupported_01 --case unsupported_02 --case unsupported_03 --case unsupported_04 --case unsupported_05 --case unsupported_06 --case unsupported_07 --case unsupported_08 --output var/footie-intelligence-unsupported-regression.json
```

Result: **8/8 unsupported requests passed**, zero model calls. This is targeted
regression evidence, not fresh model accuracy. Independent adversarial/scorer
checks after the comparison changes: **37 passed in 4.20 seconds**.

## First live 40-case holdout — core gate not met

The two unmodified reports are `var/footie-intelligence-fresh-a.json` and
`var/footie-intelligence-fresh-b.json`. Both record unchanged source fingerprints.
Independent review found **no oracle errors** in this corpus. Results:

| Journey | Strict successful workflow / supported questions |
| --- | ---: |
| Goal buildup | 10 / 10 |
| Player performance | 4 / 6 |
| Completed-window changes | 3 / 6 |
| Career history | 4 / 4 |
| Compound match and career requests | 1 / 4 |
| **Supported total** | **22 / 30 (73.3%)** |

Clarification: **5/5**. Unsupported: **5/5**. Those are separate status/safety
checks and do not inflate the supported completion rate. One supported response
had all factual anchors correct but timed out to a lookup fallback; the strict
workflow scorer intentionally did not count it as successful model completion.

There were **61 provider requests**, **152,156 reported tokens**, and **three
requests with unreported usage**. These figures are not a dollar-spend estimate.
Supported-request latency: **p50 7.834 s; p95 18.079 s**. Thus both the proposed
90% completion target and eight-second p95 target were missed.

The central product failures were scope and routing, not the independently checked
arithmetic: irrelevant season fields invalidated a match analysis; a within-match
"recent" request was routed as career research; a pattern question received the
score instead; compound requests dropped clauses or applied a player from the
career clause to the selected goal. The preserved output cannot be relabelled as
a passing AI benchmark merely because its fallback numbers were truthful.

### Independent explanation review

No invented numerical claim, incorrect returned player attribution or future-event
reference was observed in this 40-case review. This is bounded sample evidence,
not a universal guarantee. Additional issues were visible beyond automated checks:

- A question asking whether a regain was established received a partial-buildup
  summary, without explicitly answering that the regain was unknown.
- A partial sequence used "1 players" and led with zero completed passes; the
  fan explanation could instead lead with the observed carry and finish.
- Player-performance summaries emphasize selected on-ball rates. The scorer's
  two goals were omitted while lower shot volume was emphasized, so this is a
  narrow involvement view rather than a comprehensive performance assessment.
- Two clarification cases passed status checks but returned a generic capability
  list instead of asking which match or favorite player the fan meant.
- A failed compound request supplied a goal/milestone answer while silently
  omitting the separately requested season statistic.

The initial diagnostic single-agent sample proposed from this corpus was IDs
`fresh_01`, `fresh_05`, `fresh_11`, `fresh_12`, `fresh_19`, `fresh_21`, `fresh_23`,
`fresh_25`, `fresh_27`, `fresh_30`. It is a purposeful diagnostic sample, not a
random accuracy estimate. After implementation changes, comparisons must not
pair a new single-agent runtime with this old multiagent run and imply a
controlled architecture comparison.

## Final untouched wording set prepared

A third set, `fixtures/assistant/intelligence_final_holdout.json`, is frozen with
SHA-256 `e5705b131e5dc2816c4811be03cdb9b487aac44f9efb8201c25c7756efaaee93`.
It has the same 30 supported / five clarification / five unsupported composition,
with new independently authored wording and the already verified raw-data oracles.
This measures new wording and task composition on known fixtures; it does **not**
measure generalization to unseen matches. Only request-schema preflight ran during
preparation. No answers were executed, and question text was withheld from the
implementation agents.

The matched single-agent subset is precommitted **before any new outputs**:
`final_01`, `final_05`, `final_11`, `final_12`, `final_19`, `final_21`, `final_23`,
`final_25`, `final_27`, `final_30`. Evaluate these against their corresponding rows
in the final multiagent run on exactly the same frozen source. This avoids an
extra multiagent sample and keeps the two-call vs four-call comparison limitation
explicit. The first live holdout above is now regression material because its
results informed changes. The core quality gate remains unmet pending fresh
results and review; no later retry replaces its 73.3% first score.

### Frontend regression readiness check

A full frontend run intermittently failed the existing Breakdown phase-seek
assertion (expected slider `700`, observed `0`); the focused test and an unchanged
full rerun passed. No deterministic production playback defect was established.
The test now awaits the async initial render/snapshot commit inside `act` before
clicking a phase, so initialization effects finish before the user interaction.
The exact seek target and all player/phase assertions remain unchanged. Production
UI source was not changed for this investigation.

```text
npm test -- src/explore/ExploreData.test.tsx --maxWorkers=2 --reporter=dot
Test Files  1 passed (1)
Tests  4 passed (4)
Duration  2.04s

npm test -- --maxWorkers=2 --reporter=dot
Test Files  35 passed (35)
Tests  207 passed (207)
Duration  26.75s
```

Full-run log: `var/intelligence-frontend-readiness.log` (local, ignored).

## Final live evaluation and independent audit — 23 October 2026

The third corpus's **first** live run is preserved in
`var/footie-intelligence-final-a.json` and `var/footie-intelligence-final-b.json`.
The implementation had not seen these new question wordings before that run.
Both batches used identical source hashes and the frozen corpus hash above.
Results were **28/30 supported (93.3%)**, **4/5 clarification**, and **4/5
unsupported**. Compound requests passed **2/4**. Supported latency was **p50
5.538 s; p95 9.126 s**. There were 72 provider requests, 82,938 reported tokens
and two attempts without usage reporting. The four failures concerned a common
noun mistaken for a player name, a silently omitted historical clause, a missing
context request labelled unsupported, and an unsupported speed request labelled
clarification. These first scores remain unchanged after subsequent fixes.

The precommitted ten-case comparison in
`var/footie-intelligence-final-single.json` used the **same source and corpus
hashes as that first run**: multiagent **9/10**, single-agent **8/10**. The one
additional success combined current-match performance with a prior-season goal
total. Multiagent used 25 calls and 32,221 reported tokens on those ten cases
(p50 5.812 s; p95 9.160 s); single-agent used 19 calls and 34,706 reported tokens
(p50 4.141 s; p95 8.944 s). This small, purposeful, nonrandomized sample compares
existing workflows with unequal four-call/two-call limits. It demonstrates one
compositional benefit, not broad superiority or an equal-budget ablation.

### Post-fix live regression

`var/footie-intelligence-final-regression.json` reruns all 40 already-seen cases.
It is explicitly labelled **regression**, not fresh accuracy. Results:

| Check | Result |
| --- | ---: |
| Supported requests | 30/30 |
| Compound match/history requests (included above) | 4/4 |
| Clarification requests | 5/5 |
| Unsupported requests | 5/5 |
| Provider requests | 74 |
| Reported tokens | 89,231 |
| Unreported usage attempts | 0 |
| Supported-request latency, p50 / p95 | 6.071 s / 10.875 s |
| All-request latency, p50 / p95 | 5.679 s / 9.156 s |

Independent inspection confirmed no source changes during the run; all 36
fingerprinted files still matched their recorded hashes at audit time. Corpus
content remained unchanged. All 30 supported responses completed the model
workflow, and all four compound responses contained both specialists' requested
results. No partial-specialist failures or narrative-composition fallbacks were
reported. One clarification (`final_32`, no favorite player selected) used the
safe calculated fallback after specialist validation rejected a missing player;
therefore **40 scored passes does not mean 40 model-completed responses**.

The audit read every response's text and selected narrative, checked the previously
failed scope/entity cases, and inspected temporal evidence checks. No fabricated
numeric claim, wrong returned player, or future-event reference was observed in
this bounded sample. Optional follow-up pass totals were separately counted from
raw fixture events: Zane Bell 3, Nico Alder 2 and Nolan Darby 55 completed passes
at their respective selected-goal cutoffs, matching the displayed 33.3%, 50% and
1.8% buildup shares. Cross's 17-pass denominator had been independently checked
in the first-run audit. These checks do not establish universal correctness.

Remaining presentation limitations are material: the unknown-possession-start
question still receives a summary without directly saying the regain is unknown;
the short carry-and-shot sequence is described mainly by zero passes; a broad
goalkeeper performance question covers passing rather than saving; the Chinese
career answer retains the English unit “goals”; unsupported responses use a
generic capability message. Grammar and timing precision improved (“1 player,”
“about 16 seconds”). Human usefulness has not been measured by this audit.

The regression repairs are verified for this known corpus, but the **eight-second
supported p95 target remains unmet**. The fresh-wording result remains 93.3%,
not 100%, and this corpus tests known synthetic fixtures rather than unseen-match
generalization. No source edits or paid calls were made by the independent auditor.

### Final frontend and browser pass

```text
cd frontend
npm test -- --maxWorkers=2 --reporter=dot
Test Files  35 passed (35)
Tests  208 passed (208)
Duration  28.50s

npm run build
✓ built in 2.51s
```

Local logs: `var/intelligence-frontend-complete.log` and
`var/intelligence-frontend-build.log`. Browser checks used the lookup-only local
preview on port 8027; no model calls were made through the browser. Live Azure
connectivity/model execution was checked separately by the recorded evaluator.

Verified the goal explanation opens the corresponding Mateo Cross highlight with
22 active players, finishes playback, and opens Ask Footie at the selected goal's
revision/time without submitting automatically. Submitting in that embedded panel
retains the correct free-kick and score-change explanation. The standalone and
embedded inputs have distinct IDs and their own labels. Desktop comparison cards
use two columns; a 390px mobile viewport uses one column without horizontal
page overflow. Temporary viewport overrides were reset. Browser console errors
were empty at the recorded check.

Final desktop proof: `var/footie-intelligence-final-preview.jpg`. Earlier mobile
proof: `var/footie-intelligence-mobile.jpg` and
`var/footie-intelligence-comparison-mobile.jpg`. Match-context selection now uses
recorded half lengths rather than assuming the second half lasts 45 minutes;
the 48-minute second-half request is covered by an independent UI assertion.

### Local Foundry artifact preparation

```sh
.venv/bin/python scripts/export_intelligence_foundry.py --report var/footie-intelligence-final-regression.json --corpus fixtures/assistant/intelligence_final_holdout.json --output-dir var/foundry-intelligence-final-regression
```

```json
{"scored_rows": 40, "exported_rows": 40, "excluded_rows": 0, "network_calls": 0, "model_calls": 0}
```

This preserves the regression label, failed/partial execution metadata when
present, hashes and original scores. It does not upload to Foundry or fabricate
native tool-message traces. Managed identity is implemented and mock-tested but
not enabled in Azure; hosted career revision ingestion and the additional Speech
readout remain gated follow-on work. Production and its model limits are unchanged.

### Final backend verification and probe repair

```text
.venv/bin/python -m pytest -q
1 failed, 1245 passed, 1 warning in 649.79s (0:10:49)
```

The sole failure was
`test_cosmos_live_probe_logic_checks_conflicts_restart_and_revision_invalidation`.
It reproduced in isolation. The old verification script constructed a
`SimpleNamespace` with an invalid mock endpoint; the new shared authentication
helper correctly requires a validated `AzureConfig`. Updated only the probe's
`mock_config()` to return that typed configuration. Its inference transport
remains `httpx2.MockTransport`, key is a fixed dummy and no real provider request
is made. Production authentication validation was not relaxed.

```text
.venv/bin/python -m pytest -q tests/test_editorial_live_checks.py tests/test_model_identity.py tests/test_editorial_evaluation.py
39 passed, 1 warning in 21.62s
```

The focused rerun covers the original failure, both Cosmos probe seed/restart
checks, authentication compatibility and the frozen editorial evaluation. The
broader 1,246-test run was not repeated after this probe-only repair. Its 1,245
passing tests plus the repaired test and related 39-test pass are the actual
verification evidence; do not represent this as a fresh all-green full-suite run.
The warning is the existing Agent Framework evaluator experimental-API notice.
`git diff --check` passed. Logs are `var/intelligence-backend-final.log` and
`var/intelligence-probe-auth-recheck.log`.

No changes have been committed, pushed or deployed during this increment. The
local preview is http://127.0.0.1:8027/?story=last-gasp#assistant and uses deterministic
lookup mode. The live 40-case regression separately exercised Azure model calls.

### 23 October 2026 increment: transport reuse and explanation checks

The subsequent latency experiment used three **precommitted** cases (`final_12`,
`final_19`, `final_27`), chosen before the new outputs to fit the remaining approved
600-call rolling allowance. Reports are `var/footie-latency-before-reuse.json`
(frozen earlier backend) and `var/footie-latency-after-reuse.json` (candidate).
Both used the same evaluator/observer script hashes, corpus hash, questions and
case order, with `--warm-app`: one app/event loop per run, no paid priming, and
the first request included. Startup was reported separately (3.603 s before,
1.197 s after). Both runs passed **3/3**, consumed **eight provider calls** each,
and reported no partial failures or missing usage. Sources were stable within
each run; the backend hashes differ intentionally because it is a before/after
comparison.

| Request | Before | After |
| --- | ---: | ---: |
| Goalkeeper performance (`final_12`) | 11.066 s | 5.243 s |
| Completed-window changes (`final_19`) | 6.918 s | 3.733 s |
| Goal buildup plus pre-match career total (`final_27`) | 7.865 s | 7.992 s |

These are **three end-to-end diagnostics, not a release p95 benchmark**. Offline
tests overlapped the baseline run but not the candidate, so machine load was not
controlled. The candidate also adds goalkeeper saving/conceding facts, changing
that request's work and response. Provider variation, workload and pooling are
not isolated; no causal percentage speedup is established. The small sample does
not supersede the previous full 30-supported-case p95 of 10.875 s.

Candidate metadata confirms that the compound request's match and career query
stages overlap. Its route stage took about 4.001 s and its career query 2.599 s,
while the match query took 1.223 s. `provider_http` is nested within these stages
and combines HTTP/network response reading and boundary validation; it does not
separate network latency from model inference. Stage timing excludes the final
API evidence/revision revalidation and cleanup after result creation. Therefore
stage durations must not be summed or treated as complete end-to-end latency.
Only fixed stage/role/status fields and bounded finite timing numbers are retained
in the evaluator and curated Foundry export.

A separate live wording regression,
`var/footie-explanation-live-regression.json`, passed **3/3** (`final_06`,
`final_08`, `final_16`) with **seven provider calls**, **5,594 reported tokens**,
no unreported usage and no partial or narrative fallback. Its source hashes match
the candidate latency run, and no sources changed during either run. Independent
review checked the **selected narrative as well as the complete response**:

- The possession-start question explicitly says the record does not establish
  when control was won and that the observed suffix is not a full possession;
  this required statement survives narrative selection.
- The short sequence now says Eli Marsh carried the ball and scored, rather than
  leading with zero completed passes. The raw observed carry/shot supports it.
- Leon Finch's summary includes one save and three team goals conceded while on
  the pitch, without treating those goals as personal errors. The selected
  narrative retains this required goalkeeper context alongside a passing-rate
  comparison. Raw event inspection confirms save `e01004` and opposing goals
  `e00025`, `e01019`, `e01178` by the selected availability cutoff.

These are targeted **regressions** on previously seen questions. The first fresh
wording score remains **28/30 (93.3%)**; the earlier complete regression remains
**40/40** on its recorded source. The eight-second supported-request p95 gate
remains open, and this increment does not establish fresh accuracy or human
usability. The independent audit used read-only checks, no heavy test run and no
paid calls during the live comparison.

#### Exact commands for the paired diagnostic and wording check

```sh
PYTHONPATH=/private/tmp/footie-latency-baseline-20261023/backend .venv/bin/python scripts/evaluate_footie_intelligence.py --azure --warm-app --corpus fixtures/assistant/intelligence_final_holdout.json --label regression --case final_12 --case final_19 --case final_27 --max-attempts 8 --output var/footie-latency-before-reuse.json
.venv/bin/python scripts/evaluate_footie_intelligence.py --azure --warm-app --corpus fixtures/assistant/intelligence_final_holdout.json --label regression --case final_12 --case final_19 --case final_27 --max-attempts 8 --output var/footie-latency-after-reuse.json
.venv/bin/python scripts/evaluate_footie_intelligence.py --azure --warm-app --corpus fixtures/assistant/intelligence_final_holdout.json --label regression --case final_06 --case final_08 --case final_16 --max-attempts 7 --output var/footie-explanation-live-regression.json
```

The respective command summaries were `passed`, supported `3/3`, with `8`, `8`
and `7` model attempts. Total reported tokens were 9,422, 9,490 and 5,594.
The ledger read **600 requests in the rolling 24-hour window** after these 23
calls. No ledger reset, production-limit change, new budget increase or additional
paid evaluation followed. Future paid runs need sufficient naturally expired
reservations inside the approved ceiling; this is not a midnight-reset allowance.

The reviewed backend lock is now `footie-intelligence-controls-v2-latency`; the
previous lock was retained in `var/editorial-controls-before-latency.json`. Only
`multiagent.py`, `research.py`, `service.py` and `narrative.py` changed against that
previous backend source lock. Earlier evaluation artifacts remain unmodified.

#### Browser and export checks

Restarted the owned port-8027 lookup-only preview and tested the completed-match
Leon Finch question from the interface. The visible answer includes one save,
three team goals conceded, 39 attempted/35 completed passes and the historical
passing comparison. These full-match counts differ correctly from the earlier
72-minute live evaluation cutoff. The desktop view keeps two comparison cards;
390px mobile stacks them, with document and viewport both 390px wide and no
horizontal overflow. Browser console error list was empty; the viewport override
was reset. Screenshot proofs: `var/footie-keeper-improved-desktop.jpg` and
`var/footie-keeper-improved-mobile.jpg`. No frontend source changes or browser
model calls were needed for this increment.

Both candidate reports exported locally through `export_intelligence_foundry.py`
into `var/foundry-latency-after-reuse` and `var/foundry-explanation-regression`:
three scored/exported rows each, zero excluded rows, zero network/model calls.
No Foundry upload, cloud configuration change, push or deployment occurred.

#### Final combined regression pass

```sh
.venv/bin/python -m pytest -q tests/test_assistant*.py tests/test_intelligence*.py tests/test_fan_intelligence.py tests/test_model_identity.py tests/test_foundry_intelligence_export.py tests/test_editorial_evaluation.py tests/test_editorial_live_checks.py tests/test_multiagent_benchmark.py
```

```text
511 passed, 1 warning in 236.06s (0:03:56)
```

Log: `var/footie-latency-final-tests-rerun.log`. This is the relevant combined
regression set, not a rerun of the entire repository's 1,246-test suite.
Before this final pass, the same combined set reported two failures and 509
passes. One existing test compared complete English/Chinese fact objects including
the display label. It now verifies that English preference changes preserve every
field, Chinese changes only the translated label, and values, units, scope,
coverage and evidence remain identical. Its full module passed 36 tests afterward.
The second failure was the legacy mock editorial matrix observing 30 instead of
33 provider dispatches. It passed unchanged in isolation (1 passed in 7.79s) and
in this final combined pass. Added fixed case/status/reason diagnostics to that
assertion without relaxing it. A deterministic production fault was not established;
the initial intermittent failure remains recorded rather than discarded.

Additional focused passes: 131 transport/research/admission/identity tests;
139 intelligence/explanation/narrative/multiagent tests; independent evaluator and
exporter checks, including observer isolation and metadata filtering. Those sets
overlap and must not be added together as distinct tests. The sole warning is the
existing experimental evaluator API notice. Final `git diff --check` passed.

### Expanded warm-app check and completeness repair — 24 October 2026

After earlier reservations naturally expired, the ledger allowed 39 more calls.
Preselected twelve supported regressions spanning buildup, player performance,
both languages, window comparisons and two compound questions:

```sh
.venv/bin/python scripts/evaluate_footie_intelligence.py --azure --warm-app --corpus fixtures/assistant/intelligence_final_holdout.json --label regression --case final_01 --case final_04 --case final_06 --case final_09 --case final_12 --case final_15 --case final_16 --case final_17 --case final_20 --case final_21 --case final_29 --case final_30 --max-attempts 39 --output var/footie-intelligence-warm-expanded.json
```

Recorded result: **10/12**, 20 provider attempts, 17,274 reported tokens and one
attempt with unreported usage. No source changed during the run. Preserve this
failure result: the last two compound questions hit the isolated API's default
20-call hourly limiter before dispatching to Azure. Their fallback direct lookups
omitted the requested historical clause. This was a harness allowance defect and
a user-visible fallback completeness issue, not evidence of failed model routing.

The recorded all-case p50/p95 were 4.155/11.631 seconds; those include two very
fast failed requests and are not a successful-answer latency claim. The slow
`final_06` answer took 11.631 seconds, including a 9.204-second provider HTTP/query
stage, 0.163-second local tool, 0.855-second optional follow-up and 1.112-second
synthesis. Provider and parent-stage timings overlap. `final_04` retained a valid
localized answer after its optional follow-up was cancelled at two seconds; its
unreported usage is excluded from the reported token total. The eight-second
latency gate remains unmet.

Independent review found no numerical or bilingual error in the ten completed
answers. Unknown possession origin remained explicit in the selected narrative.
The two fallback answers did not disclose the omitted clause clearly enough.
The API now keeps useful direct facts but displays a localized incomplete-analysis
notice, clears selected narrative blocks so that notice is visible, and clears
the conversational plan so a follow-up cannot inherit only the answered clause.
Missing-context clarifications retain their normal context question.

The isolated evaluation app now admits the invocation allowance (1–80), set only
during app construction and restored immediately in the environment. Its limiter
is shared across warm requests. The persistent evaluation ledger still enforces
240/hour and the approved 600/rolling-day limit; production settings are unchanged.
Reports and curated exports record these separate limits. Offline tests verify
21 successful reservations followed by a denial in the same app, environment
restoration, invalid caps and observer isolation.

A narrow workflow optimization also removes synthesis when exactly one approved
story bundle exists. The same required-claim and specialist-coverage validation
still runs, and the API performs its final evidence reread. Multiple candidates
retain model selection. A typed `selection_mode` persists calculated versus
model-selected wording through the cache, including compatibility with old
receipts. This does not skip query planning or weaken deadlines.

Reviewed backend lock: `footie-intelligence-controls-v3-summary-selection`.
Only `assistant/api.py`, `admission.py`, `multiagent.py` and `research.py` changed
against v2; its prior lock is retained locally. No hosted configuration changed.
The twelve-case report exported to `var/foundry-warm-expanded`: all twelve rows,
including both failures, zero exclusions, zero network/model calls.

#### Bounded live recovery check

Preselected the slow origin question, the single-club comparison with one valid
summary, and both previously blocked compound questions before this next run:

```sh
.venv/bin/python scripts/evaluate_footie_intelligence.py --azure --warm-app --corpus fixtures/assistant/intelligence_final_holdout.json --label regression --case final_06 --case final_20 --case final_29 --case final_30 --max-attempts 16 --output var/footie-intelligence-warm-recovery.json
```

```text
PASS final_06
PASS final_20
PASS final_29
PASS final_30
status: passed; supported: 4/4; model_attempts: 12; total_tokens: 15441
```

| Case | Request wall time | Calls | Result |
| --- | ---: | ---: | --- |
| Unknown possession origin | 6.124 s | 3 | Required unknown-start statement retained. |
| Southbank completed-window comparison | 2.990 s | 1 | Sole validated summary used directly; calculated label, no synthesis. |
| Game changes plus pre-match career goals | 5.936 s | 4 | Match comparison and 73 pre-match career goals both returned. |
| Player performance plus prior-season goals | 7.073 s | 4 | Current performance and 14 goals in 2025–26 both returned. |

No partial failures, unreported usage, source changes or narrative fallbacks in
this run. The sample p50/p95 were 5.936/7.073 seconds. These four known regressions
do **not** establish a full-suite p95, a fresh accuracy score or a causal transport
speedup. Do not splice them into the previous twelve-case result and relabel it
a single passing run. Both specialist query stages overlap on compound requests;
route time is about 1.9–2.0 seconds in this sample. The earlier 9.204-second provider
tail remains part of the reliability evidence.

The recovery report exported locally to `var/foundry-warm-recovery`: four scored
and exported rows, zero exclusions and zero network/model calls. No evaluation
was uploaded to Foundry. The two live runs in this increment used 32 attempts
and 32,715 reported tokens, plus the one cancelled call's unknown token usage.

#### Final checks for this increment

```sh
.venv/bin/python -m pytest -q tests/test_assistant*.py tests/test_intelligence*.py tests/test_fan_intelligence.py tests/test_model_identity.py tests/test_foundry_intelligence_export.py tests/test_editorial_evaluation.py tests/test_editorial_live_checks.py tests/test_multiagent_benchmark.py
```

```text
526 passed, 1 warning in 139.20s (0:02:19)
```

Log: `var/footie-summary-selection-final-tests.log`. The warning is the existing
experimental evaluator notice. The focused frontend command, run from `frontend`,
was `npm test -- src/assistant/Footie.test.tsx`: **14 tests passed**. It verifies
that incomplete-analysis text stays visible, outside collapsed evidence. There
were no frontend implementation changes in this increment. Additional focused
123-test transport/research/admission and 68-test harness/export runs overlap with
the combined set and are not additional distinct coverage. `git diff --check`
passed. The owned lookup-only port-8027 preview was restarted with current code;
Azure inference was exercised separately by the bounded evaluator.

The final read-only ledger check showed 555/600 attempts in the rolling day after
more historical reservations naturally expired. This is a moving count, not a
reset or new allowance. No source report was overwritten, and no cloud settings,
production limits, live traffic, Foundry upload, push or deployment changed. The
next release gate remains broader warm-app latency/reliability verification with
enough available allowance; four successful retries cannot establish its p95.

### First twenty-case warm regression and rollout audit — 24 October 2026

With 45 evaluation calls available, fixed the next run to `final_01` through
`final_20`, in corpus order, before looking at results. The remainder of the
forty-case corpus was not run or replaced with earlier targeted samples.

```sh
.venv/bin/python scripts/evaluate_footie_intelligence.py --azure --warm-app --corpus fixtures/assistant/intelligence_final_holdout.json --label regression --case final_01 --case final_02 --case final_03 --case final_04 --case final_05 --case final_06 --case final_07 --case final_08 --case final_09 --case final_10 --case final_11 --case final_12 --case final_13 --case final_14 --case final_15 --case final_16 --case final_17 --case final_18 --case final_19 --case final_20 --max-attempts 45 --output var/footie-intelligence-warm-release-a.json
```

Result: **20/20 supported regressions passed**, **39 provider calls**,
**36,177 reported tokens**, zero unreported usage, partial answers or narrative
fallbacks. Sources and the frozen corpus were unchanged during the run. First-half
request latency: **p50 4.223 s, p95 6.279 s, maximum 6.385 s**. This measures local
TestClient API processing with live Azure inference, not deployed ingress,
browser or mobile-network latency. It is known-case regression evidence, not
fresh accuracy. The isolated API allowance was 45 for this invocation; it did not
change the production hourly allowance.

Independent review checked selected narratives, fact scopes and relevant replay
evidence. Unknown possession origins and goalkeeper context were retained,
carry-led finishes remained clear, and Chinese calculated narration was labeled
accurately. Cases 19 and 20 each used one provider query and no synthesis call.
The full forty-case gate remains incomplete: this half does not cover the compound,
career-history and invalid-scope cases in the remainder. The earlier slow provider
response is not erased by this faster sample.

The report exported locally into `var/foundry-warm-release-a`: twenty scored and
exported rows, zero excluded rows, no network/model calls. No Foundry upload.

#### Shared-store rollback compatibility

A separate source audit found a deployment blocker before any cloud write: the
new `Plan.analysis`, `Plan.investigate_player_id` and `Receipt.selection_mode`
fields would make the old revision's strict decoder reject the entire shared
admission document. This happens before expired-job pruning, so simply waiting
for the short-lived receipt to expire would not repair rollback. The affected
fields had only been exercised locally; no hosted state migration was performed.

The fix preserves the shared version-one quota ledger. Successful answers whose
plans use new analysis semantics, or whose summary is calculated, are not cached
in that legacy document. Only that completed job is removed; all charged weighted
reservations and other pending leases remain. Repeated questions can run again
only within the existing hourly/daily limits. Genuine failed jobs retain their
existing cooldown. Legacy-compatible, model-selected receipts still cache, with
the new null/default fields omitted from their persisted wire representation.
The serializer refuses to strip non-null analysis semantics into an old query.

This deliberately trades repeat-answer caching for rolling-deployment and rollback
compatibility. Richer cache records would need a separately versioned cache store
while retaining the common admission ledger. The earlier local v3 cache-metadata
test is superseded by explicit compatibility tests; calculated responses remain
honestly labeled, but are now recomputed rather than shared-cache hits.

Also corrected a monitoring error: an intentional calculated answer was counted
as `footie.fallback=true`. The trace flag now reflects an actual lookup fallback
or narrative failure reason. Offline tracing tests distinguish successful unique
summaries, ordinary direct lookups and failed research without contacting Azure.

Verification of this post-run compatibility increment:

```sh
.venv/bin/python -m pytest -q tests/test_assistant_admission_compat.py tests/test_assistant_admission.py tests/test_assistant_transport.py
# 56 passed in 20.19s
.venv/bin/python -m pytest -q tests/test_assistant_fallback.py tests/test_agent_observability.py
# 23 passed in 8.68s
PYTHONPATH=backend .venv/bin/python var/footie-admission-legacy-roundtrip.py > var/footie-admission-legacy-roundtrip.txt
```

The compatibility suite checks actual persisted SQLite and Cosmos-double payloads
using independently frozen old wire types, nested plans, repeated requests, usage
retention, sibling leases, failed-job cooldowns, wrong/expired/replaced owners and
Cosmos ETag conflicts. An additional independent audit verifies six extracted
legacy source files byte-for-byte against `git show 7ce9b8`, then uses that actual
old reader **and writer** between current SQLite operations. All eighteen charged
slots survive; the old runtime denies another four-slot reservation at a limit of
twenty. No application quota database or cloud resource was used for this audit.

The first monitoring-test attempt reported one failure because its tracer stub
accepted only one argument, while the actual framework also supplies tracer
metadata. Correcting the test double's signature exposed the intended successful
workflow; the final tests assert both response mode and exported fallback flag.
No production tracing configuration was changed.

This is preventive writer compatibility, not a migration for an incompatible
receipt already persisted. Such state still fails closed; recovery must preserve
charged usage rather than delete the shared control document. The new fields
have not been deployed by this work.

Reviewed lock: `footie-intelligence-controls-v4-rollback-compatibility`; only
`assistant/admission.py` and `assistant/api.py` differ from v3. The twenty-case
report retains its pre-fix hashes, and must not be presented as a full evaluation
of the final build. Query prompts, model transport, analysis tools and candidate
selection were unchanged by these two fixes. No additional live calls were made.
Final read-only evaluation ledger: **594/600**, with six slots remaining and no
reset. `git diff --check` and source-lock validation passed. No push, deployment,
Foundry upload or hosted ingestion/identity activation occurred.

### 24 October 2026 — complete v4 warm release regression

After earlier reservations expired naturally, the evaluation ledger had 431/600
charged calls. Ran the complete forty-question corpus in one process on the v4
compatibility build, without source changes or concurrent application test load:

```sh
.venv/bin/python scripts/evaluate_footie_intelligence.py --azure --warm-app \
  --corpus fixtures/assistant/intelligence_final_holdout.json \
  --label regression --max-attempts 80 \
  --output var/footie-intelligence-warm-release-full.json
```

Final output:

```json
{
  "status": "passed",
  "buckets": {
    "supported": {"passed": 30, "total": 30},
    "clarify": {"passed": 5, "total": 5},
    "unsupported": {"passed": 5, "total": 5}
  },
  "model_attempts": 69,
  "tokens": {
    "prompt_tokens": 85456,
    "completion_tokens": 2637,
    "total_tokens": 88093
  }
}
```

Independent audit recomputed **supported p50 3.408s, p95 5.167s, maximum 5.497s**.
All four compound requests passed. All 38 source fingerprints match the final
files and remained unchanged during the run; the corpus hash remains
`e5705b131e5dc2816c4811be03cdb9b487aac44f9efb8201c25c7756efaaee93`.
No unreported provider usage, supported-answer partial failure or fallback.
The missing-favorite-player case `final_32` used a safe clarification fallback;
five unsupported requests made zero model calls. A scored clarification is not
presented as successful model completion.

Selected prose/evidence review found no invented figures, wrong attribution,
future-history leakage or stale replay links. Unknown possession origins stayed
unknown; goalkeeper team-conceded facts avoided individual blame; equal completed
windows retained their boundaries. Two compound summaries could expose secondary
context earlier, although those details remain in the expanded context/evidence.

This meets the eight-second local engineering latency target. Measurements are
sequential warm local API requests with live Azure inference, including the first
request; they are not hosted ingress, browser, concurrency or human-usability
measurements. **The independent fresh-wording result remains 28/30 (93.3%).** This
40/40 result is regression evidence. Earlier failures and slower runs are retained.

```sh
.venv/bin/python scripts/export_intelligence_foundry.py \
  --report var/footie-intelligence-warm-release-full.json \
  --corpus fixtures/assistant/intelligence_final_holdout.json \
  --output-dir var/foundry-warm-release-full
# {"scored_rows":40,"exported_rows":40,"excluded_rows":0,"network_calls":0,"model_calls":0}
```

The export is local only. Production model limits remain 120/hour and 400/day;
the evaluation ledger remains 240/hour and 600/rolling-day without reset.

Read-only Azure readiness audit: current app is healthy in Single revision mode,
so the normal deployment workflow would immediately change public traffic. A
separate staged path must pin production and disable the candidate's Event Hubs
consumer and scaler: zero HTTP weight alone does not isolate background ingestion.
No model inference role is currently assigned to the attached managed identities;
authentication activation is a later, separately verified step.

Azure's delayed budget report showed **US$4.728 actual / US$37.904 forecast** against
the US$125 total cap. This is not real-time spend or remaining credit. The trial
credit expires **13 November 2026 at 14:09:17 Singapore time**, earlier than the
budget's 14 November UTC end. Use the credit expiry for cleanup planning. The
credit API's US$200 closed balance is a last-invoice balance, not unspent credit.

#### Release checks after the full model run

```sh
.venv/bin/python -m pytest -q > var/footie-intelligence-release-backend.log 2>&1
# 1315 passed, 1 warning in 368.69s (0:06:08)
cd frontend
npm test
# Test Files 35 passed (35); Tests 209 passed (209)
npm run build
# TypeScript passed; Vite production build completed
cd ..
node --test integrations/personalization/client.test.mjs
# tests 14; pass 14; fail 0
frontend/node_modules/.bin/tsc --noEmit --strict --target ES2022 --module ESNext --moduleResolution Bundler --lib ES2022,DOM --skipLibCheck integrations/personalization/client.ts
# exit 0
.venv/bin/python scripts/verify_personalization.py
# status passed: 844 matches, 1,176,374 events, 44 featured profiles;
# 285 position checks, 3,000 independent simulation matches, no validation warnings
.venv/bin/python -m pytest -q tests/test_staging_guard.py tests/test_deployment_guard.py
# 38 passed in 0.09s
```

The sole backend warning is the existing experimental Azure evaluation API
warning. The new staging tests were added after the full suite collected its
files, so their focused run is reported separately. The deployment identity Bicep
compiled; its existing app-scoped role gains only revision read/deactivate actions,
with no data-plane or role-assignment permissions. No Azure permission was changed
by local compilation. Independent staging review covered interrupted provisioning,
traffic pins, candidate ingestion isolation and restoration before Single mode.

The local Docker daemon is unavailable, so container smoke and the Linux build
must pass in GitHub CI before any staged release. A private-value comparison found
neither the configured model key nor its endpoint in the release files; values
were never printed. `var/`, `.env`, `reports/` and `research_notes/` are excluded
from this release. See [staging](../staging.md) for the reviewed activation path.

#### First hosted candidate — 24 October 2026

Exact main commit `0d7313a4c8e5b3195ec5914a1243acceb79a1670` passed CI
[40069777802](https://github.com/Haydnlee31/CounterPress/actions/runs/40069777802):
**1,359 backend tests**, **209 frontend tests**, production build, restricted
container smoke, Azure template compilation and career audit with no warnings.

Staging [40070457872](https://github.com/Haydnlee31/CounterPress/actions/runs/40070457872)
created `counterpress--stage-40070457872-1`. Independent control-plane review
confirmed the old production revision at 100%, the candidate's review label at
0%, both revisions healthy, exact approved template differences and preserved
identities, model configuration and allowances. Candidate ingestion was disabled.

The hosted container smoke passed health/readiness/assets, protected Studio,
44 career profiles, four featured matches, nine highlights, causal milestones,
22-player focus, audience fact parity, preference isolation and private-path 404s.
It made no inference calls.

The bounded hosted regression passed **4/4** authored cases without retry:

| Case | Hosted response | Trace-confirmed provider calls |
| --- | ---: | ---: |
| Unsupported tracking-speed question | 2.573s | 0 |
| Goal buildup | 4.886s | 3 |
| Completed comparison windows | 2.896s | 1 |
| Match and career compound question | 4.820s | 4 |

Independent response review confirmed numbers, attribution, source availability,
pre-kickoff career history and valid actions. The 12 conservative evaluation
reservations remain charged; they are not the actual provider-call count.
Request-ID-correlated Azure monitoring showed four roots and 19 connected spans,
eight provider calls, **9,237 input / 273 output tokens**, successful final
validation, no supported-answer fallback or partial result, and no cache hits.
The compound request connected the orchestrator and both specialists. Token
totals count provider stages only; root token totals are intentionally omitted.
Trace metadata excludes source-event details, which the response audit checks.
Artifacts: `var/footie-hosted-candidate-release.json` and
`var/footie-hosted-candidate-traces.json` (private/local, not committed).

These are targeted hosted observations, not a load test, p95 estimate or fresh
accuracy result. The original 28/30 fresh-wording result remains unchanged.
Desktop browser review confirmed the assistant loaded and its suggestion cards
remained reachable beneath the fixed composer. No additional UI inference call
was made.

Cleanup [40071017273](https://github.com/Haydnlee31/CounterPress/actions/runs/40071017273)
removed the review label, then failed before creating the restoration revision.
Azure Activity Log identified `ContainerAppOperationInProgress` (HTTP Conflict).
Independent inspection confirmed production still healthy and explicitly pinned
at 100%, with no restoration revision or production promotion. The app remained
in Multiple mode; switching directly to Single would have been unsafe. Recovery
and the production release are recorded below only after verification.

Local recovery using the independently reviewed conflict-handling fix succeeded:
`PASS: original production image/settings restored; candidate inactive; Single
mode restored`. The restoration revision is
`counterpress--restore-40070457872-1`. Recovery skipped the already-removed label,
created the original production image/settings, waited for exact-revision health,
then deactivated the candidate and verified Single mode. It neither reset nor
refunded shared admission state. Focused checks: **78 passed in 0.10s**.

The fix retries only the exact ARM `ContainerAppOperationInProgress` HTTP Conflict,
up to six attempts, with configuration/identity/template/routing drift checks
before each resend. Other errors and timeouts stop with sanitized messages.
The 180-second retry deadline bounds resend eligibility, not the total wall time
of separate metadata reads. Normal production workflow
[40071500453](https://github.com/Haydnlee31/CounterPress/actions/runs/40071500453)
was dispatched for the already-tested application commit; its final outcome is
authoritative in that workflow, not implied by successful candidate validation.
