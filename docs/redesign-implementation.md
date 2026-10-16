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
adaptation remains off until step 2 is implemented and verified.

## First release verification

**Matchday is live.** [Release evidence](verification/matchday-live.json) records
the exact deployed commit and passing local/CI/live checks. Step 2's
[editorial pilot](evaluation/editorial-pilot.md) is complete: a single editor had
21/22 valid adaptations versus 13/22 for the two-role graph. Templates remain the
public default. The [editorial access controls](editorial-access.md) now implement
Entra authorization, shared durable admission, revision-bound reuse and stale-task
cancellation locally. Real Entra/Cosmos activation checks, human usefulness and
Studio remain pending. Human participants will be arranged later; the [test kit](evaluation/fan-usability.md)
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

Hosted model adaptation remains disabled. Matchday currently presents factual
recap statements, not generated editorial wording. Studio and user research are
subsequent releases, not features of this first UI slice.
