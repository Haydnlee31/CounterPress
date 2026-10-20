# Layout refresh — local verification, 20 October 2026

Preview: `http://127.0.0.1:8017/?story=last-gasp#matchday`.
No commit, push or deployment was performed for this revision.

## Changes

- Primary navigation: Matchday, Match Centre, Clubhouse, Footie; Tools stays secondary.
- Explore Data's functionality is now Matchday's Breakdown view. `#explore` remains compatible. Both views share a mounted `HighlightExperience` and `MatchPitch`.
- Shared cream/forest palette, club accents, compact Matchday introduction/score and consistent Watch/Breakdown and Overview/Moments view controls.
- Match Centre comparisons receive more space; mobile places them before the editorial summary. Footie's standalone welcome is more compact without applying those overrides to its drawer.
- Larger player hit areas are rendered behind visible markers; decorative halos/shadows no longer intercept adjacent-player clicks. Phone commentary follows the pitch.

## Commands and results

```sh
npm --prefix frontend test -- --reporter=dot
```

```text
Test Files  29 passed (29)
     Tests  172 passed (172)
```

This includes analysis phase seeking, 22-player selection, player evidence, comparison counts, changed-highlight resets, retry behavior, navigation and a new App-level legacy/Watch/Breakdown test that checks DOM identity, exact seek position and preserved player selection.

```sh
npm --prefix frontend run build
```

```text
> tsc --noEmit && vite build
✓ 302 modules transformed.
✓ built in 879ms
```

Browser tooling is supplied by the local Codex runtime; no package dependency was added:

```sh
NODE_PATH=/Users/haydn/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules node scripts/test_unified_layout.cjs
```

```text
PASS
• Watch/Breakdown/history: same mounted pitch, exact seek, player, comparison and route preferences retained
• Instrumented narration: one recording, no refetch/restart/pause on view switch
• Watch, Breakdown, Match Centre, Clubhouse and Footie: no horizontal overflow; all main navigation visible at 1440/768/390/360px
• Chinese at 360px: translated views, phase comparison and seek controls usable
• Match Centre: keyboard shot map, animated replay, filters and Footie open/close preserve paused context at 360px
• Empty directory reset, snapshot outage/retry, legacy Explore link, reduced-motion controls and 720px reflow pass
No assistant requests or browser errors. Azure voice was stubbed; no paid synthesis.
```

The audio check uses an actual HTMLAudioElement with a generated silent recording and timing markers. It proves media continuity across views, not Azure voice quality. At 1440×1000 the pitch canvas begins at approximately 590 CSS pixels from the top. Screenshots and results are in ignored `var/layout-validation/`; desktop and mobile Watch, Breakdown, Match Centre, Footie and Chinese comparison views were visually inspected. The 720px check exercises reflow, not browser zoom UI.

An isolated preview was started without Azure:

```sh
.venv/bin/python scripts/run_footie_local.py --port 8018
NODE_PATH=/Users/haydn/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules node scripts/test_footie_context.cjs
```

```text
PASS Footie context: profile season, no automatic questions, source-time highlight handoff, Match Centre event revision, pause/return, focus restoration, mobile layout, no browser errors.
```

The latter submits three deterministic questions to the non-Azure server. No paid model or synthesis calls were made. No backend/data/model settings changed, so the backend suite and live Azure voice/model checks were not repeated. Human usability testing and assistive-technology testing remain separate from these automated checks. Untracked `reports/` and `research_notes/` were left untouched.

## Spacing follow-up — 20 October 2026

User review identified the Footie mascot touching its welcome heading. The 176px mascot had been constrained by a 120px wrapper. The wrapper now follows the artwork's intrinsic size, with an explicit gap before the heading and separate spacing for the description and starter cards. Fixed mobile profile action clipping by wrapping actions with 12px gaps and at least 44px height. Restored spacing overridden by page resets in Breakdown explanations and Live Companion copy; separated Match Centre editorial actions and the full-match language control from adjacent sections.

```sh
npm --prefix frontend run build
npm --prefix frontend test -- --reporter=dot
NODE_PATH=/Users/haydn/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules node scripts/test_spacing.cjs
NODE_PATH=/Users/haydn/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules node scripts/test_unified_layout.cjs
```

```text
✓ 302 modules transformed.
✓ built in 817ms
Test Files  29 passed (29)
     Tests  172 passed (172)
PASS all 13 page layouts: no horizontal overflow, clipped controls or duplicate headers; mascot separation and profile actions verified. No AI calls.
```

The spacing audit covers Footie, Matchday Watch/Breakdown, Match Centre, Clubhouse directory/player/club/following/comparison, Tools, Studio's signed-out entry, Evidence desk and full-match replay at 1440, 768, 390 and 360 CSS pixels. It checks clipped controls even below the viewport, visible header count, mascot/title separation, commentary/control separation, phase explanation spacing and non-overlapping profile actions. Deliberate scroll containers remain scrollable. Screenshots and results are under ignored `var/spacing-validation/`; the affected desktop/mobile views were visually inspected.

The existing unified-layout journey also passed again: exact replay/player state, instrumented audio continuity, Chinese comparisons, filters, Footie drawer return, error/empty recovery and reduced motion. Authenticated Studio editing and every possible dynamic content combination were not part of this spacing audit. The changes remain local and unpublished.

## Footie logo header preview — 21 October 2026

Placed the approved concept C in the shared local header with the accessible home-link name **Footie home**. The built-in image-generation tool removed the cream backdrop; the resulting PNG is framed by an SVG viewport without changing the wordmark. This is a raster preview, not vector lettering. The asset and exact generation prompt are in `frontend/src/assets/brand/footie-wordmark-forest-v1.{png,json}`.

At 176px desktop width, 144px phone width and 128px on screens at most 350px wide, the football remains visibly distinct. The home link retains at least 44px height. A narrow-screen adjustment keeps Tools and Language on the same header row at 320px.

```sh
npm --prefix frontend run build
npm --prefix frontend test -- --reporter=dot
NODE_PATH=/Users/haydn/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules node scripts/test_footie_brand.cjs
NODE_PATH=/Users/haydn/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules node scripts/test_spacing.cjs
```

```text
✓ built in 824ms
Test Files  29 passed (29)
     Tests  172 passed (172)
PASS Footie header: 4 workspaces × 7 widths (320–1440px); 44px home target, keyboard home link, aligned Tools, visible navigation and no overflow.
PASS all 13 page layouts: no horizontal overflow, clipped controls or duplicate headers; mascot separation and profile actions verified. No AI calls.
```

Desktop, 390px and 320px rendered headers were visually inspected. Header screenshots and measurements are in ignored `var/logo-validation/`. No publishing or full project/infrastructure rename was performed; historical documentation and secondary CounterPress copy remain for a later naming pass. The logo image generation is separate from the browser checks, which submit no assistant questions.
