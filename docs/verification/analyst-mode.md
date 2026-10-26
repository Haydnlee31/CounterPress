# Analyst Mode verification

## Candidate-based release validation

The final reviewed architecture uses exact, evidence-bound candidate selection.
The native director is v8, four specialist agents are v4, and the editor is v5;
all six endpoints have explicit version selectors. See the
[native smoke receipt](analyst-native-candidate-smoke-20261026.json) and
[reviewed benchmark](analyst-native-benchmark-native-acceptance-20261026-v8-reviewed.json).

```sh
.venv/bin/python -m pytest tests/test_analyst*.py tests/test_editorial_evaluation.py -q
```

Recorded result: **158 passed, 1 skipped** (the optional SDK environment). The
isolated native SDK environment separately passed **42 tests**. The semantic
suite includes twelve independently written counterexamples; the bilingual and
audience-depth compatibility matrix covers 24 combinations.

The complete frontend run, `cd frontend && npm test`, passed **265 tests across
39 files**; the production build passed. Isolated browser checks at 1440, 760,
390 and 360 pixels found no overflow or JavaScript errors. Checks covered player
focus, recent windows, missing map coverage, single match-wide values, unknown
pass outcomes, source-clock playback and backward seeking. Evidence-only facts
are excluded from the statistics controls, and partial citation lists say how
many supporting plays are currently shown.

The live benchmark returned seven complete supported analyses and one appropriate
quiet-window abstention, using **17 reported model calls**. Six cases are now
regressions; two fresh cases were selected before their responses and align with
the application's source-minute schedule. Two modified-claim attacks were
rejected by the deterministic publication boundary. The assistant's source-based
qualitative score was **41/48**, not a human usability result or statistical
accuracy estimate. Some consequences and counterpoints remain generic, and only
the documented candidate families are supported.

Both the actual production provider and Container App managed identity passed
native invocation and session cleanup. The application now skips allowance
reservation and hosted startup when no supported candidate exists. Existing
Footie behavior and production limits remain separate.

## Earlier implementation checks

Local verification on 26 October 2026. Native cloud execution and release status
are recorded separately; local tests do not establish live Foundry readiness.

## Application and evidence

The first full backend run completed **1,790 passed, one optional native-SDK test
skipped**, with three evaluation-lock failures while implementation was changing.
After review and updating the source lock to
`footie-intelligence-controls-v12-native-analyst-mode`, the focused evaluation,
Analyst, transport, admission and integration run passed **115 tests**, with the
same optional SDK skip. The native SDK is tested in its own isolated environment
and in the new CI job, avoiding dependency conflicts with the FastAPI app.

```sh
.venv/bin/pytest -q
.venv/bin/pytest -q tests/test_editorial_evaluation.py tests/test_analyst_admission.py \
  tests/test_analyst_api.py tests/test_analyst_provider.py tests/test_analyst_metrics.py \
  tests/test_analyst_integration.py tests/test_analyst_deployment.py \
  tests/test_analyst_foundry_runtime.py
```

The evidence audit exercised **62 snapshots** across the three supported matches
and both halves. Every dispatch packet passed the native input contract; the
largest contained **23,979 characters**, below the 24,000 limit. Checks include
paired-window arithmetic, revisions/retractions, occurrence and availability
cutoffs, unknown outcomes, delivery-ceiling equivalence, geometry, player focus,
and compound signals crossing specialist boundaries.

The independent review found and fixed:

- Different ineffective delivery ceilings producing duplicate paid cache keys.
- Compound transition insights losing their shot evidence during role filtering.
- Individual-player evidence being omitted from the default player specialist.
- Completed native results requiring a second revision check before publication.
- The editor selecting prose without an independent semantic verification pass.

The first live benchmark disproved the sufficiency of that model-based verifier:
it accepted both deliberately false readings. Those results and the source-based
review remain in [the native benchmark record](analyst-native-benchmark.md).
The replacement publication boundary permits only exact readings from the
snapshot's server-built, localized candidate catalog. Native agents rank and
select those interpretations; neither specialist nor editor may rewrite facts.
Transport also checks the actual returned agent version, independently of the
version requested in the body. Candidate rules still require source-based review
and new held-out checks; citation membership alone is not semantic accuracy.

## Interface

```sh
cd frontend
npm test
npm run build
```

**255 frontend tests passed** across 39 files; the final targeted interface pass
passed **16 tests**, and the production build passed. Tests cover source-clock
buckets, forward-progress coalescing, rewind and revision invalidation, malformed
payloads, pending results, pause/hidden-page behavior and allowance responses.

Isolated Chrome checks passed at **1440, 760, 390 and 360 pixels**: no horizontal
overflow or page errors, aligned three-column statistics, player rankings,
source-time updates, no paused polling, and rewind. Screenshots are private local
artifacts under `var/analyst-*.png`. A CSS specificity conflict that collapsed
metric columns was identified visually and fixed. The lead insight card no
longer stretches into an empty full-height panel.

```sh
.venv/bin/python scripts/container_smoke.py http://127.0.0.1:8018
```

Result: application health/readiness, assets, access boundaries, evidence,
highlights, GI attribution, career profiles, personalization, causal milestones,
preference isolation, private-path 404s, and the new no-model Analyst snapshot
check passed.

## Release controls

New deployment settings preserve existing Footie and its secrets. Activation
requires Cosmos admission and a private, verified pinned native manifest;
HTTP/untrusted endpoints and unverified versions are rejected. Native invocation
uses only HTTPS, dedicated agent endpoints, fresh sessions and bounded cleanup.
The source lock now includes native runtime Python and pinned requirements.
