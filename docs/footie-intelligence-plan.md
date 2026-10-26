# Footie intelligence improvement plan

Status: implementation in progress, 26 October 2026. The core intelligence release
shipped on 24 October. Phase 4 now has locally verified revision-aware highlight
cards and assistant observation boundaries; career ingestion remains disabled in
production pending isolated hosted validation. Independent evaluation and release
evidence are recorded in [the verification report](verification/footie-intelligence.md).
This document does not claim the full sequence has shipped.

Managed-identity support and a curated Foundry export are prepared locally. Existing
production model authentication and ingestion configuration remain unchanged. Builds
on the bounded assistant, personalized cards, event revisions and application-hosted
agents.

## Product outcome

A fan understands what happened, why the recorded play matters to them, and where
to look next. Every useful answer connects **explanation → evidence → replay or
profile**. The same underlying facts support different interests without changing
credit, scores, denominators or eligibility.

Keep the existing Footie panel, Matchday, Match Centre and Clubhouse. Matchday
remains highlights-only. Four featured matches remain the watchable library;
wider career history supports profiles and analysis. Add capability within these
journeys, with progressive disclosure rather than another tools dashboard.

## Three user journeys

| Fan question | First useful answer | Supporting view and action |
| --- | --- | --- |
| What made that goal happen? | Explain the recorded buildup, transition timing and contributions before the finish. | Short possession timeline; replay the relevant sequence. |
| How is my player doing? | Compare the player's recorded involvement or production with an appropriate historical baseline and role. | Compact comparison; open the player or relevant moments. |
| What has changed in the game? | Describe a supported change between comparable, completed observation windows. | One clear before/after visual; replay an example. |

Casual answers lead with one plain-language finding. Analyst answers expose
comparisons, denominators and evidence. A player's supporter may see their buildup
contribution while a scorer's supporter sees a milestone. Preferences influence
relevance, never the truth or the order of sporting credit.

## Phase 0 — establish trustworthy scope and baseline

Before expanding reasoning, inventory which sources support each proposed tool:
canonical events, timestamps, possession boundaries, actors, outcomes, locations,
minutes and historical coverage. Check existing detectors before adding another
implementation of the same metric.

Create explicit mappings between canonical career matches, archive events and
linked highlights. Namespace source IDs. Unlinked preloaded reconstructions can
support local play explanations but cannot acquire invented career history.
Animated player coordinates must not become measured tracking data.

Freeze current regression results and compare the current workflow with a
single-agent baseline using the same tools, model, context and evidence. Prepare
an independently reviewed question set and expected facts before tuning. Keep
new holdout questions out of development prompts.

Deliverable: source capability matrix, versioned analysis definitions, baseline
report and independent fixtures. A tool is unavailable when its inputs do not
support it; missing observations are not zeros.

## Phase 1 — football analysis tools, independent of the model

Start with goal buildup and player contribution, then add form and window changes.

1. **Possession chain:** identify observed start/end, actions, participants,
   progression and elapsed regain-to-shot time where endpoints are known. Show
   contributions separately from official assists; do not invent assists from
   proximity or participation.
2. **Player involvement:** recorded receptions, passes, carries and shot-creating
   actions where present, plus team shares and role-appropriate covered rates.
   Do not label all observed events as touches or infer off-ball movement.
3. **Historical comparison:** compare compatible metrics, roles, units and
   covered periods; expose sample size and minimum eligibility. During replay,
   historical baselines end before kickoff. Any current-match addition must be
   explicitly calculated once at the selected occurrence/availability cutoff.
4. **Match changes:** compare completed `(start, end]` windows using documented
   eligibility and minimum samples. Reuse existing progression/pressure analysis
   only where source semantics support it. A ranking is descriptive, not proof
   of statistical significance or tactical causation.

Tool results carry subject, metric, unit, coverage, window, rules version and
source event/revision references. Test against separately authored expectations,
including incomplete chains, missing positions, period boundaries, duplicates,
corrections, retractions and no-change controls.

Exit: calculations and scope checks pass independently of any model; one real
fixture in the existing library supports the goal-buildup journey end to end.

## Phase 2 — bounded investigation and useful explanations

Retain Footie as orchestrator, Match Analyst for current-play evidence and Career
Analyst for historical comparisons. Upgrade their capabilities before adding roles.

The workflow becomes: resolve the fan's question and cutoff → choose relevant
tools → inspect evidence → optionally request one focused follow-up → compose an
explanation with explicit claim references → validate → render an answer/action.

Preserve the existing maximum four provider requests per question initially.
Simple questions skip delegation and extra investigation. The optional follow-up
uses the remaining shared allowance rather than an unbounded agent loop. Measure
any proposed increase separately before changing admission limits.

Support flexible explanation structure with typed claims and approved relations
such as temporal sequence, comparison and milestone. Python supplies factual
names, numbers, units and scope. Treat connective wording as reviewable output:
claim citations alone do not validate an unsupported causal sentence. Use a
verified concise fallback when composition, timing or validation fails.

The agents may report observed routes and contributions; they cannot invent
marking intent, measured speed, injuries or causal mechanisms from animation.
Ask one short clarification when ambiguity affects the answer. Return supported
partial findings when a specialist fails, clearly scoped to what was established.

Exit: all three user journeys work through the existing local Footie interface,
with a relevant replay/profile action and natural language rather than JSON.

## Phase 3 — prove user value before expanding cloud integration

Use at least 40 fresh cases, including ordinary fan language, paraphrases,
follow-ups, combined match/history requests, absent data, misleading premises,
different preferences, temporal boundaries and corrections. Include English and
Simplified Chinese for any newly shipped bilingual claim family; track unsupported
translation coverage explicitly.

Proposed release targets, not current results:

- At least 90% task completion on supported fresh questions. Report unsupported
  and clarification cases separately so refusals cannot inflate this measure.
- Zero observed fabricated numerical claims, incorrect entity attribution,
  future-data leaks or stale replay links in the release suite. Any such failure
  blocks release; this is a test gate, not a guarantee outside the sample.
- Human review confirms explanations add useful context, with a matched comparison
  against the baseline. Seek five fans when available; engineering review does
  not substitute for user evidence if recruitment remains pending.
- Report correct tool choice, clarification quality, audience differentiation,
  p50/p95 latency, provider calls and tokens. Target p95 at most eight seconds for
  uncached interactive answers on the agreed load; publish measured results.
- Existing profile, replay, keyboard and mobile journeys remain usable. New
  evidence views stay collapsed by default and controls keep adequate spacing.

If a holdout reveals a failure, preserve that first score. Once used for tuning,
those cases become regressions; use another untouched set for renewed claims.
Keep the multiagent path only where its measured benefit justifies extra latency
and cost. Model-based grading supplements deterministic and human checks.

## Phase 4 — one proactive, personalized live path

After the core quality gate, connect the improved intelligence to the existing
Event Hubs → Container Apps → Cosmos → Web PubSub path. First verify the current
hosted configuration: the career revision bridge is documented as locally
implemented and pending cloud activation.

Extend existing milestone and focused-player cards. Use deterministic candidate
triggers for significant completed plays, supported pattern changes and milestones;
invoke AI only when it can add context. Cache shared evidence and a small set of
audience variants. Enforce deduplication, cooldowns and one active insight card.

Each insight needs a stable identity, source namespace, match/event revision,
occurrence and availability times, evidence fingerprint, expiry and audience
scope. Apply corrections as updates or withdrawals, including stale cache and
queued narration invalidation. Recheck revisions before publishing.

The correction journal does not regenerate independent archive/preloaded replays.
For the showcase, use a supported canonical match and verified replay binding.
If a correction invalidates the replay, suppress its action until a valid version
exists; never leave the old animation presented as corrected evidence.

Next hosted verification design (reviewed, not provisioned): a temporary
`counterpress-phase4` app, `histories-phase4` Cosmos container,
`deliveries-phase4` Event Hub and `counterpress-phase4` Web PubSub hub, reusing
existing service tiers. Keep the production guard exact; introduce a separate
guard that rejects mixed production/test settings. The PubSub hub currently needs
a server-side configuration extension. Verify distinct checkpoint/quarantine
prefixes and scoped identity access before sending. Use the same byte-identical
fixture snapshot and genuine dataset digest with a separate journal/index; never
rewrite checksums to manufacture a new dataset. Disable inference in this test app.
Stop/drain the sender and remove temporary resources after collecting evidence.

Exit: demonstrate duplicate delivery, correction, restoration, reconnect and
paused-viewer recovery through the real hosted path. No API-only claim of success:
inspect two browser viewers and the resulting trace.

## Phase 5 — purposeful Microsoft integration and release

1. **Foundry quality management:** export curated synthetic evaluation trajectories
   and compare releases. Keep raw user conversations out of production telemetry.
   Local evaluation begins in Phase 0; Foundry integration extends it here.
2. **Azure Speech, Follow by ear:** focus on highlights, using the same validated
   insight for optional spatial narration and captions. Test first-audio delay,
   pause/seek, 0.5–2× playback where supported, correction cancellation and queue
   backlog. Prefer short completed-play summaries; drop obsolete queued insight
   before it delays the next one. Avoid changing playback merely to fit speech.
3. **Entra managed identity:** replace backend model-key access after validating
   the SDK and least-privilege model role. Cross-device fan accounts are optional
   later work; they are not required for this showcase.

Keep the runtime in Container Apps. Additional search infrastructure, portal
authoring migration, new agent roles and an Agent Console are deferred unless a
measured user or engineering need justifies them. Check actual spend and credit
expiry before paid work: US$125 is the total project cap, not remaining credit.

Implement and validate locally first, in small reviewable increments. Publish a
tested staging revision before changing live traffic. Keep the prior revision
and feature flags available for rollback; a rollback must preserve committed
event revisions and journal state. Only enable new ingestion after compatible
consumers are deployed and the isolated hosted correction check passes.

## Showcase and immediate next move

The proposed 90-second journey: choose two fan interests → play one supported
highlight → explain its buildup and personal significance → open the evidence or
replay → demonstrate an event correction updating affected insights → reveal the
Foundry execution trace and measured baseline comparison. Use actual supported
statistics; do not invent a milestone just to make the script more dramatic.

The first core increment shipped on 24 October: evidence-backed buildup,
role-aware involvement/history, equal-window comparisons, bounded investigation,
and the existing Ask Footie panel with supporting timelines and actions. The
independent fresh-wording result is 28/30 supported requests (93.3%); the subsequent
known-case regression passes 40/40 scored checks. Those are different measures.

The complete forty-question regression on the v4 compatibility build passed
40/40: thirty supported answers, five clarifications and five unsupported requests.
Supported answers measured p50 3.408 seconds and p95 5.167 seconds, using 69
provider calls across the suite. All source fingerprints stayed unchanged. There
were no supported-answer partial failures or fallbacks; one missing-favorite-player
case safely fell back to clarification. This passes the local engineering latency
gate, not deployed ingress/browser performance or recruited-fan usability. The
previous full supported p95 of 10.875 seconds and failed diagnostic runs remain
in the verification history. The fresh-wording accuracy remains 28/30 (93.3%);
the new run is a known-case regression, not a new blind result.

Request-owned HTTP/authentication reuse, stage timings, direct unknown-origin
answers, carry-led finishes, role-aware keeper context and localized units are
implemented. A sole validated summary skips unnecessary synthesis. Incomplete
research fallbacks visibly disclose missing analysis and clear inherited scope.
The isolated evaluation harness now matches its invocation allowance while
retaining the approved persistent 600-call rolling-day ledger. Production limits,
request deadlines and final evidence rereads remain unchanged.

The rollout audit additionally found that new cached plan fields would make the
old runtime reject the shared admission document. Writer compatibility now keeps
the original quota format: advanced/calculated successful answers are recomputed
on repeat requests rather than cached there, preserving all charged reservations.
Legacy-compatible answers still cache. This avoids a new store or a quota reset
and keeps rollback readable. Tests use an independently frozen legacy decoder.
Intentional calculated answers no longer appear as monitoring failures.

The complete run includes the compatibility and telemetry fixes, superseding the
earlier twenty-case sample for release regression evidence. Full application checks,
isolated staging and the core production release subsequently passed. Phase 4 adds
explicit revision review without advancing a paused viewer or replaying withdrawn
source material. Next: create an isolated hosted career journal, ingestion stream,
checkpoint and notification scope for correction/reconnect validation. Do not run
withdrawal/restoration on the public canonical fixture: even a restored goal changes
its immutable digest and invalidates its authored replay and three highlights.
Managed-identity activation and the optional Speech extension follow separately. Prepared Foundry
exports are local artifacts, not uploaded evaluations. Human fan testing remains
pending recruitment.
