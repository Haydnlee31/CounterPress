# Data foundation verification

Final local checks on 19 October 2026; no paid model calls or cloud writes.

```text
$ .venv/bin/pytest -q
645 passed, 1 warning in 32.13s
```

The warning is the existing Agent Framework experimental evaluator warning.

```text
$ .venv/bin/python scripts/verify_personalization.py --output docs/verification/personalization-data.json
Validated 200 matches
Validated 400 matches
Validated 600 matches
Validated 800 matches
```

The complete JSON result is in [personalization-data.json](personalization-data.json):
844 matches, 1,050,765 events, 1,975 goals, all 44 featured profiles, four featured
fixtures and three native replay excerpts passed. The audit took 47.64 seconds.
The same audit is now required in GitHub Actions on Linux.

```text
$ .venv/bin/python scripts/container_smoke.py http://127.0.0.1:8016
PASS: health, readiness, frontend/assets, Studio callback/access boundary, evidence/recaps, replay goals, GI attribution, 44 career profiles, four featured matches, causal milestone, private-path 404s
```

This local HTTP check used Uvicorn and the built frontend. The GitHub Actions
container job runs the same assertions inside the restricted production image.
It checks the new milestone immediately before and at its availability time.

A separate build into ignored `var/personalization-reproduction/` reproduced all
core artifacts byte-for-byte. The final highlight metadata also includes the
outcome availability time, so its end covers ball arrival and processing. Source
files are needed only to refit the model or import archive lineup metadata;
running the app, tests and full audit needs no source downloads or credentials.

`git diff --check` passed. No `frontend/` files changed.
