# Fan feedback implementation — 21 October 2026

Local review build; not pushed or deployed. Existing unrelated working changes
have been preserved.

## Try it

Start the frontend build and API:

```sh
npm --prefix frontend run build
.venv/bin/python scripts/run_footie_local.py --port 8019 --commentary-dir var/commentary --voice natural
```

The commentary directory contains locally prepared recordings, not credentials.
On a fresh checkout without these recordings, omit both commentary arguments.
Preparation is a separate, explicitly metered Azure operation; playback never
synthesizes a recording.

- `http://127.0.0.1:8019/#gi`: select a match, then **Moments** or **Watch full match**.
  Faces/Initials and 0.5×/1×/1.5×/2× controls sit above the pitch.
  **Auto-play next sequence** continues through the current moment filters.
- `http://127.0.0.1:8019/#football/standings`: select a season; club links open
  profiles. On phones, **Show all columns** expands the compact league table.
- `http://127.0.0.1:8019/?story=last-gasp#matchday`: choose **Listen**, wait for
  commentary readiness, then **Play highlight** to try the original accent with softer delivery.

## Behavior and design

**Portraits:** reuse the 44 existing fictional portraits with tight circular
face crops, team-colour rings, active-player emphasis and existing name
tooltips. A persistent Faces/Initials preference works across pitches. Unmapped
or failed portraits fall back to initials. Match Centre maps archive identities
through explicit aliases. The ball remains above portrait markers. Phone
Match Centre pitches rotate vertically while portraits remain upright.

**Standings:** use the existing authoritative season ledger: 12 clubs, seven
selectable seasons, league fixtures only. Cup and showcase results do not
inflate league points. Wins earn three points, draws one; sorting uses points,
goal difference and goals scored, followed by stable club ID for equal records.
Featured clubs get compact position cards. The phone table keeps position,
club, played, goal difference and points visible; the expanded table also shows
wins, draws, losses and goals for/against. Current data ends 19 October 2026.

**Playback:** full-match mode continuously replays the available positioned
actions across both halves; breaks between actions are compressed. It is an
event reconstruction, not an uploaded 90-minute video or continuous optical
tracking. Original match clocks and scores follow the active event. Manual
seeking pauses. Individual sequences auto-advance only after their outcome
finishes; previously watched build-up is excluded on automatic continuation.
Speed persists across sequence remounts. Pausing or seeking to the end does
not unexpectedly advance. Opening Footie pauses replay. Full matches do not
request narration.

Fixed a replay grouping defect: identical timestamps in separate periods or
nonadjacent groups no longer merge. Full-match motion anchors are cached for
the stable timeline, avoiding whole-match reconstruction every animation frame.

**Cards:** consume recorded yellow, red and second-yellow tags, deduplicate
revisions, and respect revision availability at playback cutoff. Bookings link
to their moment; booked players carry pitch indicators and sent-off players
leave the pitch. Two yellows imply dismissal. Archive matches currently contain
three and one yellow cards respectively; dismissal paths use authored tests.
The synthetic match has no card coverage, so it displays unavailable counts,
not zero. No season accumulation or suspension length is invented: future
suspensions require recorded competition decisions.

Tag meanings follow [Wyscout's event documentation](https://support.wyscout.com/matches-wyid-events).
The two-caution dismissal rule follows [IFAB Law 12](https://www.theifab.com/laws/latest/fouls-and-misconduct/).
Actual suspension lengths depend on competition rules and decisions; the
fictional league does not inherit Premier League sanctions.

**Voice:** a local English comparison uses Azure `en-GB-RyanNeural`, with `chat`
and `cheerful` styles supported in the [official voice/style list](https://learn.microsoft.com/en-us/azure/ai-services/speech-service/language-support?tabs=tts).
Whole authored phrases and real speech bookmarks remain intact. Existing
Mandarin recordings are unchanged. The production default is unchanged until
the comparison is accepted. Six Azure Speech F0 syntheses reserved **1,463
characters** through the existing persistent quota ledger. No AI model calls,
new infrastructure or publication occurred for this feedback work.

A browser test initially caught a 1,625 ms first-play delay. Audio preparation
now waits for the recording to buffer before exposing ready playback, with
abort/error cleanup and a timeout. All six English recordings then started
within 12–15 ms in the local test. This is a measured local result, not an
internet latency guarantee or a subjective claim about voice quality.

## Verification

Commands run from the repository root:

```text
.venv/bin/pytest -q
892 passed, 1 warning in 147.02s

npm --prefix frontend test -- --run
Test Files  34 passed (34)
Tests       191 passed (191)
Duration    9.38s

npm --prefix frontend run build
✓ 312 modules transformed.
✓ built in 869ms
```

The backend warning is the existing experimental evaluator warning.
Tests cover portrait fallback, standings season replacement, event grouping
across halves, sequence completion, seeking, future-score isolation, 2×
persistence, card corrections/dismissals, buffering and audio cancellation.

Browser prerequisites: Playwright and Chrome. This workstation used:

```sh
export NODE_PATH=/Users/haydn/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules
export CHROME_EXECUTABLE='/Applications/Google Chrome.app/Contents/MacOS/Google Chrome'
node scripts/test_fan_feedback.cjs http://127.0.0.1:8019
node scripts/test_full_match_replays.cjs http://127.0.0.1:8019
LANGUAGES=en SPEED=2 node scripts/test_highlight_sync.cjs http://127.0.0.1:8019
node scripts/test_highlight_controls.cjs http://127.0.0.1:8019
```

Run audio journeys sequentially so another browser cannot take audio focus.
The checks use prepared local recordings and make no Azure requests.

Observed results:

- 22 face markers, three recorded bookings, automatic next sequence, retained
  2× speed, Faces/Initials switching, 12 standings rows and season switching.
- All three full-match final scores: **4–2, 3–2, 2–2**. Phone pitch orientation,
  visible points column, expanded-column control and no page overflow pass.
- Desktop 1440px and phone 390px screenshots reviewed; highlight controls also
  pass at 360, 390 and 760px. No browser JavaScript errors.
- Six English highlights at 2×: one start each, natural audio end, zero cuts,
  pitch preserved, every phrase bookmark synchronized within the test's 180 ms
  tolerance. Measured starts: **12, 15, 15, 15, 15, 14 ms**.
- Pause/resume, external audio pause, seek, speed, restart, reduced motion,
  preparation failure and absence of full-match speech requests pass.

Local screenshots and machine-readable results are in ignored
`var/fan-feedback/`. Credentials, recordings and private Azure diagnostics are
not added to the repository. Next: user reviews portraits, automatic replay and
the voice comparison, then publish the accepted version through existing gates.

## Voice preference correction

The user chose to keep the original accent and reduce robotic delivery. The
active local profile is now `natural`: the same `en-US-GuyNeural` voice,
`friendly` build-up at style degree 1.0, and restrained `excited` delivery at
0.8 for shots. Script text, punctuation, grounded action positions and Mandarin
remain unchanged. The earlier British audition is retained only as a separate
cache variant. Production remains unchanged pending publication.

Six profile regression cases verify the original voice, cache separation,
identical evidence/bookmarks and unchanged Mandarin. Targeted narrative tests:
`27 passed in 0.32s`. The updated profile uses styles listed in
[Microsoft's voice support documentation](https://learn.microsoft.com/azure/cognitive-services/speech-service/language-support?tabs=tts).

Original-accent browser rerun passed for all six highlights at 2×: starts
14/15/14/15/15/16 ms, one continuous recording each, every phrase bookmark
observed, natural ends, no cuts and preserved pitch. The six additional F0
syntheses reserved 1,463 characters (2,926 across both audition rounds).
The active local preview is the original-accent `natural` profile.

## Control placement refinement — 21 October 2026

User review identified controls and booking chips touching the Match Centre
widget edges and competing with the pitch. Replaced the above-pitch option
strip and full-width autoplay row with one inset player dock below the field.
Playback/seek is primary; speed, Display and a compact Auto-play switch form
its secondary row. Faces/Initials lives inside a native keyboard-accessible
Display disclosure. Bookings expand from a quiet summary, while player card
indicators remain on the field. Removed the redundant normal-play instruction.
The main match timeline and previous/next actions retain their existing role.

The selected-play widget uses 32px side gutters on desktop and 20–24px on
smaller screens. Full-match controls respect the parent's padding. Mobile
playback gives the seek bar its own row; speed, Display and Auto-play fit on
one row at 360px. Settings expand in normal flow, so no floating menu can be
clipped by the rounded widget. Shared Display styling also applies to Matchday
and Clubhouse replay. Clubhouse puts secondary settings below play/seek.
Matchday commentary actions now have an explicit inset too.

Actual screenshot iteration caught an inherited summary rule inflating the
menus and an orphaned phone Auto-play row; both were corrected before the final
checks. No data, voice recordings, cloud configuration or backend changes were
needed for this layout refinement.

```sh
npm --prefix frontend test -- --run
npm --prefix frontend run build
node scripts/test_replay_layout.cjs http://127.0.0.1:8019
node scripts/test_spacing.cjs http://127.0.0.1:8019
node scripts/test_fan_feedback.cjs http://127.0.0.1:8019
```

Use the NODE_PATH/CHROME_EXECUTABLE prerequisites above on this workstation.
The dedicated layout test covers Match Centre moments/full replay, Matchday and
Clubhouse highlight dialogs at 1440/1024/800/390/360px: inset controls, no page
overflow, Display/portrait selection, booking disclosure, Auto-play toggle and
2× selection. The existing spacing audit covers 13 pages at four widths (52
page/viewport combinations). Browser errors: none. Screenshots/results are
in ignored `var/replay-layout/` and `var/spacing-validation/`. Build: 312 modules,
939ms. No cloud calls, push or deployment; preview remains on port 8019.

Final interaction results: 191 frontend tests passed (34 files, 16.32s).
Browser regression confirmed 22 portraits, automatic next sequence, retained
2× speed, correct full-match score, standings and season switching. No browser
errors. `git diff --check` passed.

## Player hover cards — 21 October 2026

Added a shared, pointer-anchored player card to Matchday, Match Centre moments,
full-match replay and Clubhouse highlight dialogs. It shows the existing
portrait, full name, registered position group and shirt number. Works for both
portrait and initials markers. Existing player selection/follow controls remain.

Metadata comes from the featured-player registry (one shared request, not one
per pointer movement); Clubhouse reuses its loaded player records. Archive
identities resolve through the existing alias mapping. Unmapped substitutes
retain their display name and unavailable fields; no shirt or role is inferred
from a provider ID. These are roster positions, not inferred tactical roles.

Cards have a 12px viewport safety margin and flip left/up near edges. Rendering
outside the clipped pitch keeps them visible, while modal replays render the
card inside the dialog's top layer. Pointer users can move into the card without
it disappearing. Keyboard focus opens it; Escape dismisses only the card.
Touch users tap a player, then tap elsewhere to dismiss. Scroll/resize also
clears it. The card does not add a button or shift the pitch/control layout.

Validation:

```text
npm --prefix frontend test -- --run
35 test files passed; 196 tests passed; 9.41s

npm --prefix frontend run build
314 modules transformed; built in 838ms

node scripts/test_player_peek.cjs http://127.0.0.1:8019
PASS: Matchday, moments, full-match, Clubhouse hover/keyboard/initials/metadata
PASS: phone touch and outside dismissal; no browser errors
```

Use the browser environment variables documented above. Regression cases cover
viewport flipping, unavailable substitute metadata, keyboard dismissal, outside
interaction and moving into the card. Real-browser testing caught and corrected
Escape also closing the modal replay. Desktop and phone screenshots reviewed in
ignored `var/player-peek/`. No backend changes, model calls, speech calls or
publication. Local preview remains on port 8019.

## Stable player inspection — 21 October 2026

Following feedback about clicking moving players, pitch markers are now
presentation-only while playback runs. Pause first to inspect/select a player.
Moving markers are excluded from pointer hit testing and the tab order; the
shared card also rejects focus-driven opening while disabled. Matchday's larger
invisible hit targets and Clubhouse's selection handlers follow the same rule.
Resuming or changing the paused frame clears the card immediately. No extra
mode toggle was added. Coaching annotations are deferred.

Removed the inherited blue SVG focus outline and retained a 2px non-scaling
portrait border for keyboard focus. Regression checks verify no oversized outline
and stable marker bounds while the card is open on a paused frame.

Verification: `npm --prefix frontend test -- --run` — 197 tests in 35 files,
7.95s; `npm --prefix frontend run build` — 314 modules, 1.28s.
`node scripts/test_player_peek.cjs http://127.0.0.1:8019` passes all four replay
surfaces, paused-only inspection, resuming, pointer/tab exclusion, stationary
marker bounds, keyboard outline, metadata and phone dismissal. No browser
errors. `git diff --check` passes. Local only; no cloud calls or deployment.

## Corrected interaction: live hover, no pitch selection

The user's clarification supersedes the paused-only behavior above. Hover cards
remain available throughout playback. Pitch markers are now informational groups,
not buttons: click/Enter does not select a player, change focus preferences or
pause the replay. Mouse pointer-down does not focus the SVG, preventing the
unwanted click ring. Keyboard focus still exposes accessible details, and touch
uses the card as a hover equivalent without selecting a player. Existing player
lists and the Clubhouse focus selector remain the explicit selection controls;
Breakdown instructions and regression tests now reflect this.

The card checks the marker under a stationary pointer during animation, so it
dismisses if that marker moves away. Keyboard/touch cards follow their marker's
current bounds. Cards stay hoverable and Escape-dismissable. No layout, model,
recording or cloud changes. Local preview remains on port 8019.

Corrected behavior verified: 198 frontend tests pass (35 files, 7.26s); build
passes (314 modules, 864ms). Real-browser regression passes live hover and inert
clicks on all four replay surfaces, keyboard/initials metadata, viewport bounds,
modal Escape handling and phone dismissal. No browser errors. No publication.

### Match Centre statistics and nearby-play layout — 21 October 2026

Replaced the unequal lower columns with a compact four-metric summary and a full-width chronological sequence. The old context list's 255px scroll cap hid later events while the taller statistics column left blank space underneath. Nearby events now have natural height, a selected-play marker, aligned desktop cards, and compact mobile timeline rows. Statistics retain their filter navigation; nearby events still open the corresponding play. No data, playback or model behavior changed.

Validation:
- `npm --prefix frontend test -- --run`: 35 files passed; 198 tests passed (8.33s).
- `npm --prefix frontend run build`: 314 modules transformed; production build passed (849ms final build).
- `NODE_PATH=/Users/haydn/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules CHROME_EXECUTABLE='/Applications/Google Chrome.app/Contents/MacOS/Google Chrome' node scripts/test_moment_context_layout.cjs http://127.0.0.1:8019`
  - Output: `PASS: 15 responsive sparse/dense context checks; statistic filters and event navigation at 5 widths; no clipping, hidden events or browser errors.`
  - Widths: 1440, 1024, 768, 390, 360px; screenshot scenario at 46:55, opening event, and densest context window. Verified this area is hidden in Overview.
- Inspected desktop and mobile screenshots in `var/moment-context-layout/`; tightened mobile cards into timeline rows after the first visual pass.
- `git diff --check`: passed.

Local preview only; not published.

### Follow-up — restore editorial columns and use action-panel space

User preferred the original two-column design. Supersedes the stacked layout above: restored the serif Shots & passes heading, kickers and simple lists, with shared CSS grid rows aligning both headings, scope labels and list starts. Context rows and statistics rows are 76px; nearby events remain available in a scrollable four-row area. On mobile the sections stack. Removed the bookings/send-offs board from Overview; in-play card indicators remain.

The desktop action list now fills the adjacent replay's available height, replacing its former 410px cap. Size containment prevents loaded actions from stretching the replay, and Show more remains at the panel bottom. Mobile keeps an independently bounded list.

Verification:
- `npm --prefix frontend test -- --run`: 35 files, 198 tests passed (8.64s).
- `npm --prefix frontend run build`: passed, 314 modules, 818ms.
- Same `scripts/test_moment_context_layout.cjs` command as above: 15 scenarios at 1440/1024/768/390/360px passed. Assertions now cover parallel heading/list baselines, no blank desktop panel footer, loading 40 additional actions without stretching the panel, reaching the last loaded action, stat filters, event navigation, overview board removal, and no overflow/browser errors.
- Desktop/workspace/mobile screenshots inspected; corrected missing whitespace in the mobile heading.
- `git diff --check`: passed. Local only, not published.

### Replay movement and lineup continuity — 21 October 2026

Local correction following a ten-minute baseline playback review. The baseline
captured a roughly 41 m/s player movement in the 17:58 own goal, a ball jump over
400 m/s between actions, duel contestants following a long ball, and a goalkeeper
being replaced by an involved substitute and subsequently returning.

**Data and implementation**

- Added minimal, attributed starting XIs, broad roles and substitutions from the
  licensed [Wyscout match archive](https://doi.org/10.6084/m9.figshare.7770422) and
  [player archive](https://doi.org/10.6084/m9.figshare.7765196), CC BY 4.0. The
  extraction script records source hashes; fixture manifests verify lineup
  hashes. Substitution minutes are constrained by the last outgoing and first
  incoming player's events. These are estimated boundaries, not measured
  second-precise substitution times. Substitutes inherit stable formation slots.
- Preserved source event IDs, locations, outcomes, order, scores and match dates.
  Synthetic match rosters use their existing registered roles. Career statistics
  and the synthetic event generator are unchanged.
- Split replay into connected scenes. Restarts, missing travel and contradictory
  event locations use a 250ms fade out/in, rather than impossible pitch crossings.
  Connected player movement uses smooth paths through recorded actor contacts,
  with enough presentation time to reach them. Duels anchor contestants at the
  contest location; the ball endpoint is not treated as either player's run.
- Conservative animation limits: player peak speed 8 m/s, acceleration 5 m/s²,
  ball speed 32 m/s. These are engineering limits for presentation, not empirical
  estimates of particular players. Supporting motion uses broad role/home-shape
  priors and reachable targets. Goalkeepers react toward shots within the same
  movement envelope. Lofted passes have a height/shadow cue; provider shot
  endpoints are reconstructed from outcome categories rather than misreading
  provider goal-mouth coordinates as pitch coordinates.
- Goal outcome visibility, score changes, discipline cutoffs and Footie context
  now use each action's resolution time. Clubhouse shares the corrected motion
  engine. Matchday's separate highlight animation and prerecorded narration
  timing are unchanged. No new toggles or dashboard layout changes.

**Reproducible checks**

```sh
.venv/bin/python scripts/prepare_replay_lineups.py \
  --matches var/gi-research/wyscout/matches_World_Cup.json \
  --players var/personalization-source/players.json
node scripts/audit_replay_motion.cjs
npm --prefix frontend test -- --run
npm --prefix frontend run build
.venv/bin/pytest -q
```

The whole-match audit samples every 100ms of presentation time, checks lineup
size/keeper persistence and scores, and measures movement between connected
frames. Scene cuts are explicitly excluded from speed calculations: no travel
is claimed across missing intervals. Results in `var/replay-review/motion-audit.json`:

| Archive | Presentation minutes at 1× | Samples | Max player m/s | Max acceleration m/s² | Max ball m/s | Limit violations | Score |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| 2058017 | 42.819 | 25,692 | 8.000 | 4.944 | 30.814 | 0 | 4–2 |
| 2058007 | 52.401 | 31,441 | 8.000 | 4.899 | 31.066 | 0 | 3–2 |
| Synthetic | 41.997 | 25,199 | 8.000 | 4.834 | 30.868 | 0 | 2–2 |

Archive and replay tests cover source actors being on the pitch for every touch,
all recorded substitutions, integrity failure, backward seeking, duel anchoring,
carry/player continuity, deterministic seeking, goal/restart cuts, keeper
reaction, outcome visibility and completion callbacks. The editorial evaluation
lock was reviewed and versioned to `replay-lineup-continuity-v1`: only the new
lineup module and the two GI readers changed relative to the preceding lock;
frozen editorial cases, prompts and expected facts did not change.

Browser commands use the installed Playwright runtime and Chrome:

```sh
export NODE_PATH=/Users/haydn/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules
export CHROME_EXECUTABLE='/Applications/Google Chrome.app/Contents/MacOS/Google Chrome'
node scripts/test_replay_motion.cjs http://127.0.0.1:8019
node scripts/test_replay_layout.cjs http://127.0.0.1:8019
```

**Remaining limits**

This is an event-constrained reconstruction. The archive does not contain
continuous positions for all 22 players, exact body contacts, measured ball
height, or complete keeper trajectories. Formation spacing, supporting runs,
shot target points and save reactions remain estimates. Close player portraits
can overlap; this is not a collision-aware football physics or tactical
simulation. Recorded substitutions have minute-level precision. Stoppages are
compressed and presentation time is adjusted for plausible travel, so 1× is
animation speed, not the original match clock. The aggregate audit validates
configured constraints; it does not establish that unobserved trajectories
match the original footage.

[FIFA's physical-analysis method](https://www.fifatrainingcentre.com/en/fwc2022/physical-analysis/background-and-method.php)
uses 25Hz optical tracking. Comparable synchronized tracking, or calibrated and
validated video tracking, would be needed for faithful off-ball reconstruction.
[FIFA's position analysis](https://www.fifatrainingcentre.com/en/fwc2022/physical-analysis/how-do-various-positions-cover-distances.php)
informs the broad distinction between supporting movement and fast actions;
it is not a calibration dataset for the numeric limits above.

Local only: no deployment, new Azure resources, paid AI calls, or speech generation.

Final validation results:
- `npm --prefix frontend test -- --run`: **203 tests passed**, 35 files (9.68s).
- `npm --prefix frontend run build`: **passed**, 313 modules (903ms).
- `.venv/bin/pytest -q`: **902 passed**, one existing experimental-evaluator
  warning (155.59s). Initial three lock failures were resolved by the reviewed
  version update described above, followed by the complete suite rerun.
- Motion browser audit output: `PASS: 12 live motion scenarios across 3 matches,
  recorded substitutions, final scores, mobile bounds, and 90+ seconds
  uninterrupted 1x playback.` No page errors. Contact sheets reviewed for the
  own goal, aerial duel, other archive goal, synthetic carry and uninterrupted
  playback; phone screenshot reviewed. Artifacts: `var/replay-motion-browser/`.
- Existing responsive replay audit: **passed** at 1440, 1024, 800, 390 and 360px
  across Match Centre moments/full replay, Matchday and Clubhouse, including
  display settings, 2× controls, auto-play and inset content. No page errors.
- `git diff --check`: passed.
- `node scripts/test_player_peek.cjs http://127.0.0.1:8019`: **passed** on
  Matchday, Match Centre moments/full replay, Clubhouse and phone. Live hover,
  keyboard details, initials, inert clicks and dismissal remain intact; no page
  errors. Updated the test to await card dismissal rather than racing React's
  state commit. No hover-card implementation changes were required.
