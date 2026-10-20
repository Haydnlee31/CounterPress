# Unified CounterPress experience

The current local revision has four main destinations: **Matchday**, **Match Centre**, **Clubhouse** and **Footie**. Tools remains a secondary menu. Preview: `http://127.0.0.1:8017/?story=last-gasp#matchday`. This revision has not been published.

## Fan journey

1. Watch a highlight in Matchday. Its title, description, compact scoreboard and replay are together.
2. Switch to **Breakdown** below the score for build-up phases, player involvement, passing routes, phase comparisons and the action timeline.
3. Switch back to **Watch** at any point. Both views share the same mounted pitch, audio track, exact playback position and player selection. Comparison choices and route visibility also survive the switch.
4. Choose another play from **More highlights** below the replay. A different highlight starts a new replay and clears its analysis selection.
5. Open **Match Centre** for whole-match comparisons, goals, moments, the shot map and club/player/half filters. The match library and full-match archive remain here.
6. Use **Clubhouse** for player/club careers, follows and comparisons. Ask **Footie** from a profile or supported match moment to retain that subject, season or exact event context.

## Shared presentation

Cream surfaces, forest-green text, sage borders and restrained gold accents follow Clubhouse and Footie. Club preferences affect accents, crests and player markers rather than whole-page backgrounds or text contrast. Pitch team colours remain distinct. Matchday and Match Centre use matching underline view controls. Match Centre gives more space to statistics and a smaller editorial summary; on narrow screens the comparisons appear first. Standalone Footie's welcome area is shorter; the embedded drawer retains its own layout.

## Interaction details

- `#matchday/breakdown` is the new analysis URL. Existing `#explore` links still open Breakdown with their selected `story`. Invalid story IDs fall back through the existing scenario validation.
- Watch/Breakdown are hash links and support browser back/forward. No second snapshot subscriber or narration player is created by switching views.
- The analysis explanations still require the authored event IDs and revisions. The data and analytical rules have not changed.
- All 22 pitch players remain present. Larger touch targets now sit behind visible markers; invisible halos/shadows cannot intercept another player's marker.
- Match library and Tools support outside-click dismissal and Escape with focus restoration. Full-match filters and selection retain their existing session storage.
- Club/language preferences, English/Chinese highlight content, reduced-motion behavior and exact-context Footie handoffs remain supported. Match Centre content is still English.
- Tools, authentication and publishing semantics are unchanged. Legacy evidence analysis is accessible through **Tools → Evidence desk**.

## Validation

See [the local validation record](verification/layout-refresh.md) for commands, results and limits. Screenshots and machine-readable browser results are stored under ignored `var/layout-validation/`. No backend, data, authentication, cloud resources or model configuration changed.
