# Analyst Mode verification

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

The final verifier is model-based. Contract tests prove rejection and failure
handling, not perfect semantic accuracy; live held-out and adversarial checks are
required before activation.

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
