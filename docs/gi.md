# Match Centre replay data

Match Centre (`#gi`) is the default workspace. Overview, Moments and Watch full match share the selected fixture. Moments supports action, team, player and half filters; full-match playback adds speed and continuous sequence controls. Analyst Mode opens from the full-match view.

## Read model

`GET /api/gi/matches/{match_id}` serves a validated, cached full-match model. The registered library contains `synthetic-32fe41c5d304ce68d7d9`, `wyscout-2058017` and `wyscout-2058007`. See [data provenance](../README.md#data-and-scope) for generated and adapted fixture definitions.

Contracts preserve source identities, occurrence order, period-relative clocks, revisions, source tags and nullable coordinates. Display identities are stable fictional aliases. The source fixture is bundled with the application; opening a replay does not require access to the original data provider.

UI statistics derive from the selected events and scope. The paginated action list does not change the statistical denominator. Own goals contribute to the beneficiary team's score. Unknown outcomes remain unknown. Source event maps and recorded shot endpoints are distinct from reconstructed full-team replay movement.

The API exposes event-backed replays rather than a live video feed. Saved highlights reference canonical events in the selected match. Reports and analyst conversations have separate [source and temporal checks](analyst-room.md).

## Validation

```sh
.venv/bin/python -m pytest -q
npm --prefix frontend test
npm --prefix frontend run build
NODE_PATH=/Users/haydn/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules CHROME_EXECUTABLE='/Applications/Google Chrome.app/Contents/MacOS/Google Chrome' node scripts/test_gi.cjs http://127.0.0.1:8010
```

The browser test uses an isolated headless profile, the actual local API, desktop/390px/360px layouts, metric/filter reconciliation, own-goal navigation, review context, keyboard access and retry. It writes screenshots to ignored `var/gi-desktop.png` and `var/gi-mobile.png`. See `verification/gi-local.json` for recorded results.

The backend-wide evaluation lock is versioned `gi-reader-regression-v1` because adding the GI reader changes the backend source set. Existing prompts, synthetic scenarios and evaluation oracles are unchanged; this is not a new live-model evaluation.
