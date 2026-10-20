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

## Local career realism and portrait follow-up — 19 October 2026

The local dashboard now includes the personalization UI and four fictional player portrait previews. Assist coverage is complete for all 44 featured players after preserving four explicit provider assist credits. Counts with other incomplete coverage remain visible with coverage details; unknown zeros remain null, and assist rates use matching covered counts/minutes.

Changed implementation areas: `backend/counterpress/personalization/{contracts,imports,metrics,coverage,service,calibration,registry,simulation,realism,build}.py`, `backend/counterpress/fan/{presentation,service}.py`, regenerated `fixtures/personalization/`, `frontend/src/football/visuals.tsx`, `data.ts`, `football.css` and `FootballHub.test.tsx`, four JPEG assets in `frontend/src/football/portraits/`, and `frontend/src/vite-env.d.ts`. The accounting tests, smoke script, full-ledger verifier and documentation were updated. Shared navigation and the remainder of the local UI were already pending from the preceding implementation.

Exact commands and final output summaries:

```text
$ .venv/bin/pytest -q
677 passed, 1 warning in 43.74s

$ .venv/bin/pytest -q tests/test_personalization_coverage.py tests/test_fan_personalization.py tests/test_editorial_evaluation.py
52 passed, 1 warning in 11.19s

$ npm --prefix frontend test
Test Files  24 passed (24)
Tests       154 passed (154)

$ npm --prefix frontend run build
✓ 250 modules transformed.
✓ built in 1.07s

$ .venv/bin/python scripts/verify_personalization.py --output docs/verification/personalization-data.json
status: passed
matches: 844
events: 1143062
goals: 2336
featured_profiles: 44
featured_matches: 4
highlights: 3
population_checks: 10 historical + 10 independent-validation checks passed
elapsed_seconds: 52.22

$ .venv/bin/python scripts/container_smoke.py http://127.0.0.1:8017
PASS: health, readiness, frontend/assets, Studio access, evidence/recaps, replay goals, GI attribution, 44 career profiles, four featured matches, nine personalized highlights, causal milestone, 22-player focus, audience fact parity, preference isolation, private-path 404s
```

The targeted backend rerun follows the final covered-rate and singular/plural wording adjustments. The existing Agent Framework experimental evaluator warning remains. Full-ledger verification output is also saved as JSON, including exact checks. No paid model inference, new Azure services, Git push or deployment occurred.

The offline/mocked editorial controls lock hashes all backend Python sources, including the career code. Changed files were reviewed and the controls lock versioned to `career-realism-v2`. The original paid pilot lock, prompts and case expectations were not altered; the new hash does not imply a repeated paid pilot or human review.

Chrome verification: all four portraits load in the directory; Rory Ellis's profile displays 143 matches, 86 goals and 10 assists; the 390×844 layout has no horizontal overflow; the new Nico Alder highlight autoplays with 22 visible players, finishes 1–0 with his 30-goal milestone, and keyboard seeking back to the start returns to 0–0 and removes future insight cards. The original desktop viewport was restored. Portrait image-load failure falls back to the existing jersey artwork and has a regression test.

Population evaluation uses 304 real fitting matches, 76 untouched real holdouts, 96 fitting simulation seeds, 240 independent mixed-club validation simulations, and a distinct 100-candidate showcase pool. Historical averages: 2.76 goals, 23.58 shots, 52.5% forward goal share, 12.3% defender goal share and 62.7% assisted goals. Definitions, tolerances and limitations are in `docs/personalization-data.md` and the dataset manifest. Career statistics are event reductions; they were not independently edited to hit targets.

Four preview assets were generated using the built-in image generation tool, then encoded as JPEG without changing their composition. Exact per-player prompts and repository asset paths are saved in `docs/player-portrait-prompts.json`. All other featured players retain their original jersey illustration pending style review.
