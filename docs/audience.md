# Audience preferences and languages — Stage 7

The same eligible insight now has analyst and casual views in English and
Simplified Chinese. Preferences change presentation and priority; authoritative
match state, counts, time windows, event identities and revisions remain separate.
This stage uses approved bilingual templates and makes no model requests.

## Try it

Start the API and frontend using the [README](../README.md), then choose **Go to
comparison**. Use the preference controls above the scoreboard:

1. **Analyst** shows the pitch, raw counts, windows, supporting sample size,
   segment metrics and sequences around qualifying recoveries. Evidence expands
   into exact event records and revisions.
2. **Casual** shows one count graphic and a short explanation. Detailed evidence
   remains available on demand; the pitch, sequence and metrics are initially hidden.
3. **Language → 简体中文** switches narrative and main interface labels. The
   registered names `Eastbridge` and `Northport`, player IDs, numeric facts and
   clock values are preserved.
4. **Player contribution → eb09** selects `p064`, its pitch marker and surrounding
   events `p063`–`p065`. The team comparison remains 1 versus 4. The display says
   that one of five supporting events is selected. **eb04** produces the honest
   no-qualifying-contribution state, even though that player appears elsewhere in
   the match records.
5. **Card budget → 0** hides the insight card. A budget of 1 permits at most the
   single eligible comparison. Preferences cannot create a card for the control
   scenario, incomplete windows or a withdrawn comparison.
6. **Local viewer** switches between two independent in-memory preference
   profiles. Viewer 1 starts in analyst mode; Viewer 2 starts in casual mode.
   These are local demonstration profiles, not accounts. Reloading resets them.

Club and metric preferences rank eligible candidates. Stage 7 originally offered
only a recovery-count story. Stage 8 now adds pressure exposure and pressured
escape with [shared ranking and card-budget selection](pressure-publication.md).
Changing preferences cannot manufacture an eligible story.
The priority starts at 10, adds 20 for the subject club and 30 for a selected
qualifying player, and adds 10 for recovery focus or subtracts 5 for passing focus.
The display budget remains zero or one card across all eligible metrics.

Player contribution means the recorded actor of a qualifying recovery. A nearby
pass or duel provides sequence context; it does not confer credit for the recovery.
The fixture provides player IDs, not personal names, so the interface uses those
IDs without inventing names.

## Facts, language and uncertainty

Variants are rendered only from an eligible, validated `Insight`. Narrative text
is separate from the existing `Insight.facts` and `EvidencePacket`. The count
graphic reads authoritative numeric fields. The source-record panel still exposes
the original machine-readable JSON; schema keys are not translated.

| English term | Simplified Chinese | Meaning here |
| --- | --- | --- |
| High recovery | 前场夺回球权 | Established open-play control at x ≥ 70 m in the actor team's attacking direction |
| Open play | 运动战 | Excludes restarts |
| Duel | 争抢 | Not itself a controlled recovery |
| Attacking third | 进攻三区 | Final 35 m of the normalized 105 m pitch |
| Supporting sample | 支持样本 | Qualifying event counts, not rate denominators or independent trials |

Both languages state that recorded recovery counts do not establish whether
pressure was effective. Analyst text additionally states the threshold and
duel/restart exclusions. Both retain `(48:00,53:00]` and `(53:00,58:00]` boundaries.
Desktop browser review checked Chinese football terms against these definitions,
numeric/window agreement and line wrapping.

The earlier Azure workflow remains available and audited. Its general-English
adaptation field is retained in the API, but it does not have an audience/language
identity. Audience views therefore use their validated bilingual templates rather
than translating arbitrary model text or making a new request per viewer.

## API and cache

The snapshot endpoint accepts these query parameters in addition to `at_ms` and
`scope_id`:

| Parameter | Allowed values / default |
| --- | --- |
| `language` | `en` (default), `zh-Hans` |
| `depth` | `analyst` (default), `casual` |
| `club_id` | Registered team ID; omitted means any |
| `player_id` | Registered player ID; omitted means all contributors |
| `metric_focus` | `balanced` (default), `high_recoveries`, `passing`, `pressure_exposure`, `pressured_escape`, `possession_without_progression` |
| `card_budget` | 0 or 1 (default) |

Unknown IDs or unsupported values return 422. Responses contain the registered
`teams` and an `audience` object with the echoed preferences, eligibility/display
state, narrative variant, supporting/selected event counts, highlighted source
references and, for analysts, canonical sequence context. Existing authoritative
snapshot fields are unchanged. Responses remain `Cache-Control: no-store`.

An example request:

```sh
curl -sS 'http://127.0.0.1:8000/api/scenarios/increase/snapshot?at_ms=780000&scope_id=viewer-one&language=zh-Hans&depth=casual&player_id=eb09'
```

The process-local LRU cache stores at most 128 immutable narrative variants. Its
key is `(insight_id, revision, language, depth, club_id, player_id)`. It contains
no viewer IDs, playheads, sequence state or shared preferences. Metric focus and
card budget affect selection/priority, not narrative content, so they do not
duplicate cached text. A process restart safely recreates variants on demand.

Local correction ingestion invalidates old variants immediately. Other service
instances reconcile against their freshly read history on the next snapshot.
Revision tracking is monotonic: an older in-flight read cannot repopulate a
superseded revision. Historical playback can still render historically valid
facts, but those old variants do not re-enter the current cache. Sequence context
is rebuilt from canonical records available at the requested cutoff.

Every preference, viewer or seek change creates a new browser playback scope and
clears the previous display. The client validates the echoed preferences and
variant identity as well as scope, scenario, cutoff and lifecycle revision.
Delayed responses cannot substitute another viewer's language or perspective.

## Verification

Backend tests cover identical facts across both languages and depths, actual
player contributions, honest empty states, priority/budget behavior, invalid
preferences, reusable bounded caching, correction/withdrawal invalidation and
historical replay. UI tests cover mode/language switching, selected evidence,
empty/budget states, independent viewer preferences, delayed-response rejection
and API perspective validation.

All 177 backend tests and 16 frontend tests pass; the production build passes.
Exact commands and output are recorded in [progress](progress.md). Browser captures:

- [English analyst view](screenshots/audience-analyst-en.png)
- [Simplified Chinese casual view](screenshots/audience-casual-zh.png)

No Azure calls, new cloud resources, procedural generator or additional detector
were added in this stage. Next: the Stage 8 seeded procedural generator with
held-out matches and explicit no-change/successful/unsuccessful-pressure controls.
