# Clubhouse — local user test

Open **http://127.0.0.1:8017/#football**. The same interface is available through
**Clubhouse** in the dashboard navigation. This change is local; Azure has not
been redeployed.

## Try it as a fan

1. In **Players**, search for **Enzo Clarke**, follow him, then open his profile.
   The career view shows his recalibrated goals, assists and appearances. Refresh the
   page: the Following state should remain.
2. Explore **Match history**, expand a result, and visit **Seasons**. Use the
   Period selector to change between career and an individual season. The pitch
   heatmap shows where recorded actions took place.
3. Open **Mateo Cross** and choose **Mateo Cross reaches 75 career goals**. The highlight
   plays automatically with 22 active players, named on hover/focus. The score
   changes from 2–2 to 2–3 and the milestone appears when the shot finishes.
   Drag the replay slider back to the beginning: the score and cards rewind too.
   At the end, use **Replay** to watch it again. Escape closes the viewer.
4. Add Clarke and **Dario Voss** to **Compare**. Compare goals, assists, passing,
   challenges and minutes in the same period. You can select up to four players.
5. In **Clubs**, follow **Redhaven** and open its club profile. Visit **Following**
   to find followed players, club records and relevant highlights together.
   “Make my club” sets the hub's accent. You can follow up to 12 players and four
   clubs; changing one browser tab updates another tab on the same local origin.
6. Switch **Insights** between **At a glance** and **In depth**, then try Chinese.
   Insight wording and the number of profile metrics change; football facts do
   not. Known partial statistics display their covered-match count. Fully unavailable statistics appear as a dash, never a fabricated zero. Assists now have coverage for all 44 featured players.

Tell us where you hesitated, which numbers you expected but could not find, and
whether the milestone appeared at a convincing moment. The next development
stage waits for this user review.

## Restart the local app

From the repository root, build the frontend:

```sh
npm --prefix frontend run build
```

Then start the server and leave this terminal open:

```sh
COUNTERPRESS_DB_PATH=var/spatial-review-http.sqlite3 COUNTERPRESS_PROFILE_DB_PATH=:memory: COUNTERPRESS_STATIC_DIR=frontend/dist COUNTERPRESS_STREAMING=off .venv/bin/python -m uvicorn counterpress.api.main:app --host 127.0.0.1 --port 8017 --no-access-log
```

If 8017 is already running, open the link instead of starting a second server.
No model calls, Azure sign-in or deployment are required for Clubhouse. A first
visit initializes the local career index and can take a little longer.

## Integration and review notes

- The new UI lives in `frontend/src/football/`. Shared UI changes are limited to
  the lazy route in `App.tsx` and the Clubhouse link/context handling in
  `shell/AppHeader.tsx`. This keeps the colleague's later redesign easy to merge.
- It uses the existing `/api/fan/*` and `/api/data/*` contracts and independent
  browser adapter. The v2 data refresh also corrects assist coverage and recalibrates generated careers. Names, IDs and saved favorites remain stable.
- The directory displays 44 featured players and four featured clubs. The loaded
  identity registry also resolves supporting opponents and substitutes in history
  and the pitch. Historical matches stay in profile history.
- The footer makes the library snapshot date visible. Every profile, feed and
  comparison shares the cutoff at the end of that date. Replays use source event
  occurrence/availability clocks; playback seconds are never sent as match time.
- Original jersey illustrations and the new Southbank/Redhaven vector marks are
  local SVG artwork. All 44 featured players have original fictional portraits generated with the built-in image tool, including the four approved previews. The stable player-ID map in `frontend/src/football/portraits.ts` supplies cards, following and profile views. JPEG assets are bundled by Vite and loaded lazily; unavailable images and supporting players retain jersey artwork. The exact prompts are in `docs/player-portrait-prompts.json`. No third-party portraits, crests or site assets are copied.
- The new career highlights open in the hub's replay viewer; six existing clips
  open their established Matchday routes. The viewer uses existing event-based
  formation interpolation, not a new player-tracking feed. It makes no voice calls.
- Browser storage denial is visible; choices still work for that visit. No
  accounts, cross-device sync or general Footie chat are implied by this UI.
- Suggested questions navigate supported history/season views. They do not call
  an unfinished agent. Readable statistics and insight cards replace raw JSON.

Design references: [NBA directory](https://www.nba.com/players),
[Tracker profiles/history](https://tracker.gg/valorant/),
[DataMB](https://datamb.football/?lang=en), and
[StatsHub](https://www.statshub.com/player-stats). The design adapts discovery,
profile hierarchy and comparable metrics to CounterPress's own data and identity.

## Verification

```sh
npm --prefix frontend test
node --test integrations/personalization/client.test.mjs
npm --prefix frontend run build
.venv/bin/python scripts/container_smoke.py http://127.0.0.1:8017
```

The UI tests cover search/follow/persistence, missing-stat handling, history,
comparison scope, stale responses, retry, unavailable storage, cross-tab changes
and causal replay cutoffs. Manual Chrome checks cover the real local data,
desktop and 390-pixel layouts, follow/profile/highlight/rewind, and comparisons.

## Coverage and portrait review

- Open Rory Ellis: his career assist count is visible, including with **At a glance** selected.
- Switch to **In depth**: passes leading to a shot, saves and recoveries can have coverage details because the two adapted archives do not completely record them.
- Filter the directory by each club to see its eleven portraits. Search a newly illustrated player such as Amir Rhodes or Nico Alder and open the profile: the same portrait follows the player. The Clubhouse rename preserves `#football` links and saved favorites. This portrait update does not change the statistics dataset.
- Career totals and the new showcase changed with recalibration; the older two adapted matches and the existing legacy simulation retain their source actions.
- Verify all 844 records with `.venv/bin/python scripts/verify_personalization.py --output docs/verification/personalization-data.json`.
