# Analyst implementation and acceptance history

Historical checkpoints and test evidence. Earlier runtime descriptions and allowances are superseded by the [current conversation contract](../analyst-room.md). This is an audit record, not a setup guide.

# Analyst Mode — live desk, 27 October 2026

## Linked-passage implementation (local candidate)

This source revision is prepared for local review; the deployment record determines which revision is live.

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

## Cost and operational bounds

The two-call turn permits at most 6,000 locally estimated input tokens per request (including schema plus a 768-token framing reserve), 2,000 output/reasoning tokens for each of the draft and review calls. No automatic model retries. A conservative $1/M input and $4/M output assumption gives $0.028 per complete turn; **$0.03 is reserved before dispatch**. The shared durable allowance keeps a **$2.70 cumulative model-usage bound per physical match**, including failed/cancelled calls, across viewers, languages, focus choices and revisions. Shared deployment lifetime allowance is $12. This is a conservative model-use reservation, not an Azure invoice or a cap on shared hosting/storage charges. Existing total project budget remains $200.

The ledger uses the existing Cosmos container, partition `analyst-live-control-v1`; local preview uses the configured SQLite ledger path plus `.live`. It fails closed without durable admission. Completed results can be reused for up to 30 days; a bounded control-document size may evict older result payloads. Cumulative counters never expire or reset. Fully metered calls on the known `gpt-5-mini` pair settle at the conservative $1/$4 token rates, rounded **up** to whole cents (at least one cent per turn). Missing, partial, out-of-bound or unknown-model usage retains all three cents, as do failures/timeouts/cancellations without a complete result. The CAS transaction records the original reservation, accounted cents and an idempotent settlement marker; retained historical records with complete usage can settle once. Pruned/unknown historical calls remain fully charged. This releases unused reservation, not billed charges. Exact source/prompt/preference cache hits remain free; revised prompts and different replay cutoffs are new work. Changing view preferences can consume new turns, so the allowance does not promise 90 minutes of fresh commentary for every possible view. Cache misses after expiration/eviction remain subject to the same lifetime match limit.

The current source adapters cover the three registered library matches, both halves and all mapped players. Source coverage differs by match. Shared durable admission/cache helps repeated viewers; active tasks and cancellation remain process-local, with two concurrent jobs globally. This has not been load-tested as a many-match production broadcast service. Scaling beyond the pilot requires durable workers, cross-worker cancellation and per-tenant budget management.

Local startup below still applies. Both named deployments must exist on the configured Azure account. No new Azure resources, agent permissions or model deployments are provisioned by this change. The native Foundry roundtable path remains separate and unchanged; the live manager emits OpenTelemetry spans through the existing configured tracing setup. Do not describe the new live manager as a native Foundry or Agent Framework group-chat runtime.

## Validation

Focused regression checks cover reviewed publication, rejected edits, short citation resolution, attempt/completion separation, accelerated-turn fairness, quiet skips, durable spending across preferences/restarts, temporal history and recorded-only shot paths. Frontend tests cover successive live publication, fast-forward coalescing, team groups and accumulated conversation. Browser checks cover all three matches, focus propagation, statistics dialogs and desktop/tablet/mobile layouts. A 48-case real-snapshot matrix exercises both halves and player/team views using mock model transport, with no paid calls. Real Azure model and continuous 5× browser checks are reported separately in the task validation evidence; mock publication is never presented as live evidence.

## Earlier implementation and review history

The sections below describe earlier roundtable checkpoints and their historical test results, **not the current Azure live-manager limits or runtime**.

# Earlier Analyst room — 26 October 2026

## Hosted release input budget

The Azure discussion transport now checks the actual serialized HTTP request
before dispatch, including prompts, shared history and response schema. It uses
OpenAI's `o200k_base` tokenizer plus a 4,096-token framing allowance and rejects
estimates above 16,000. Tokenizer failures also prevent dispatch. This is a
conservative local gate, not a provider-guaranteed prompt limit; compare returned
per-role usage after live validation. The image preloads the checksum-verified
tokenizer data during its normal TLS-verified build, avoiding runtime downloads.
Five turns maximum, no transport retries, and completion caps of 2,200 per
specialist / 4,000 for Footie (including reasoning) remain unchanged. No model
authentication or Cosmos allowance changes accompany this guard.

The Analyst Mode redesign follows the user's pitch → conversation → specialist desks sketch. It replaces the visible candidate-reading panel with an actual, bounded multi-agent conversation. Match Centre and Highlights retain their separate purposes.

## Reference audit and design choice

Reference: [MatchMind live app](https://ca-matchmind-fh62l3n45y67i.wittyriver-305907d2.eastus2.azurecontainerapps.io), [MIT source repository](https://github.com/auroraeye-dev/matchmind).

Exercised the event replay, pause/restart, speed selection, live pitch, shot map, team/player heatmaps, player-follow camera, metric focus, audience and club controls, Spanish personalization, broadcast view, highlight replay/next/speed, timeline replay, tracking-feed mode, vision trace, and overlay-feed download. The downloaded feed contained timed overlay records. This covers the main feature families, not every seed, language combination, external MCP client or failure condition.

Its strengths are linked pitch/statistics views, personalized output and inspectable generation traces. Its source uses deterministic interpretation followed by model roles and rendering; it does not provide the shared specialist conversation requested here. A trace exposed a rejected invented quantity with rules fallback. Replay restart also displayed a stale Resume label while running. We use the interaction ideas, not copied source, graphics or prompt text.

Chosen framework: [Microsoft Agent Framework group chat](https://learn.microsoft.com/en-us/agent-framework/workflows/orchestrations/group-chat). [AG2 group chat](https://docs.ag2.ai/latest/docs/user-guide/advanced-concepts/groupchat/groupchat/) was considered. MAF fits the existing Azure implementation and offers explicit speaker selection, shared history and bounded turns. It is real shared-history execution, not independent answers styled as a chat.

## Experience

- Full-width replay with 1×, 2×, 5× and 10× controls; other replay surfaces retain their existing speeds.
- A shared conversation with named speakers, reply relationships, source clocks, expandable metric/play evidence and Footie's round-up.
- Four desks: Player Analyst (individual statistics/heatmap), Match Analyst (team statistics, rolling momentum and heatmap), Chance Analyst (shots, goals, chance estimates and shot map), Defensive Analyst (recoveries, duels, supported turnovers and saves).
- Full metric details remain accessible from each desk, including source coverage and unavailable measures.
- Two columns on desktop, one on mobile. Match selection, player focus, English/Chinese and detail preferences remain available.
- The fixed FULL TIME context bar is hidden on this replay page to avoid conflicting with the current match clock.

## Execution and source boundaries

Every discussion has one immutable revision-aware snapshot. Metrics update in 15-second match-clock buckets; model discussions use minute buckets. Replay rendering never invokes a model.

The bounded order is Match → Player → Chance → Defence → Footie. Specialists receive role-specific facts and prior peer messages. They can build on, qualify or challenge a colleague. Footie checks the source independently, edits fixable factual wording and reply links, and synthesizes accepted findings. Edited messages pass the direct citation/number checks again. Five model calls maximum, no autonomous tool writes, no open-ended debate. GPT-5 mini is the default for this room after local comparisons exposed weaker reasoning with GPT-4.1 mini. Specialists use minimal reasoning, the chair low reasoning. Existing Footie chat is unchanged.

Structured output, reference checks, numeric checks and an independent model review are separate gates. A rejected parent withdraws dependent replies unless the editor has supplied a source-supported, self-contained revision. These checks reduce errors; they do not prove every football interpretation true. Tests cover fabricated quantities, invalid citations, false doubling, rejected dependencies, safe editorial repairs, fabricated repair claims, provider failures, source corrections and temporal isolation.

A seek backwards, new match, period change, preference change or revision invalidates the previous viewing scope. An in-flight round is allowed to finish across forward time buckets, then catches up to the latest eligible bucket. Responses retain their source timestamp. Pausing stops automatic requests; Discuss this spell permits one explicit paused request. Browser hiding stops polling. Already admitted server work may finish and be cached.

Metrics are computed from available events, not the replay's illustrative off-ball animation. On-ball heatmaps are not continuous tracking. Event share is not possession time. Geometry-based chance estimates are uncalibrated; authored xG/speed preserve their provenance. Missing speed, tracking, pressure or other measures remain unavailable, not invented zeros.

## Run locally

```sh
uv sync
npm --prefix frontend ci
npm --prefix frontend run build
.venv/bin/python scripts/run_analyst_local.py --discussion --port 8020
```

Uses existing server-side Azure configuration, either injected environment variables or a local `.env` file. Set `AZURE_OPENAI_ENDPOINT` and `AZURE_OPENAI_DEPLOYMENT` for your existing deployment. An injected `AZURE_OPENAI_API_KEY` takes precedence over the optional secure-binding alias `COUNTERPRESS_MODEL_API_KEY`, which takes precedence over a local file value. Existing managed-identity environment configuration also works without a key or `.env` file. The launcher does not persist or print injected values. Never put credentials in frontend files. Start without `--discussion` for an offline preview; enabling discussion requires separately verified access and a monetary test budget. Open `http://127.0.0.1:8020/?match=synthetic-32fe41c5d304ce68d7d9#analyst` on the machine running the server.

Start replay, or seek past the first minute and press Discuss this spell. Evidence-based conversation is slower than the animation; at 10×, several match-clock buckets can pass during a round. Older discussions stay timestamped, not relabelled as current. No artificial typing dialogue is shown while the real review is pending.

The durable local allowance is `var/analyst-local-allowance.sqlite3`, shared with legacy Analyst Mode: $30 lifetime, conservative $0.10 reservation per round, 120/hour, 200/day and two concurrent rounds. Reservations are not Azure billing measurements. The project's $200 total ceiling is unchanged.

## Native Foundry path

The same MAF runtime is packaged into the hosted-agent ZIP, rather than maintained as a separate conversation implementation. Native prompt versions contain the free-prose specialist instructions and structured response schemas. The director invokes pinned versions and maintains shared conversation history. Existing stop/delete cleanup and one-run session permits remain in use.

Prepare an offline plan with:

```sh
.venv/bin/python scripts/configure_analyst_foundry.py --discussion
```

Provisioning requires the existing explicit `--apply --code --manifest ...` workflow; no native agent versions or application deployment were changed during this UI implementation. A *new verified* private activation file must include `"protocol": "roundtable-v2"`. Do not relabel the old candidate-agent manifest. `run_analyst_local.py --foundry-config ...` and `deploy_azure.py` route that verified protocol to the new discussion provider. Rollback disables discussion explicitly. The local Azure transport validates the interaction before native deployment; it is not a claim that the new native release is live.

## Verification

Frontend build, full frontend regression suite, Analyst/API/native adapter tests and existing assistant regressions were run. Actual Azure model rounds were inspected, including a stronger-model comparison. Browser checks include desktop and 390-pixel mobile width, playback speed, seeking, manual discussion, source evidence, player/club selection and detailed statistics. See the task response for final counts and remaining limits. This is development validation, not a blind accuracy benchmark or a guarantee of factual correctness.


## Cloud review checkpoint — 26 October 2026

The original local handoff was restored byte-for-byte at base `000e83b5330c655399d801d410d147a55a91d019`, including Highlights. This review keeps the replay → conversation → specialist desks layout.

- Statistics/configuration retries are separate from an explicit discussion request. Seeking evidence or the timeline pauses playback and creates a new viewing scope; late responses cannot populate that scope.
- Evidence buttons select an exact event ID and revision in the replay. Specialist cards label a finding's source clock and suppress prose more than three minutes behind current statistics. Timestamped conversation history remains available until a scope change.
- A viewing-session cancellation endpoint stops a running job in the current server process when its last interested viewer leaves. Other viewers retain their shared job. Cancellation stops subsequent Agent Framework turns; already sent model calls may still be billed. Reservations are never refunded. This is best effort within one process, not a distributed cancellation guarantee: another worker or a failed cancellation request may continue until the existing bounded timeout. The UI suppresses stale results independently.
- Roundtable v2 renders quantitative facts from typed metric references. Python owns actor labels, metric labels, quantities, units, source windows, differences and percentage-point changes. Previous/current comparisons require the same actor, metric, unit and basis. Raw numerals, spelled-out quantities and unsupported named subjects are rejected from model commentary. Source coverage and heuristic/authored provenance accompany rendered claims. This reduces numerical misattribution; free qualitative interpretation and event claims still require the editor and independent evaluation. It is not a guarantee of semantic accuracy.
- Native transport independently rebuilds rendered fact clauses from its own snapshot and rejects old protocol versions. Existing native agents must not be relabelled or activated as v2. New native activation and live model quality checks have not run.

The cloud preview runs without `--discussion` and without Azure configuration. It exposes real replay/statistics and prepared Highlights summaries; it does not fabricate agent conversations. Browser interaction tests may intercept discussion responses using clearly synthetic test fixtures. Those are UI tests, not live-model evidence.

At the original offline checkpoint, actual Azure usage, background resource costs and OpenAI credit balance were unavailable and no live model calls had run. The later bounded live check is described below. No paid resources, production deployment or merge were created. App admission counters are not monetary spending caps.

## Bounded live contract check

Runtime authentication and generation were subsequently verified with the existing Azure resource. A five-request acceptance allowance exposed format and citation failures; it did not complete a reviewed five-role conversation.

The fact renderer now treats each valid preceding placeholder as a complete sentence, allowing `[[fact:0]] [[fact:1]]` without extra punctuation. It still rejects absent/repeated markers, prose attached to placeholders, missing citations, incompatible windows and uncited subjects. Captured rejected model responses are regression fixtures, not accepted analyst findings.

Prompts and schema descriptions specify zero-based marker placement, current-to-previous comparison orientation, citations for both endpoints, and explicit team citations when a player specialist discusses a colleague's team reading. A pass count does not justify a tactical role or pass-length claim. Azure and prepared native discussion definitions now use bounded `medium` reasoning for GPT-5 specialists; completion caps remain 2,200 per specialist and 4,000 for Footie, including reasoning. Existing native versions were not activated or relabelled.

Those early diagnostic calls rejected unsupported prose and missing team citations; no invalid candidate was promoted to a validated finding. A later complete round passed the checks described below.

## Complete live round after deterministic fact layout

The generation contract now asks the model for typed facts and qualitative commentary without placeholders. Python inserts the fact sentence markers before the existing renderer and citation checks. It never invents IDs, fills missing citations, changes selected values, or repairs incompatible comparisons. Existing explicit markers are still validated strictly. Footie revisions follow the same normalization, and the published v2 `draft_text` retains the normalized representation for independent native validation.

One actual five-role Azure round completed on the synthetic match at H1 24:00 with Isaac Lane selected. All specialists received the preceding rendered conversation; the Player and Chance Analysts built on it, the Defensive Analyst qualified the control reading, and Footie synthesized the accepted contributions. Snapshot IDs, metric/actor/unit/window bindings and no-future-evidence checks passed. This was real model output, not the earlier authored UI fixtures.

The round took approximately 95 seconds. Footie accepted the contributions without an explicit revision, and the result used metric citations without event-specific citations. This verifies one snapshot and shared-history execution; it does not establish broad factual reliability, live evidence-button selection, native hosted deployment, or an observed editor correction. Accelerated playback can substantially outpace a reviewed round. A second complete player/snapshot case has not run.

## Compact room and citation publication

The wide layout places Player and Match Analysts left of the replay, Chance and
Defensive Analysts right, and the conversation directly below. Smaller screens
show one selectable specialist workspace. Maps expand on demand and full metric
boards open in a keyboard-accessible dialog without moving the replay clock.

Typed facts explicitly name their source metric IDs. The application now carries
those IDs into the citation index after checking that they exist in the role's
scoped snapshot. It never guesses missing IDs or repairs an invalid quantity,
comparison, subject, or free-text claim. Review decisions and revisions are
validated separately from Footie's synthesis: a faulty synthesis is withheld
without discarding independently accepted specialist messages. A faulty revision
or acceptance decision still blocks publication. Partial publication is labelled.

The same pipeline supports the three registered full-match fixtures; additional
matches require the event/roster adapter and library registration. Source coverage
varies. Event-location maps are not continuous off-ball tracking. Shared Cosmos
admission limits apply across viewers, while completed snapshot/preferences results
are reused. Active execution and cancellation are process-local, so this is not yet
a durable distributed worker system or a load-tested many-match live service.

## 27 October 2026: full 5x acceptance and release hold

The local Azure-backed acceptance replay completed the featured synthetic match
at 5x with Rory Ellis (`eb09`) selected. It published 29 comments, including 20
cross-role replies, with all four specialists represented. Fresh turn latency was
13.6 seconds median (18.1 maximum); 60 actual model calls consumed 217,668 input
and 34,193 output tokens. Conservative allowance settlement charged US$0.61 for
this run, not an Azure invoice amount. This was a functional full run, **not a
usefulness acceptance pass**.

Observed defects and corrections: natural half-time no longer clears discussion
history; priority goal turns cannot manufacture corrections to unrelated earlier
comments; reference-only `see e1–e7` annotations and ranges after factual text are
cleaned without deleting factual words; shot origin is distinct from ball
destination and the observed wrong-box claim is blocked; the observed inference
about attacking intent is rejected. Explicit seeks, rewinds and preference changes
still invalidate the visible discussion. The original full run plus bounded
follow-up segments used US$0.85 of the additionally approved US$1, retaining all
previous charges. Two candidates remain: the single-candidate experiment did not
materially improve successful-publication latency.

The final targeted live checks published 3/3 goal-segment turns and 5/6 half-time
turns, with every published comment retained in the browser. The intent guard was
added after those checks and verified offline. Repetition of the same
circulation-without-danger conclusion still survives semantic review. Do not
present those targeted checks as a new full-match pass or publish this increment
as an accepted improvement in conversation quality. Next work is explicit memory
of prior conclusions and a usefulness gate that requires a changed interpretation,
not simply new event IDs. Remaining latency needs separate evaluation; raising
allowance caps does not reduce model latency.

A two-minute observation of the public MatchMind app at its lowest selectable
20x speed measured 33 moment-linked overlays: 14 had an actual model stage in
their path (median 4.113 seconds, maximum 8.363); 19 were entirely rules-based
(median 0.002 seconds). Its 18 successful model-stage traces had median 2.085
seconds. These are different workloads and environments, not a controlled speed
benchmark. Classification uses the whole trace path because an overlay labelled
`rules` can still inherit model-written explanation upstream. Source inspection
shows minimal reasoning, compact moment packets, cached agents/shared clients,
importance filtering, bounded concurrency and rule fallbacks, with no equivalent
independent semantic editor. Useful inspiration is compact, event-triggered work
and separating instant statistics from reviewed prose; do not label rule output
as an AI conversation or remove grounding to match its timings.

Sources: https://github.com/auroraeye-dev/matchmind/blob/main/matchmind/llm/provider.py
and https://github.com/auroraeye-dev/matchmind/blob/main/matchmind/orchestrator.py .

The editorial pilot lock is versioned `v23-analyst-live-continuity` after reviewing
exactly the five changed analyst backend modules. Case data, expected results,
editorial prompts, evaluator and dependencies were not changed. The old lock's
three failing tests are not hidden or bypassed; the affected offline matrix and
analyst tests are rerun against the new source hashes.

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

An admin-only, idempotent allowance grant supports at most one additional dollar
per match after explicit approval. There is no public grant endpoint. It never
resets spent counters or raises the shared US$12 allowance. Grant IDs and reasons
are retained durably, and oversized optional history can be evicted without
removing spend records, grants, or the active conversation scope. The feature does
not grant production credit automatically.

The source lock is versioned `v24-analyst-conclusion-memory`; frozen cases,
expected results and evaluator logic remain unchanged. Targeted verification:
`PYTHONPATH=backend python -m pytest tests/test_editorial_evaluation.py tests/test_analyst_*.py -q`
returned 303 passed, 1 skipped. Live acceptance observations are recorded separately
from these deterministic tests.


The complete 5x player-focused replay then finished with 16 published comments,
six cross-role replies, all four roles represented, and all four goal events cited.
Nine repetitive conclusions were withheld (five deterministic memory decisions,
four semantic editorial decisions). The retained conversation stayed visible
across half-time; no browser errors occurred. Published-turn latency was 13.47s
median and 17.94s maximum. Two request-size failures found during the replay were
fixed with bounded context; captured-context live retries subsequently returned
one published comment and one correct repeated-conclusion rejection, without a
provider failure. The over-strong single-pass "liability" judgement seen during
the replay is now blocked by a regression check. These safeguards improve the
observed conversation; they do not promise that every football interpretation is
perfect or that every source minute warrants another message.

## Full-time match report

At the end of Analyst Mode's full replay, **Match summary** opens a visual report.
Opening it is free. **Approve deep analysis** explicitly starts a bounded report:
one gpt-5-mini author (up to 6,000 output tokens, medium reasoning) and an independent
reviewer/editor (up to 5,000 output tokens, low reasoning). Each request is guarded at
18,000 input tokens including a conservative framing margin. The durable ledger
reserves US$0.10 before either call, within the existing match and shared Analyst
allowances. This conservative accounting ceiling is not an Azure invoice. Failed
attempts remain charged. Same source revision, language, model and report version
reuse the saved result; changing a source invalidates it. No credit is granted or
budget increased by this feature.

The report calculates facts before generation: score (including own goals), shot
conversion (excluding own goals), pass completion with known-outcome denominators,
half-by-half attempts, player contributions and recorded high recoveries where
coverage supports them. Every paragraph carries registered evidence references;
a separate model checks and edits the headline, prose, numbers, denominators and
causal interpretations before any narrative is published. Final references and
report structure are validated again; raw IDs and millisecond timestamps are
blocked from displayed prose. An unverifiable report leaves
the deterministic charts available. This reduces factual errors; it does not
establish the truth of every tactical interpretation.

The pitch is 105 × 68 m, divided into six equal length bands and three width
channels. Both teams attack +x; y below 68/3 is attacking left, then centre, then
right. An attacking left route faces the opponent's right side. Cell counts are
located on-ball actions, not player occupancy or possession duration.

A shot's entry route is the **first observed crossing of x=70** in its preceding
continuous, holder-linked chain, bounded to 30 seconds/eight earlier actions.
Opponent actions, restarts, missing recipient links, unknown outcomes, occurrence
gaps and gaps over 12 seconds break the chain. Shot origin is a separate statistic.
Unknown entry routes remain unknown. Archive matches without reliable recipient
links therefore default to shot-origin channel comparisons rather than fabricated
build-ups. Lane conversion shows goals AND attempts, with null for an empty sample.
No single-match channel rate is a reliable prediction or proof of an individual
defender's weakness. Suggestions are hypotheses; high recovery counts alone are
not proof of aggression or a pressing system.

The interpretation follows the distinction between wide-area delivery and chance
creation described by [FIFA's analysis of wide areas](https://www.fifatrainingcentre.com/en/fwc2022/technical-and-tactical-analysis/use-of-wide-areas.php)
and [FIFA Game Insights](https://www.fifatrainingcentre.com/en/game/game-insights/using-wide-areas.php).
These are methodology references, not additional evidence about Footie's matches.


### Coaching-quality refinement (27 October)

A published-browser test returned unavailable after about 45 seconds. A captured
local reproduction succeeded, but its headline incorrectly implied a win in a
2–2 draw and its recommendations were generic. The first two refinement checks
were withheld: field names leaked into prose and independent entry counts were
incorrectly compared with bounded shot-route windows. These are failed checks,
not accepted sample reports. The original production failure was not reproduced
locally; safe stage/type diagnostics now make future failures distinguishable
without logging model prose, URLs or credentials.

The report now gives each team a proposed coaching task and a measurable check,
with direct links to the referenced shot passages. The model receives roles,
score-before-shot context, final recorded actions, exact return-pass combinations
and shot outcomes. Whole-match aggregates remain intact, while examples select
up to three goals, the first blocked shot and the first other failed attempt per
team. The examples illustrate the counts; they do not estimate causal effects.
Independent final-third entry totals and truncated linked-route counts are omitted
from the writing packet because they cannot form a valid entry-to-shot funnel.
They remain in the visual report. Editorial questions depend on the team evidence:
more circulation with fewer attempts, frequent blocked attempts, or a focused
review of other unsuccessful finishes. A question is not a tactical diagnosis.

The editor can repair a draft before final validation. Both factual support and
coaching usefulness must pass. Final draw/win consistency is independently checked;
aggregate-score claims are rejected. Short citation aliases are mapped back to real
facts and passages. Standalone citation brackets are removed; references used in a sentence become readable passage clocks so the sentence stays intact.
This does not establish unobserved defender positioning, shot quality or causality.

The coaching approach follows UEFA's use of concrete tactical observations with
video and data: https://www.uefa.com/development/performance-analysis/about-performance-analysis/
The external methodology supplies no facts about the synthetic match.


A further bounded live author/editor check completed in 47.83 seconds. Manual
review found a pass-attempt/completion label error and grammatical gaps from
removed citation aliases. A narrowly scoped formatter now reconciles explicit,
cited full-match overview pass totals (not player, window or qualified pass counts)
with the computed values. The captured response is checked in
`fixtures/evaluation/analyst_report_coach_response.json` and replayed through the
final publication code without model calls. It preserves a correct 2–2 result,
384/442 and 316/373 completed/attempted passes, distinct coaching tasks and
readable references to actual passages. A single cited sequence is described as
an example rather than proof of a repeated pattern. This observed case is useful
as a coaching review prompt; it does not validate every future generated report.

The tested Northport task contrasts Stone to Blake at 11:21 (blocked) with the
Rivers/Fletcher return at 20:03 (goal), then proposes testing final-pass choices and
recording blocked/on-target outcomes. Eastbridge instead reviews longer build-up
against the recovery finish and Hayes/Mercer return. These are proposed drills
and review questions, not claims about unobserved defensive positioning.


### Published-report acceptance follow-up (27 October)

The fresh published test returned in 49.681 seconds with working desktop/mobile
cards and passage links, but manual review found a further wording variant:
442 pass attempts were called completed passes. It also incorrectly credited a
recovery to the scorer in a goal passage that did not start with his recovery.
A second model's approval is therefore not sufficient evidence of factual accuracy.

The API now projects the overview and player-contribution paragraphs directly
from the same revision's authoritative facts, including on cache reads. Strength,
weakness, proposed practice and measurement remain model-written. The projection
is pure, preserves stored responses and charges, and does not require another
model request or invalidate the report cache. No model token or spending limits
changed. The captured published response is a regression fixture; both English
and Chinese projections, idempotence and preservation of coaching text are tested.

Both sides' sampled goals contain return passes, and the generated coaching
recommendations consequently overlap. They are useful hypotheses for reviewing
specific passages, not proof that return passes cause goals or universally avoid
blocks. Do not force artificial tactical differences to make the report appear
more insightful. Event-only evidence cannot establish off-ball defensive errors.


### Judging experience (27 October, owner-authorized)

Opening Match summary now starts the report automatically. There is no approval
button or cost message. Completed reports are shared and reused; pending work is
joined rather than started again. Close/reopen does not duplicate a model job.

The application defaults to `COUNTERPRESS_USAGE_CAPS=off`, as explicitly requested
by the owner. Analyst live/report/native cumulative spending ceilings and
hour/day allowances, plus Footie's cumulative model-call allowances, no longer
stop judging sessions. Historical accounting is retained. Same-origin controls,
short request-rate limits, two concurrent jobs, bounded model turns, timeouts,
failure cooldowns and factual checks remain. Azure subscription credit limits and
provider quotas are external and are not changed. Set the variable to `on` to
restore legacy admission limits without resetting prior charges.

The report uses an editorial scoreline and verdict, a team coaching brief,
full-width training plan, player contribution and distinct evidence panels.
Reduced motion and narrow screens are supported. This supersedes earlier
approval/cost-cap descriptions above.
