# Analyst conversation and match reports

## Live conversation

The deployed live path uses the Container App scheduler described below. The separate [native Foundry path](analyst-foundry.md) has its own configuration and contracts.

`COUNTERPRESS_ANALYST_DISCUSSION=azure` runs the Footie live turn manager in the existing Container App. Each admitted source-minute selects **one relevant specialist** (Player, Match, Chance or Defensive), proposes two short alternative comments with the existing `gpt-5-mini` deployment, then independently selects or rejects the exact drafts with a second `gpt-5-mini` call (low reasoning). The reviewer cannot rewrite prose. At most one exact reviewed draft is published. This replaces the weaker writer after bounded tests exposed attribution errors. Footie checks the current, revision-pinned evidence packet; it does not use future match knowledge or assume career facts unavailable in that packet. Existing general Ask Footie remains unchanged.

The manager prioritizes unreported goals since the preceding accepted turn, including own goals recorded as `other` (and the opening shot), then rotates by recent attempted roles and eligible evidence, preventing accelerated replay from repeatedly selecting the same role when clock minutes are skipped. Quiet spells skip inference. Rejected attempts advance scheduling without supplying unpublished prose to later agents. Up to three earlier approved messages provide conversational context. A role receives a specific earlier peer claim and available source anchors to extend or qualify with new evidence; unrelated points remain standalone. Priority goals must be cited and cannot inherit an unrelated buildup. Canonical card events are currently unavailable and are not inferred; arbitrary browser-supplied chat is never accepted. Replies can build on, qualify or challenge a different colleague. The model writes prose directly; the legacy typed-fact sentence formatter is not used on this path.

Short, source-local citation aliases are constrained by the response schema, then resolved back to canonical IDs. Final gates check references, player attribution, reply eligibility, numbers and source freshness. Footie's independent semantic review handles attribution and implications; this reduces errors, not a guarantee of correctness. Pass attempts and completed passes are explicitly separate. Geometric xG remains in the statistics but is excluded from the live commentary packet because it is uncalibrated. Formatting cleanup removes citation-only brackets and duplicate completion annotations without adding facts.

Passages are built from the complete visible event stream before evidence shortlisting, never stitched from a sparse set of citations. At most three recent passages are retained in a snapshot; each model turn receives one role-relevant passage of at most seven actions. Explicit recipient/holder links are distinguished from team chronology. Opponent actions, source-order gaps, restarts, long gaps, unknown outcomes and recipient mismatches break links. Corrected/retracted/unavailable events are resolved before extraction. A still-developing passage remains `ongoing`, never a guessed finish. Actor/recipient names, clocks, pitch areas and ball direction are computed before inference; raw coordinates remain available in the UI evidence. This is event-supported on-ball analysis, not video tracking or inferred off-ball tactics.

Publication diagnostics record the scheduled role and a bounded decision code (published, repetitive, unsupported claim, abstained or validation failure). They do not publish rejected draft text or provider configuration. The exact-citation and temporal guards remain in place, and the new passage-to-window causal check rejects inferring that one move caused an aggregate statistical change.

Forward playback keeps a running turn, publishes it at its original source timestamp, then coalesces to the newest eligible minute. Pending results poll once per second. There is no backlog of every skipped event and no unreviewed token streaming. Pausing, hiding, seeking, changing match/preferences and source corrections retain the existing stale-result and cancellation protections. Approved history is scoped to match, preferences, correction generation and prompt manifest; rewinding cannot import a future contribution.

## Interface

- Two specialist desks on each side of the pitch at wide desktop sizes; a selectable desk on smaller screens. The desk pair stays together instead of stretching to the height of the central content.
- Player choices are grouped by team. Focus links the selected player's statistics, pitch ring/name, contextual activity map and model request.
- The latest comment is always first and outside any scrolling history. Earlier comments remain in a collapsed, independently scrollable history; new comments do not collapse the history while someone is reading it. Desktop crests and scores are enlarged, while mobile retains a compact horizontal score row.
- Core totals and a two-sided rolling momentum ribbon stay visible. Relevant shot/pass maps appear below the conversation; selecting a player shows their on-ball activity map. Full statistics remain available in each desk's dialog.
- Shot arrows connect recorded start/end coordinates only. Missing endpoints remain dots. The heatmap uses soft density cells; these remain recorded action locations, not continuous tracking.
- Context maps explicitly show the current statistics clock. A comment keeps its own earlier clock and expandable evidence, so current maps are not presented as its frozen evidence snapshot.


## Conclusion memory and usefulness checks

The live manager now retains the last 18 accepted conclusions within the existing
match/preferences/source-revision/model-version scope. A conclusion has a canonical
subject, a stable topic, a short reading, cited event identities, mechanism and
trend direction. Rejected drafts never become conversation memory. Retrieval
excludes future cutoffs, survives a process restart, and deduplicates the model's
brief by topic and subject. Recent comments remain available across natural
half-time; explicit seeks and preference changes still invalidate the visible room.

The independent editor must identify the prior conclusion it is developing and
state whether the contribution is a reversal, a new mechanism, or a new decisive
outcome. Server checks reject fabricated memory references, uncited subjects,
unchanged mechanisms, unsupported reversals and repeated outcomes. Cross-role
paraphrases of sterile circulation share the same club-level key; changing player
names, event IDs or counts does not make that lesson new. A changed score can
change its significance. This is an enforceable repetition gate alongside semantic
review, not a claim that model judgement is infallible.

Both author alternatives and independent review remain on the bounded mini-model
path, with no extra memory model call. Deeper reviewer reasoning was tried and
rejected because incomplete responses and extra latency harmed continuity. The
reviewer remains at low reasoning. Large requests compact memory field names,
omit notes for absent metrics, and roll off only older dialogue that is not a
proposed reply target. Evidence, candidate text and memory values are retained;
the actual transport still enforces the 6,000-token bound before any model call.
A worst-case 48-case matrix with 18 retained conclusions fit within 5,958 tokens.

Source-schema regression checks now also reject the observed unsupported
"liability" judgement from a single failed pass. Factual checks and usefulness
checks are distinct: a true statistic can still be an unhelpful repeated comment.

## Full-time report

Opening **Match summary** at full time starts analysis automatically. Identical completed reports are reused and pending requests join existing work. The report combines authoritative match totals, pitch zones (six lengthwise bands and three widthwise lanes), linked shot passages, team strengths and weaknesses, player contributions and proposed coaching exercises.

Model-authored interpretation is independently reviewed and validated against the source. Overview totals and player contribution paragraphs are projected from authoritative facts, including on cache reads. Suggested drills and explanations remain interpretations: event-only evidence cannot establish off-ball positioning, causation or a defender's general ability.

## Operational controls

Results and accounting use the existing Cosmos store in the hosted app; local preview uses SQLite. Requests are scoped to match, source revision, preferences and model/prompt version. The application defaults to `COUNTERPRESS_USAGE_CAPS=off` for judging. This removes cumulative application spending ceilings while preserving accounting, short request-rate limits, two concurrent jobs, bounded model turns, failure cooldowns and source validation. Azure provider quotas and subscription limits remain external constraints.

Shared cache hits reuse accepted output. A failed or unsupported draft is not presented as an active conversation. Source timestamps remain visible during accelerated playback, so an asynchronous finding is not misrepresented as instantaneous.

## Verification evidence

The recorded full 5× player-focused run published 16 comments, including six cross-role replies and citations for all four goals; nine repetitive conclusions were withheld. Median publication latency was 13.47 seconds and maximum latency 17.94 seconds. Two request-size failures discovered during that run were fixed and checked using captured-context live retries. These observations describe that acceptance run, not a guarantee for every match or concurrent load.

See the [dated acceptance history](verification/analyst-release-history.md) for results, failures and subsequent fixes. Deterministic/mock tests are separate from live model evidence. Use the [user walkthrough](demo-guide.md) to explore the current experience.
