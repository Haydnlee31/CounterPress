# CounterPress

[![CI](https://github.com/Haydnlee31/CounterPress/actions/workflows/ci.yml/badge.svg)](https://github.com/Haydnlee31/CounterPress/actions/workflows/ci.yml)

Synthetic football insights through Stage 5: a React replay screen with inspectable evidence,
SQLite history, correction-driven updates and withdrawals, backed by FastAPI and
deterministic synthetic match calculations. Stage 6 includes the Azure wording
adapter and bounded Microsoft Agent Framework Analyst/Producer workflow, verified
offline and against the configured Azure deployment.
Stage 7 adds analyst/casual views, club and player preferences, a card display
budget, and English/Simplified Chinese presentation variants with revision-aware caching.
The first Stage 8 increment adds a seeded possession generator, independently
reviewed controls and whole-match development/holdout splits.
The second Stage 8 increment adds observed build-up episodes, duel-based pressure
exposure and pressured-escape comparisons with typed evidence and a local CLI.
The third increment persists those comparisons with independent lifecycle
revisions and displays bilingual pressure/escape cards with inspectable episodes.
The fourth adds sustained possession without progression, independent positive
and negative controls, durable corrections and bilingual episode evidence.

## Local setup

GitHub Actions runs backend tests and frontend tests/builds on pushes to `main`,
pull requests targeting `main`, and manual runs from the Actions tab. The workflow
uses Python from `.python-version`, uv 0.11.29, Node.js 24 and committed dependency
locks. Actions are pinned to commit hashes, repository permissions are read-only,
and no Azure credentials or live model requests are used. See
[the workflow](.github/workflows/ci.yml) and the official
[uv](https://docs.astral.sh/uv/guides/integration/github/) and
[Node.js setup](https://github.com/actions/setup-node) action documentation.

Prerequisites: Python 3.11+ and [uv](https://docs.astral.sh/uv/getting-started/installation/).
The project selects Python 3.13 through `.python-version`. Run from this directory:

```sh
UV_CACHE_DIR=.uv-cache uv sync --locked
uv run --frozen uvicorn counterpress.api.main:app --host 127.0.0.1 --port 8000 --reload
```

`uv sync` creates `.venv` and installs the application and test dependencies using
`uv.lock`. No credentials, environment file, separate database server or cloud
subscription is needed. SQLite history is created at `var/counterpress.sqlite3`;
set `COUNTERPRESS_DB_PATH` to choose a different file. Host and port are explicit Uvicorn options. Stop the server with Ctrl+C.

In another terminal:

```sh
curl -sS http://127.0.0.1:8000/health
```

Response:

```json
{"status":"ok","service":"counterpress"}
```

Interactive API docs: <http://127.0.0.1:8000/docs>.
OpenAPI: <http://127.0.0.1:8000/openapi.json>.
Health reports process liveness only.

## Open the interface

With the backend running, use another terminal:

```sh
cd frontend
npm ci --cache ../.npm-cache --no-audit --no-fund
npm run dev
```

Open <http://127.0.0.1:5173/>. Click **Go to comparison**, then **Show evidence**.
Play, pause, reset, speed and seek controls work across the 48:00–58:00 segment.
The control scenario shows no increase card. See the [interface guide](docs/interface.md)
for API contracts and verification details. The [history guide](docs/history.md)
explains persistence, correction ingestion and historical replay.

## Validate the foundation

```sh
uv run --frozen python -m counterpress.fixture fixtures/tiny_possession.json
uv run --frozen pytest -q
```

The first command loads only the fixture, validates its shape, identities, actors,
timing and possession transitions, and prints the event IDs. It never reads the
hand-written expected results in `tests/expected_tiny_possession.json`.
Tests independently check those expectations, event references, window boundaries,
and invalid inputs, as well as the health endpoint and documentation routes.

## Files and scope

- `backend/counterpress/domain/models.py`: football contracts, with no API/cloud dependencies.
- `backend/counterpress/api/main.py`: FastAPI application and typed health response.
- `backend/counterpress/api/snapshots.py`: historical snapshots and deterministic lifecycle publications.
- `backend/counterpress/history.py`: storage interface, SQLite journal and versioned evidence.
- `backend/counterpress/ingest.py`: local atomic revision ingestion CLI.
- `backend/counterpress/fixture.py`: initial-revision fixture validation and CLI.
- `backend/counterpress/domain/replay.py`: canonical revision selection, source journal and pure state reduction.
- `backend/counterpress/domain/metrics.py`: pass totals/distances and high-recovery comparisons.
- `backend/counterpress/clock.py`: virtual play, pause, reset and speed controls.
- `backend/counterpress/replay.py`: replay sessions, snapshots and console report.
- `backend/counterpress/generator/`: seeded conditional possession simulation and separate evaluator exports.
- `tests/test_generator.py` and `tests/expected_generator_controls.json`: continuity audits and independent controls.
- `backend/counterpress/domain/pressure.py` and `backend/counterpress/pressure.py`: observed episode evidence and analysis CLI.
- `backend/counterpress/pressure_publications.py` and `backend/counterpress/pressure_views.py`: durable pressure publication and bilingual presentation.
- `fixtures/pressure/`, `tests/test_pressure.py`, `tests/expected_pressure.json`: independent episode controls and regression checks.
- `backend/counterpress/domain/progression.py` and `backend/counterpress/progression.py`: sustained-possession evidence and CLI.
- `fixtures/progression/`, `tests/test_progression.py`, `tests/expected_progression.json`: independent progression controls, corrections and regression checks.
- `fixtures/tiny_possession.json`: fictional Eastbridge/Northport sequence.
- `fixtures/recovery_increase.json` and `fixtures/recovery_control.json`: 89-event,
  ten-minute scenarios with independently checked one-versus-four and one-versus-one counts.
- `fixtures/faults/`: invalid player/coordinate examples and duplicate/correction record arrays.
- `tests/expected_tiny_possession.json`: separately hand-checked oracle and example evidence packet.
- `tests/test_foundation.py`: foundation checks.
- `tests/test_snapshot_api.py`: API and evidence integrity checks.
- `tests/test_history.py`: durability, lifecycle, correction, atomicity and viewer checks.
- `fixtures/faults/recovery_corrections.json`: four source revisions for update/withdraw/re-create.
- `frontend/src/`: React TypeScript screen, playback controls, pitch, evidence panel and interaction tests.
- `tests/test_replay.py` and `tests/expected_tiny_metrics.json`: replay checks and hand-calculated metric expectations.
- `tests/test_scenario_fixtures.py`, `tests/expected_recovery_scenarios.json`, and
  `tests/expected_faults.json`: scenario audits and separate expected results.
- [Fixture review](docs/fixtures.md): qualifying recovery IDs, control differences and fault semantics.
- [Contract conventions](docs/contracts.md): identity, timing, coordinates and evidence semantics.
- [Progress](docs/progress.md): current milestone and next work.
- [Replay guide](docs/replay.md): controls, revision handling, commands and limits.

The fixture starts at minute 48 with Eastbridge trailing 0–1. It demonstrates a
duel followed by established control, a completed pass, an incomplete pass and an
opponent recovery. Its one-minute span is for contract checks; the planned ten-minute
one-versus-four recovery data is now available in the separate ten-minute fixture.
Replay computes these comparisons from event data and the interface displays the
eligible fact alongside its exact supporting records.

The fixture validator accepts only ordered initial revisions. The replay journal
also accepts exact retransmissions and corrections through `--updates`. It rebuilds
snapshots from available canonical revisions. The snapshot API publishes the
historically eligible factual card, evidence and lifecycle revision to the interface.
SQLite survives restarts and the browser retains withdrawal revisions within each
playback scope. Both the single-call adaptation and bounded Analyst/Producer
workflow are implemented and verified against Azure. Audience preferences and
bilingual explanation styles are now implemented with the same evidence checks.
The seeded generator now exports feeds compatible with the existing replay and
evidence pipeline. The pressure-proxy and defensive build-up-escape detector now
provides CLI evidence and durable replay cards with fully observed episodes and
meaningful controls. Possession without progression now has its own independent
controls, episode evidence and durable replay cards. Best next move: player-contribution
detection with independent controls and evidence-linked attribution, followed by recaps.
Azure application deployment remains later work.

## Run the replay

```sh
UV_CACHE_DIR=.uv-cache uv run --frozen python -m counterpress.replay fixtures/recovery_increase.json --speed 60
UV_CACHE_DIR=.uv-cache uv run --frozen python -m counterpress.replay fixtures/recovery_control.json
UV_CACHE_DIR=.uv-cache uv run --frozen python -m counterpress.replay fixtures/recovery_increase.json --at 54:00
```

The first two reports show one versus four and one versus one high recoveries,
with exact source IDs. At 54:00, the final comparison is not ready and future
events are absent. The CLI advances a virtual clock without real-time waiting;
speed affects the elapsed time needed to advance, not event timestamps or metrics.

Implementation references: [FastAPI first steps](https://fastapi.tiangolo.com/tutorial/first-steps/),
[Pydantic validators](https://pydantic.dev/docs/validation/latest/concepts/validators/),
[uv projects](https://docs.astral.sh/uv/guides/projects/).

## Try a persisted correction

```sh
UV_CACHE_DIR=.uv-cache uv run --frozen python -m counterpress.ingest increase fixtures/faults/recovery_corrections.json
```

The browser discovers the extended history while paused. Seek to 58:05 for the
updated 1-to-3 card, 58:10 for withdrawal, and 58:15 for a new 1-to-2 card. Seek
back to 58:00 for the original 1-to-4 evidence. Repeating the command is harmless.
Use the same database path for the API and CLI; [details](docs/history.md).

## Model adaptation (first Stage 6 increment)

The adapter accepts only two approved wording templates and inserts verified facts
in code. It records timeouts, refusals, invalid drafts and stale evidence, retaining
the factual explanation as fallback. No model call runs on a snapshot request.

See [adaptation setup](docs/adaptation.md) and `.env.example` for the explicit Azure
configuration and one-call CLI. Local tests use mocked HTTP; a separate live
request to the configured deployment passed. See the progress log for its result.

## Bounded Analyst/Producer workflow

The Analyst requests read-only comparison and quality evidence, then accepts,
narrows or rejects a candidate. The Producer receives a fresh validated package
and selects approved wording. Hard limits allow three Analyst requests, three
tool invocations, one Producer request and eight seconds overall. Corrections,
timeout and invalid output preserve the factual fallback.

```sh
UV_CACHE_DIR=.uv-cache uv run --env-file .env --frozen python -m counterpress.workflow increase --at-ms 780000
```

The command uses the existing Azure configuration and persists a sanitized audit.
The replay screen shows short action labels at the comparison cutoff. See the
[workflow guide](docs/workflow.md) for controls, limits and live verification.

## Audience views and languages

Choose **Analyst** or **Casual**, then **English** or **简体中文** above the
scoreboard. Club/metric preferences rank eligible insights; player selection
highlights actual qualifying contributions. Try `eb09` at 58:00 for event `p064`,
or `eb04` for an honest empty state. Team totals remain 1 versus 4.

Two local viewer profiles have independent preferences. Variant caching is shared
by evidence revision and perspective, and corrections invalidate old variants.
No Azure call is needed to switch views. See the [audience guide](docs/audience.md)
for cache behavior, language conventions, limitations and verification.

## Generate synthetic segments

```sh
UV_CACHE_DIR=.uv-cache uv run --frozen python -m counterpress.generator --seed 2 --profile pressure-shift --output var/my-generated-match
UV_CACHE_DIR=.uv-cache uv run --frozen python -m counterpress.replay var/my-generated-match/feeds/sim-cd3f34e3015e1cec5197fe8c.json
UV_CACHE_DIR=.uv-cache uv run --frozen python -m counterpress.generator --suite --output var/my-generated-suite
```

Choose a new output directory for each export. `feeds/` contains only public
Event-contract fixtures; `evaluation/` contains seeds, hidden settings, change
times, outcome labels and split assignments. Only feed files belong in replay or
agent inputs. The suite has 36 development and six held-out ten-minute segments.
Generated segments are available through the CLI; the browser still selects the
curated scenarios. See the [generator guide](docs/generator.md) for controls,
custom settings and limitations. No Azure configuration is needed.

## Inspect pressure and build-up escape

```sh
UV_CACHE_DIR=.uv-cache uv run --frozen python -m counterpress.pressure fixtures/pressure/increase.json --windows 48:00 49:00 50:00
UV_CACHE_DIR=.uv-cache uv run --frozen python -m counterpress.pressure fixtures/pressure/control.json --windows 48:00 49:00 50:00
```

These hand-authored two-minute controls show changing and unchanged episode
rates. Add `--json` for typed evidence with source revisions, or pass a generated
feed and `--team northport` to inspect the opposing build-up. Default windows are
48:00–53:00 and 53:00–58:00. Defensive-third duels are a disclosed pressure proxy;
the detector does not infer unobserved pressure or causal tactical effectiveness.
See the [pressure guide](docs/pressure.md) for episode rules, exclusions, minimum
samples, cooldown receipts and corrections.

In the browser, select **Pressure and escape shift**, then **Go to comparison**.
Choose **Pressure exposure** or **Escape under pressure** under Metric focus.
The one-card budget ranks eligible recovery and pressure stories together.
**Show evidence** opens sample counts, exclusions, episode outcomes and exact
source revisions. The **Pressure and escape control** scenario has no eligible
rate-change card. See [publication and UI details](docs/pressure-publication.md).

To try corrections against the same local database used by the API:

```sh
UV_CACHE_DIR=.uv-cache uv run --frozen python -m counterpress.ingest pressure-increase fixtures/pressure/replay_corrections.json
```

Seek to 58:05 for updated exposure and withdrawn escape, 58:10 for both withdrawn,
and 58:15 for restored stories. Seeking back to 58:00 retains the original facts.

## Inspect possession without progression

```sh
UV_CACHE_DIR=.uv-cache uv run --frozen python -m counterpress.progression fixtures/progression/increase.json
UV_CACHE_DIR=.uv-cache uv run --frozen python -m counterpress.progression fixtures/progression/control.json
```

The positive control changes from 1/6 to 4/6 sustained possessions without 15 m
of observed forward gain; the negative control stays at 1/6. In the browser,
select **Possession without progression**, then **Go to comparison** and
**Show evidence**. This is a spatial proxy, not a claim about possession dominance
or tactical value. See the [progression guide](docs/progression.md) for eligibility,
excluded episodes, correction commands and verification.
