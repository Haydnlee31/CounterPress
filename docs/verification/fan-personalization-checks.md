# Fan personalization verification — 19 October 2026

Local implementation verification; no paid inference or new cloud resources.
The frontend source was not changed. The independent adapter is not yet imported
by the colleague's UI. The existing hosted app has not been redeployed.

## Backend

Exact command:

```sh
.venv/bin/pytest -q
```

Final output:

```text
671 passed, 1 warning in 41.84s
```

The warning is the existing Agent Framework experimental evaluator notice.
Twenty-six personalization cases cover registry validation, bounded preferences,
canonical preference identity, audience fact parity, completed-history cutoffs,
the goal-availability boundary, metric focus, substitutions, unknown coverage,
comparisons, simultaneous fan requests, retractions, historical baseline
corrections, stale authored highlights, HTTP contracts and oversized bodies.
`tests/expected_fan_personalization.json` is a separately authored accounting oracle.

## Browser adapter

Exact commands:

```sh
node --test integrations/personalization/client.test.mjs
frontend/node_modules/.bin/tsc --noEmit --strict --target ES2022 --module ESNext --moduleResolution Bundler --lib ES2022,DOM --skipLibCheck integrations/personalization/client.ts
```

Test output summary:

```text
ℹ tests 14
ℹ suites 0
ℹ pass 14
ℹ fail 0
ℹ cancelled 0
ℹ skipped 0
ℹ todo 0
```

TypeScript exits 0 with no output. Tests include migration without destructive
writes, persistent follow/unfollow, explicit reset, denied/corrupt storage,
identity bounds, neutral defaults, cookie-free requests, stale-response rejection,
seek/unmount cancellation, separate surfaces and sanitized server errors.

## Existing UI compatibility

Exact commands:

```sh
npm --prefix frontend test
npm --prefix frontend run build
```

Relevant output:

```text
Test Files  22 passed (22)
     Tests  143 passed (143)
vite v7.3.7 building client environment for production...
✓ 239 modules transformed.
✓ built in 984ms
```

This verifies the existing frontend still builds and passes its checks. It is not
a claim that the pending new UI was tested or that people have tested usability.

## Real HTTP integration

Server command (local test database and existing production frontend bundle):

```sh
COUNTERPRESS_DB_PATH=var/fan-personalization-http.sqlite3 COUNTERPRESS_STATIC_DIR=frontend/dist COUNTERPRESS_STREAMING=off .venv/bin/python -m uvicorn counterpress.api.main:app --host 127.0.0.1 --port 8017 --no-access-log
```

Verification command and exact output:

```sh
.venv/bin/python scripts/container_smoke.py http://127.0.0.1:8017
```

```text
PASS: health, readiness, frontend/assets, Studio access, evidence/recaps, replay goals, GI attribution, 44 career profiles, four featured matches, nine personalized highlights, causal milestone, 22-player focus, audience fact parity, preference isolation, private-path 404s
```

The same smoke assertions run against the restricted Docker image in CI. This
local command tested a real uvicorn HTTP server, not a locally built Docker image.

## Review boundaries

- Existing `/api/data/`, replay, voice and Studio routes retain their contracts.
- Generated career artifacts and their event digests are unchanged.
- Favorite storage is device-local; no account or cross-device synchronization.
- The new client rejects delayed views, but the UI must actually integrate it and
  clear cards when context changes. No presentation-layer integration is claimed.
- The general assistant, Azure career-ingestion bridge and model-authentication
  migration remain future work.
- The editorial source lock is versioned `fan-personalization-v1` to account for
  added backend modules. Previous paid evaluation results were not rerun or reused
  as evidence of the new assistant's quality.
