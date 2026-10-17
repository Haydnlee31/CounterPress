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
