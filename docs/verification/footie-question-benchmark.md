# Footie question benchmark — 21 October 2026

This implements the first finishing step from the renewed Microsoft Reactor comparison: evaluate interpretation separately from factual grounding. The assistant changes are local and unpublished. The career-index streaming bridge, assistant request tracing and managed-identity model authentication remain subsequent work.

## Protocol

The [58-question corpus](../../fixtures/assistant/questions.json) was authored before running the baseline. It spans 15 categories: player lookups, metric distinctions, goalkeepers, unavailable coverage, comparisons, recent form, seasons, follow-ups, clubs, preferences, language, ambiguity, unsupported requests, temporal boundaries and corrections. Ten live-sample IDs were selected in that original corpus, before model results were observed. Cases bind to the canonical ledger checksum and explicit fixture/event IDs; a different dataset requires reviewing the labels.

Each case contains an independently specified operation, subjects, metric, rate flag and season scope. The expected answer is calculated from that label through the existing deterministic readers, not through the router under evaluation. This tests semantic routing and agreement with the canonical readers, **not an independent numerical audit of those readers**. Existing accounting, distribution and revision tests remain necessary.

Scoring compares:

- Raw proposed intent, separately from the effective validated/fallback intent.
- Subject, metric, period, units, value, coverage and full evidence references.
- Chart content and relevant next actions, including replay availability.
- Narrative sentences against the exact evidence-bound candidate sentences.
- Explicit anchors: unavailable values remain null, a milestone appears only after its event becomes available, and retraction removes the milestone and stale replay action.

Comparison-player order is ignored; season, metric and subject association are not. Recent-form operations always calculate per-90, so that operation's unused rate flag is normalized. Unused comparison-season fields are ignored outside season comparisons. The one offline career-at-replay case proposes a career lookup but is rejected by the temporal guard: it counts as correct final behavior, not correct raw routing.

These are regression cases, not unseen fan traffic. Because the failures informed fixes, a perfect final result is not a population accuracy estimate. Narrative selection can be factually valid but unhelpful; relevance, tone and ease of use still need human review.

## Findings and changes

The initial offline run produced **44/58 correct final intents and answers**. The [baseline report](footie-benchmark-baseline.json) is retained. It predates the later chart-content scoring check; the intent comparison is unchanged.

Fixed distinct failure classes:

- Chance creation is shot assists/key passes, not goal assists. Expected assists is also distinct.
- Longer metric phrases take precedence over contained terms: save percentage, goals conceded and completed passes no longer get rejected as saves, goals or pass attempts.
- Two named seasons and “side by side” now route to the appropriate comparison.
- Metric follow-ups preserve the previous season; explicit career wording clears a selected season.
- First-name-only substring matching no longer substitutes a known player for an unknown full name. Full names remain supported next to Chinese text; unique surnames still work.
- “Better” no longer triggers the betting filter. Vague creativity/best-player questions and multiple separate metrics ask for clarification rather than silently choosing a figure.
- Server validation enforces explicit periods, per-90 requests, unsupported time queries and the default career scope, independently of the model's schema-valid output.

The initial [Azure sample](footie-benchmark-azure.json) produced **5/10 correct final answers**, and **3/9 correct model interpretations**; one unsupported tracking question intentionally made no model request. Five failures were valid statistics narrowed to the current season instead of the requested/default career view. A sixth incorrect model plan turned “And last season?” into a two-season comparison; the existing fallback returned the correct answer.

We fixed the prompt and, more importantly, enforce scope server-side. A regression test replays all nine captured model plans through the actual API with no network calls: they now return correct answers, rejecting mismatched plans and using the deterministic fallback. This is **recorded-response regression**, not fresh model evaluation.

Fresh targeted Azure checks after those fixes:

| Question | Result | Calls | Response time |
|---|---|---:|---:|
| How often has Mateo Cross found the net? | Correct career plan, facts and Azure-selected narrative | 2 | 4,957 ms |
| And last season? | Correct prior-player season lookup; calculated narrative under the one-call budget | 1 | 2,814 ms |

See the [career-scope result](footie-benchmark-azure-scope-check.json) and [follow-up result](footie-benchmark-azure-followup-check.json). The original ten-question Azure sample has **not** been rerun in full after the fixes. The initial sample's p50/p95 was 3,797/5,458 ms; that small sample is diagnostic, not an SLA.

## Budget and privacy

The three successful evaluation runs reserved **20 model attempts** total (17 + 2 + 1), reporting **36,694 input and 604 output tokens: 37,298 total**. All attempts returned usage. This is not a dollar-cost or Azure-account spending statement. No speech synthesis, new Azure resources, deployment, hosted write or production data mutation was performed.

The evaluator has a persistent SQLite attempt ledger at ignored `var/footie-evaluation-budget.sqlite3`, with a maximum 20 attempts per rolling hour. Reservation occurs before sending, and is transactional across processes and protected across threads. A failed request consumes its reservation. Restarting the command does not reset the ledger; do not delete it to bypass the limit. This evaluation ledger is separate from the running app's existing process-local budget and is not an account-wide quota.

An initial runner setup error returned HTTP 503 because its SQLite budget connection was created on a different thread. It made **zero** model attempts. The connection/thread handling was fixed and tested before the recorded live sample.

Reports retain case IDs, sanitized intents, aggregate usage, latency, failures and source checksums; they omit model endpoints, credentials, raw model prose and user conversation content. Cases contain only authored football questions. Output files cannot be overwritten accidentally. The runner now marks missing model coverage **incomplete** and exits 2, so an exhausted budget cannot masquerade as a successful Azure benchmark. Earlier reports retain their original format and results.

## Reproduce

Offline, no model calls:

```sh
.venv/bin/python scripts/evaluate_footie.py --output var/footie-offline-new.json
```

Final [offline result](footie-benchmark-final.json): **58/58** effective intents, canonical answers/visuals/actions, narrative bindings and temporal anchors passed; raw intent **57/58**, with the remaining case safely rejected by the playback-scope guard. Model attempts: **0**.

After the evaluation allowance renews, the full ten-question live sample is:

```sh
.venv/bin/python scripts/evaluate_footie.py --azure --output var/footie-azure-new.json
```

It uses the real question endpoint in an isolated local FastAPI app and the existing model configuration from ignored `.env`. It does not call the hosted application. Maximum 20 attempts, including planner and narrator. A targeted repeat can use `--case goals_paraphrase`; a planner-only budget check can add `--max-attempts 1`. Targeted results must not be described as full-sample validation.

```sh
.venv/bin/pytest -q tests/test_assistant_evaluation.py tests/test_assistant.py tests/test_assistant_narrative.py tests/test_assistant_moments.py
```

```text
138 passed in 31.69s
```

The suite includes every authored case, isolated retractions, deliberately corrupted subject/scope/value/evidence/chart/story/action outputs, captured Azure-plan regressions, explicit-scope enforcement, dataset mismatches and persistent concurrent budget checks.

The offline editorial source lock was versioned to `grounded-footie-question-benchmark-v1`. This records the changed assistant code; it does not rerun or relabel the separate paid editorial pilot.

## Next

Repeat the broader live sample when the bounded evaluation allowance renews, without discarding the initial failures. Then connect event ingestion to durable career revisions and prove one goal/correction journey across match state, profiles, personalization and Footie. Keep the interface unchanged during this integration. Request tracing and keyless model access follow; they were not implemented by this benchmark.

## Final checks

```sh
.venv/bin/pytest -q
```

```text
858 passed, 1 warning in 109.17s (0:01:49)
```

The warning is the existing experimental editorial evaluator notice. The full
backend run includes the new question regressions and existing model, temporal,
streaming, identity and data checks. No frontend files changed. `git diff --check`
and a private-value/credential-pattern scan of all 16 changed/new deliverables
passed. Unrelated `reports/` and `research_notes/` remain untouched.

An exhausted-budget runner check returned exit code 2, `evaluation_status:
incomplete`, zero model attempts, and the correct calculated answer. It proves
that fallback success does not qualify an unexecuted model evaluation as a pass.
