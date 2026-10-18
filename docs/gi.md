# GI full-match reader

Open `http://127.0.0.1:8010/#gi` after starting the local preview:

```sh
npm --prefix frontend run build
COUNTERPRESS_STATIC_DIR=frontend/dist .venv/bin/uvicorn counterpress.api.main:app --host 127.0.0.1 --port 8010
```

GI is a separate navigation destination from Matchday and Explore data. It opens Eastbridge versus Northport, using the licensed historical match as the source behind the display aliases. Select a goal, click a metric card, or filter by team, player and half. The action list opens pitch locations and passing routes, with previous/next actions and a ten-second context on either side. The list initially renders 40 matching actions and offers more; statistics always cover the entire selected team/player/period scope, independent of the action-list filter.

Player names reuse fictional dashboard identities, with unique substitute labels for five additional participants. Source identity mappings stay stable across filters and reloads. The historical source and alias disclosure appear in the footer; the visible match header, filters and action details use Eastbridge/Northport. The 4–2 result is preserved. The aliases do not identify the actual footballers. Attribution and metric definitions are at the bottom of GI.

## Current implementation

`GET /api/gi/matches/wyscout-2058017` serves a validated, cached, immutable full-match read model. Its separate Pydantic contracts preserve provider IDs, source/occurrence order, period-relative occurrence time, revision, raw tags and nullable locations. The source manifest has a pinned SHA-256. The source fixture is packaged through the existing Docker `COPY fixtures` instruction. No new dependencies or runtime secrets are required.

The UI derives scope counts from these returned events; no model is invoked. Goals reconcile to 4–2 including the Croatian own goal. Pass totals exclude restarts, and one Croatian pass has an unknown outcome and missing end point. On-target non-goals are not automatically classified as saves. Review candidates currently use the provider's dangerous-ball-lost tag, not a new causal model or automatic player-error judgment.

The first version uses a **bundled, read-only fixture**, separate from the existing highlight store. The research SQLite import remains under ignored `var/gi-research/wyscout/`; it is not a production Cosmos migration. There are no uploads, processing jobs, AI calls, or new cloud resources. A future multi-match reader should use per-event or bounded-segment GI storage with an atomic import manifest and pagination, rather than the existing whole-history Cosmos document.

Coordinates show actions, not full-team tracking. Pass routes connect the recorded start/end locations; shots show their recorded starting location rather than inventing a goal-mouth destination. Context uses `(event time − 10 seconds, event time + 10 seconds]` in the same period. Previous/next navigation follows the whole-match occurrence order, explicitly switching the action filter to Every action.

The official replay opens externally. There is no embedded video or exact-time jump: playback, permission for any processing/embedding, and per-half media-clock anchors have not been verified. No video has been downloaded. GI currently uses English; the existing Matchday/Explore bilingual experience is unchanged.

## Validation

```sh
.venv/bin/python -m pytest -q
npm --prefix frontend test
npm --prefix frontend run build
NODE_PATH=/Users/haydn/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules CHROME_EXECUTABLE='/Applications/Google Chrome.app/Contents/MacOS/Google Chrome' node scripts/test_gi.cjs http://127.0.0.1:8010
```

The browser test uses an isolated headless profile, the actual local API, desktop/390px/360px layouts, metric/filter reconciliation, own-goal navigation, review context, keyboard access and retry. It writes screenshots to ignored `var/gi-desktop.png` and `var/gi-mobile.png`. See `verification/gi-local.json` for recorded results.

The backend-wide evaluation lock is versioned `gi-reader-regression-v1` because adding the GI reader changes the backend source set. Existing prompts, synthetic scenarios and evaluation oracles are unchanged; this is not a new live-model evaluation.

## Next stage

Verify video playback and lawful embedding, calibrate event-to-media offsets for each half and sampled events, then add accurate seek controls. Only then introduce owned/licensed video uploads with roster/event files and private storage. Video-only extraction should begin with short reviewed clips and measured accuracy/cost. Existing US$75 total budget still applies.

## Canvas redesign

The match room now leads with existing club crests, a dark pitch canvas and a compact action rail. Team and period chips replace dropdown-heavy controls. The Shot map shows the scoped shot locations in club colours; goal markers are larger, and selecting any marker opens that shot. Keyboard Enter/Space selection is supported. Both teams use normalized attacking direction. The full-match scrubber steps through recorded actions by occurrence order, not evenly spaced wall-clock seconds.

A six-goal ribbon shows the running score and is horizontally scrollable on small screens. Scope metrics live below the canvas as interactive rows instead of KPI cards. Context, raw event reference and attribution remain available. No source events, API contracts or outcome calculations changed.

Design reference: [ArtCraft's creative workspace](https://github.com/storytold/artcraft), specifically its emphasis on canvas interaction. This is an original football layout; no ArtCraft assets or source were copied. The precise dashboard reference from the user was not supplied.
