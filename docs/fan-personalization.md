# Fan personalization

Clubhouse (`#football`) combines device-owned favourites, player and club profiles, comparisons and ranked recommendations. The APIs below supply deterministic views over the [data foundation](personalization-data.md). See the [walkthrough](demo-guide.md) for the user journey.

## Capabilities

- Follow up to **four clubs and twelve players** on a device. All registered
  identities are valid, including reserves and supporting opponents. Select a
  primary club for the theme and an optional player to focus on.
- A home feed containing **nine existing/new highlights** and **four featured
  full matches**, ranked by followed players and clubs. Full matches are a
  separate list for Match Centre, never highlight cards.
- Player and club views with role-appropriate statistics, season and recent-form
  stories, event activity maps, evidence and navigation actions.
- Side-by-side comparison for two to four players under one season and cutoff.
- Live match cards with English/Simplified Chinese and casual/analyst variants.
  Facts remain identical across preferences. Scoring, creating, passing and
  defending choices prioritize relevant available information.
- Player focus returns the active eleven from each side, the focused player's
  involvement, and current statistics. Keep all active players visible; highlight
  the chosen player and involved actors. This is not a new tracking/animation feed.
- Contextual question suggestions with **existing data-view actions**. These are
  navigation prompts, separate from the model-powered [Footie assistant](grounded-assistant.md).

No model calls, new Azure resources or preference database are involved. The
career data still comes from the [data foundation](personalization-data.md).

## Start and explore the API

```sh
uv sync --locked
uv run --frozen uvicorn counterpress.api.main:app --host 127.0.0.1 --port 8000 --reload
```

Open <http://127.0.0.1:8000/docs> and expand **Fan personalization**. All endpoints
except capabilities use POST because viewer choices should not live in URLs,
browser history or shared caches. These POST requests are read-only. The server
does not save favorites or create an account/cookie. Every response is
`Cache-Control: private, no-store`, including errors. Bodies are limited to 16 KiB.

| Purpose | Endpoint |
|---|---|
| Languages, limits, storage and assistant availability | `GET /api/fan/capabilities` |
| Validate/canonicalize device preferences | `POST /api/fan/preferences/validate` |
| Following, ranked highlights and featured matches | `POST /api/fan/home` |
| Personalized player profile | `POST /api/fan/players/{player_id}` |
| Personalized club profile | `POST /api/fan/clubs/{club_id}` |
| Common-scope player comparison | `POST /api/fan/players/compare` |
| Playhead-specific match cards and player focus | `POST /api/fan/matches/{match_id}` |

The existing `/api/data/` endpoints still provide history pagination, metrics and
replays. The catalog lists every club. `/api/data/players` supplies the 44 featured
players; use `featured=false` and pagination to discover all 180 registrations.

## Preferences

```json
{
  "version": 1,
  "favorite_club_ids": ["redhaven"],
  "favorite_player_ids": ["rh08"],
  "primary_club_id": "redhaven",
  "language": "en",
  "depth": "casual",
  "metric_focus": "balanced",
  "focus_player_id": "rh08"
}
```

Omitted fields use neutral/casual/English defaults. The primary club must be a
favorite club. A focus player need not be followed. IDs must exist in the registry;
unknown IDs, duplicates, unsupported versions, extra fields and over-limit lists
are rejected. Lists are sorted canonically, making choice order irrelevant.

The response envelope echoes `request_id`, normalized `preferences`, a
`preference_id`, dataset identity and contract `version`. It contains no server
viewer identity. The client must discard results from an old context.

## Home and profile examples

```sh
curl -sS http://127.0.0.1:8000/api/fan/home \
  -H 'Content-Type: application/json' \
  -d '{"request_id":"my-football","preferences":{"favorite_club_ids":["redhaven"],"favorite_player_ids":["rh08"],"primary_club_id":"redhaven"},"as_of":"2026-10-20T00:00:00Z"}'
```

`as_of` defaults to current UTC. Home only includes completed featured matches and
their highlights before that cutoff. The fixed example date above includes all
four authored fixtures. It is useful for checking the complete library regardless
of today's actual time. Undated preloaded highlights remain available without a
season filter. A season filter excludes them because they have no league season.

Home returns `following.players`, `following.clubs`, `highlights`, `matches`,
`theme` and `onboarding`. Rank is deterministic: a followed participant takes
priority, then the primary club, then other followed clubs. Each item includes a
relevance reason and the IDs that matched. It does not imply measured popularity
or a trained recommendation model. Unfollowed content remains discoverable.

Highlights have `tag: "match"` plus their parent match/date, or
`tag: "preloaded"`. Do not display "synthetic" as the card tag. Legacy actions
provide a `scenario_id`; new career excerpts provide a replay URL. If a reviewed
clip's source changes, the authored card is withheld until its replay can be
revalidated. A correction to a historical career baseline recomputes milestone
titles; it must not leave a false "30 goals" headline behind.

Player and club requests accept `season` and `as_of`. Responses contain a complete
canonical `profile` and a `presentation` with tiles, natural-language cards, activity
map labels, follow state and questions. Analyst mode exposes more metrics and
denominators. Known partial counts remain visible with `coverage_label` describing complete-match coverage. Fully unavailable statistics remain `null`, never observed zero. Assist rates use counts and minutes from the same covered matches; comparisons suppress rates below 180 covered minutes. All 44 featured players now have full assist coverage after explicit archive credits were recovered. Shot-assist/save/recovery gaps remain visible. Partial estimates retain coverage flags.

Comparison requests add `player_ids`, for example `["rh08", "sb09"]`. Every player
uses the same season and UTC cutoff. There is no overall winner or ungrounded
quality score. `rate_comparison_available` requires at least 180 minutes for every
player; `same_role` tells the UI whether the compared positions differ.

## Playback, corrections and the pitch

```sh
curl -sS http://127.0.0.1:8000/api/fan/matches/career-showcase-southbank-redhaven \
  -H 'Content-Type: application/json' \
  -d '{"request_id":"watch-cross","preferences":{"favorite_player_ids":["rh09"],"focus_player_id":"rh09"},"cutoff":{"period":1,"elapsed_ms":592006},"card_budget":3}'
```

The response includes:

- `facts`: canonical live score, current player/club statistics, career baselines
  and milestones. Preferences never change these facts.
- `cards`: at most the requested budget (0–5). Every claim binds subject, metric,
  scope, value and evidence. Milestone claims refer to their event's time, not a
  later playhead at which the player may have scored again.
- `focus`: selected player/status, all active player IDs, followed active players,
  last twenty recorded involvements, and current match statistics/tiles. A player
  outside this fixture gets `not_in_match`; a substitute gets `not_yet_on` or
  `substituted` as appropriate. Do not invent positions for these states.
- `evidence` and `view_id`: the current event digest, career baseline, playhead and
  preference fingerprint. Replace the whole view when these change.
- `questions`: supported next steps. The goal action carries the exact event ID;
  find the replay position from that event, rather than assuming a fixed duration.

In the v3 dataset, at first-half **592005 ms**, Mateo Cross remains on 79 career goals. At **592006 ms**,
the goal result is available and the card reports 80. This cutoff is a **source
football clock**, not a narration/audio timestamp. The frontend must map its
animation or speech clock back to the source event clock before requesting a view.
Always clear old cards when seeking, changing preferences/matches, or applying a
new source revision. A retracted milestone must disappear.

`through_sequence` optionally constrains received deliveries for recovery tests.
Normal clients omit it and use current known revisions at the playhead. The new
career index is not yet connected to the existing Azure Event Hubs consumer, so
do not claim cloud-wide live career updates. Local revision ingestion and reads
are tested; the bridge is separate work.

## Independent browser adapter

[`integrations/personalization/client.ts`](../integrations/personalization/client.ts)
has no React dependency or layout. Import/copy it into the UI branch when ready:

```ts
import {
  createFanClient, readPreferences, savePreferences, toggleFavorite,
} from '../../integrations/personalization/client'

const { preferences, status } = readPreferences(window.localStorage)
const next = toggleFavorite(preferences, 'player', 'rh08')
const saved = savePreferences(window.localStorage, next)
const client = createFanClient() // keep one instance per rendered surface
const home = await client.home(next, { as_of: '2026-10-20T00:00:00Z' })
// Render the following list and ranked highlights.
// Call client.cancel() on unmount, seek or any context change.
```

Adjust the relative import for the file's location. The adapter uses same-origin
`/api/fan` URLs; the existing Vite API proxy supports local frontend development.
Build a `Registry` from the catalog/player pages and pass it to storage helpers
when you want client-side identity validation as well as the server checks.

The new storage key is `counterpress.fan.preferences.v1`. If absent, the adapter
reads and migrates `counterpress.matchday.preferences.v1` in memory, preserving
language, depth, club and selected player. Reading never overwrites either key.
Saving changes only the new key. Explicit reset clears both so legacy favorites
cannot reappear. Storage denial returns a failure/status; do not promise saved
preferences when the browser refused them. Cross-device synchronization is absent.

The client cancels superseded requests and also rejects old results if a transport
ignores cancellation. It verifies echoed request/preferences before returning a
renderable response. Use separate clients for independent screens. On a browser
`storage` event, re-read preferences and cancel/reload affected views so other tabs
reflect the change. Render text normally through React, never as raw HTML.

## Verification

```sh
.venv/bin/pytest -q
node --test integrations/personalization/client.test.mjs
frontend/node_modules/.bin/tsc --noEmit --strict --target ES2022 --module ESNext \
  --moduleResolution Bundler --lib ES2022,DOM --skipLibCheck integrations/personalization/client.ts
.venv/bin/python scripts/container_smoke.py http://127.0.0.1:8000
```

CI runs adapter checks alongside the unchanged UI tests/build and checks the new
APIs through a restricted container. Exact local evidence is recorded in
[personalization verification](verification/fan-personalization-checks.md).

## Related services

The [Footie assistant](grounded-assistant.md) uses these records for grounded questions. The [career revision bridge](career-revision-bridge.md) keeps corrected source facts available to profiles and insights. Preferences remain device-scoped; cross-device preference accounts are not part of this service. The data API exposes four featured fixtures, while the Match Centre / Analyst replay adapter currently supports three full matches.
