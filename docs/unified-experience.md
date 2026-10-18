# Unified CounterPress experience

The local build connects Matchday, Explore Data, GI, Studio and advanced analysis through the same app header and match library. Open `http://127.0.0.1:8010/#matchday`.

## Fan journey

1. Watch a highlight in Matchday.
2. Choose **Explore this highlight** or **Explore data**. The selected story stays the same.
3. Open **Match library** to browse the three highlights or the separate full-match archive.
4. In GI, select a club/player/half and explore a shot or action. Return later in the same browser tab: the filters, selected event and pitch mode are restored.
5. Choose a supported club in Matchday preferences. Its colours carry across Matchday, Explore and GI.

The header's Tools menu leads to Producer Studio and advanced analysis from every workspace. Studio authentication, approval and publishing semantics are unchanged. GI records and illustrative highlight reconstructions remain separate sources; sharing the same fictional clubs does not make them the same match or player record. The library labels highlights and full-match archive separately.

## Interaction details

- One brand header, active workspace indicator, consistent context strip, and shared responsive typography/menus.
- Match library and Tools use native keyboard-accessible disclosure elements, close on selection/outside pointer action, and support Escape with focus restoration.
- Highlight links retain the validated `story` query parameter. Invalid stories fall back to the featured highlight.
- GI state is stored only in sessionStorage under `counterpress.gi.workspace.v1`; it has no credentials, tokens or personal data. Invalid state falls back safely; blocked storage does not block browsing. Returning to a highlight does not apply GI's source-specific player filters there.
- Matchday's existing club/language preference storage is reused. GI still has English content; the existing bilingual highlight views are preserved.
- Workspace navigation returns to the top; in-page skip links retain their behavior. Reduced-motion preferences are honored.
- The advanced analysis view hides its old duplicate brand header when embedded in the app. Its standalone component remains available to existing tests.

## Validation and delivery

`npm --prefix frontend test` passed 97 tests. `npm --prefix frontend run build` passed. Real-API browser checks cover highlight continuity, GI state restoration, library navigation, Studio/advanced entry points, saved Northport styling and 1440/390/360px layouts. Existing GI and Explore browser suites also pass. Exact commands and outputs are in `verification/unified-experience-local.json`.

This is a local UI integration, not a cloud release. No backend, authentication, source-data or paid-service behavior was changed by this integration. Precise video synchronization, uploads and GI's future production event storage remain separate work.
