# Redesign delivery plan

Implementation starts locally, using synthetic fixtures and no cloud credentials.
Each vertical slice is reviewed through a PR, backend/frontend/container/Bicep CI,
and the existing protected OIDC release. Verify the exact live revision after each
release. Keep the US$75 trial envelope; no additional service is needed for the fan UI.
Real club/player identities remain permission-gated. Research and the reviewed
proposal are local working artifacts, not application assets.

1. **Matchday:** useful default at 58:00, optional following, human-readable events,
   primary recap, original display identities, local preferences, mobile controls,
   visible corrections. Preserve the existing analysis workspace and evidence rules.
   Gate: interaction, isolation, correction, persistence and responsive checks.
2. **Editorial workflow:** compare templates, one agent and existing Analyst/Producer
   on frozen cases. Integrate the smallest useful bounded workflow with Cosmos,
   explicit triggers, quotas, caching, stale-job cancellation and factual fallback.
   Gate: real model proof, supported claims/citations, latency/cost/fallback evidence.
3. **Studio:** authorized producer review, exact-revision approval, clean preview and
   export, correction/withdrawal invalidation. Gate: access control and race/restart
   tests; never present a local preview as authenticated broadcast publishing.
4. **Showcase and evaluation:** validated additional story segments if needed,
   five-fan formative tests, two producer reviews, bilingual/accessibility checks,
   held-out evaluation and a sub-two-minute demo. These studies are not yet done.

Develop and verify each slice locally before pushing. Do not batch every redesign
feature into one late cloud deployment. Do not enable anonymous paid AI or add
recurring services without checking current credits and limits. Hosted model
adaptation is available only through the explicit assigned-editor Studio pilot;
fan reading and polling never trigger model work.

## First release verification

**Matchday is live.** [Release evidence](verification/matchday-live.json) records
the exact deployed commit and passing local/CI/live checks. Step 2's
[editorial pilot](evaluation/editorial-pilot.md) is complete: a single editor had
21/22 valid adaptations versus 13/22 for the two-role graph. Templates remain the
public default. The [editorial access controls](editorial-access.md) now implement
Entra authorization, shared durable admission, revision-bound reuse and stale-task
cancellation locally. [Real Entra/local API and managed-identity Cosmos checks](editorial-integration.md)
have passed. Hosted Studio authorization and a bounded authenticated model check
have also passed; human usefulness remains pending. The [Studio review slice](studio.md) now implements
authenticated producer review, exact-version durable approval, revocation, clean preview
and checked export. Its [real browser SPA and live Cosmos checks](verification/studio-integration.json)
have passed. [Studio is now live](verification/studio-live.json), with hosted Microsoft sign-in,
approval, preview, download and revocation verified. Human participants will be arranged later; the [test kit](evaluation/fan-usability.md)
is ready and no human ratings have been fabricated.

The Matchday implementation is in `frontend/src/matchday/`. The previous workspace
is preserved in `AnalysisApp.tsx` and reachable at `#analysis`. Source schemas,
fixture IDs, deterministic rules and cloud infrastructure are unchanged.

Run `npm --prefix frontend test -- --reporter=dot` and
`npm --prefix frontend run build`. The browser smoke script additionally exercises
all four story families, readable evidence, persisted bilingual preferences,
360/390/640/1365-pixel layouts, 200% text sizing, rewind and analysis navigation.
This is automated verification, not a human usability study or full accessibility audit.

With Playwright available to Node and its Chromium installed:

```sh
node scripts/test_matchday.cjs http://127.0.0.1:8000
```

The script writes the two Matchday screenshots under `docs/screenshots/`.
`CHROME_EXECUTABLE` can select an installed Chrome binary. Set
`COUNTERPRESS_CHECK_CORRECTIONS=1` when the target already has the prepared
`stream-recovery` correction history to also check 4/3/withdrawn/2. The script
reads API data and changes browser-local preferences only; it sends no events.

Matchday presents factual recap statements without model calls. The assigned-editor
Studio AI pilot is now enabled: an explicit action invokes the single editor through
shared quotas and cache, and approval binds the chosen attempt, wording, evidence
and expiry. See [release verification](verification/studio-editorial-live.json).
Local startup stays disabled by default.
Human fan and producer usability research remains pending.

The broadcaster slice adds a per-story presenter cue and lower-third preview/download
to Studio. Both preserve the complete approved wording and qualification, with
server-side approval/correction/expiry checks and provenance. No new service, agent
or model call is involved. See [workflow](studio.md#presenter-cues-and-lower-thirds)
and [local verification](verification/studio-broadcast-local.json). Editable rundowns,
live broadcast playout, human studies and the final demo video remain subsequent work.

## Matchday fan refresh

The requested visual refresh adds original bridge/compass crests, persisted club
background colours, a 22-player interactive pitch at both explanation levels and
plain-language bilingual stories. Player initials expand to names on hover/focus
or selection. Playback animates ball actions and illustrative off-ball movement;
mobile uses a portrait pitch and reduced-motion users have a manual position control.
Disclosure is consolidated at the footer, and Matchday no longer exposes JSON.

The API adds at most 24 canonical events, ordered by occurrence and bounded by the
snapshot cutoff. Corrections appear only when available. Only seven original actors
are recorded in the fixture; additional pitch identities are display-only, and the
footer explains the distinction from tracking data. Studio's approved wording and
qualification requirements remain unchanged. No new service or model call is needed.
See [verification](verification/matchday-pitch-local.json). Human usability testing
is still required before making claims about fan comprehension or commercial readiness.

## Broadcast-style tracker refinement

The tracker opens at the latest available event, with a current-player panel,
central pitch and timestamped commentary rail on desktop. On phones, playback
controls sit immediately below the portrait pitch and commentary follows them.
Selecting an entry seeks both the pitch and feed; only the selected event and
earlier entries are shown. Playback starts at the beginning when opened at the
latest event and stops at the end. Corrections replace the feed using canonical
snapshot events rather than appending duplicate commentary.

The initial 26-metre spotlight was removed in the replay-gallery iteration below;
all 22 players now retain their full markers and labels. Team shapes now
respond to ball position and the actor's team: wider attacking support, compact
defensive lines, a goal-side defender and bounded goalkeepers. Random drifting
was removed. Exact ball/actor/recipient anchors still come from source events;
the rest is illustrative and is not a tracking reconstruction or tactical measurement.

Design references reviewed on 18 October 2026:

- [Sportradar Live Match Tracker](https://widgets.sir.sportradar.com/sportradar/en/live-match-tracker), visually inspected in its public demo: pitch action, compact score/time and surrounding context. Its [official layout documentation](https://apidocs.sportradar.com/resources/widgets/docs/lmt/lmt-plus) supports split desktop and stacked mobile compositions.
- [FotMob match centre](https://www.fotmob.com/matches/paredes-vs-torreense/ane10ht): documented commentary/ticker alongside match information informed the readable, timestamped feed.
- [Sofascore Attack Momentum](https://www.sofascore.com/news/how-sofascores-attack-momentum-changed-sport-analysis): visual emphasis helps explain match flow. CounterPress uses this as a hierarchy reference; it does not reproduce or claim an attack-momentum metric.

These are design references only. No vendor widget, artwork, tracking feed or
proprietary statistic is embedded. The changes reuse the current snapshot and
revision delivery; there is no additional service, subscription or model call.


## Replay gallery: designer and football-fan review

The review found four problems: hiding distant labels made players appear to pop
in; formation resets broke movement continuity; the strongest demo was buried
behind a single promotion; and the play button was below a tall pitch. A current
shot also revealed its outcome in commentary before the ball arrived.

Implemented changes:

- Three selected-state replay cards above the action, with brief descriptions,
  action spans and direct source-clip links. Mobile cards omit secondary copy to
  keep titles readable; the selected play retains its context below the cards.
- All 22 players remain visible. Persistent identity trajectories join at action
  boundaries, and active markers render above background markers. Carry motion
  uses the full action duration to avoid implausibly fast bursts.
- Playback controls above the field: pause/resume, previous/next, restart, speed
  and a keyboard-operable scrubber. Reduced-motion users retain manual start/end
  control. English and Chinese labels remain supported.
- A tighter header and less repeated explanatory content. Goal wording, including
  accessible commentary labels, waits for the shot; score rewinds with the pitch.

The first screenshot review prompted a second pass: controls moved above the
field on mobile as well as desktop, the large secondary explanation card was
removed, and two crowded illustrative starting slots were separated. Source
coverage and estimation limits remain in the footer rather than interrupting play.

The new stories reference Brazil's Richarlison combination and Argentina's Di María
counterattack. See [coverage and role mapping](replay.md#clip-reconstruction-source-coverage).
Automated and visual checks verify operation, not whether a fan understands the
play. The next human test is to ask a viewer to switch moments, identify the
runner/assist and rewind one pass without guidance, then compare their account
against the source clip. No new agent, model call or Azure service was required.

## Featured highlight refinement — 18 October 2026

The previous top-row chooser gave three plays equal priority and asked the fan to
configure the page before watching. Matchday now uses an editorial hierarchy:
today’s featured headline, score and pitch, then related content at the bottom.
The main action says Play highlight; secondary cards contain original pitch
illustrations, readable descriptions and durations, including on phones. Clip
references and reconstruction provenance sit in the footer. Analysis is still
reachable through the header and footer, without a scenario selector in the
highlight flow. Switching returns focus to the updated headline and keeps a
refreshable URL. No fabricated popularity counts or live badges were added.

Technical checks cannot establish fan usability. The next validation is to ask
participants to watch the featured play, discover another highlight and return
without instructions. Existing source fixtures remain separately authored
reconstructions; this UI change does not merge them into one measured match feed.
