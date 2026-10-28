# Important context: Reactor review and personalization direction

> Historical reference. This records an earlier implementation; use the [current documentation index](../README.md) for the public Footie experience.

Saved 19 October 2026 at the user's request. This is project context for the next
personalization and assistant stages. The colleague's UI redesign is still in
progress; backend work must preserve existing UI contracts and avoid editing their
screens. Save new integration code separately until the UI is ready.

## What was reviewed

Brian Benz's [Microsoft Reactor session](https://developer.microsoft.com/en-us/reactor/events/27536/),
14 October 2026: **Build AI-powered soccer insights apps with AKS and ACA**.
Review covered the recording's full auto-generated transcript, selected demo
screens, and the [companion repository](https://github.com/bbenz/football-results-dashboard).

The application answers historical football questions over approximately 49,500
men's international matches spanning 150 years. Seven suggested questions give
visitors an immediate starting point; custom questions call bounded, read-only
analytics tools. Python/SQL owns the numbers and charts, while a Microsoft Foundry
model selects tools and explains their results. It runs locally and on both AKS
and Azure Container Apps. It is a historical analytics reference application, not
a demonstrated live event or video-analysis pipeline.

Useful recording sections:

- [2:56: question-led dashboard](https://www.youtube.com/watch?v=EQ187ohgCbo&t=176s)
- [9:17: architecture](https://www.youtube.com/watch?v=EQ187ohgCbo&t=557s)
- [12:33: deterministic facts and model explanations](https://www.youtube.com/watch?v=EQ187ohgCbo&t=753s)
- [28:45: refusing unsupported counterattack questions](https://www.youtube.com/watch?v=EQ187ohgCbo&t=1725s)
- [38:51: evidence and answer diagnostics](https://www.youtube.com/watch?v=EQ187ohgCbo&t=2331s)

The speaker explicitly deferred questions about synthetic-data eligibility to the
organizers. This session is inspiration, not an authoritative substitute for the
hackathon rules.

## Comparison with CounterPress at review time

CounterPress already has event-level replays, highlights, synchronized narration,
Cosmos revision history, Event Hubs ingestion and Web PubSub revision notices.
Its new career foundation provides 44 featured players across four clubs,
844 fixtures overall, and evidence-backed player/club summaries and milestones.
That foundation is on `feat/personalization-data-foundation` (PR #49), not yet
integrated into the UI or deployed at review time.

Brian's application has a more complete user-facing question-and-answer path and
request-level observability. CounterPress has bounded internal model workflows,
but the general fan-facing assistant, provisionally Footie, remains a later stage.
Our new career index is not yet wired to the existing Event Hubs consumer.

## Decisions to carry forward

1. **Build personalization before the general assistant.** Favorite clubs/players,
   profiles, recent form, player focus and relevant highlights establish the
   context the assistant will eventually use. The colleague owns UI composition.
2. **Start with fan questions.** Examples: how recent form compares with last
   season, why a goal matters, who contributed to a club's goals, and how a player
   reached a career milestone. Suggestions must be supported by available data.
3. **Answer, visual, action.** A short explanation should lead to a calculated
   visual and a relevant next step: watch a goal, inspect a player, or compare a
   period. Avoid turning the assistant into a disconnected wall of chat text.
4. **Preserve semantic evidence bindings.** Each claim binds subject, metric,
   period, value and evidence revision. A number merely appearing somewhere in a
   tool response is not enough. The sample's [numeric checker](https://github.com/bbenz/football-results-dashboard/blob/main/demo/src/football_insights/agent/grounding.py)
   allows numbers from the question and compares magnitudes; it does not fully
   validate subject/metric association. Do not weaken our existing contracts.
5. **Keep facts independent of preferences.** Favorites affect selection and
   presentation, never scores, credit, statistical denominators or eligibility.
   Playback must not reveal later outcomes or career milestones.
6. **Evaluate the assistant before release.** Fixed fan questions, paraphrases,
   unsupported requests, correction handling, latency and cost are useful lessons
   from the sample's [evaluation methodology](https://github.com/bbenz/football-results-dashboard/blob/main/docs/METHODS.md#evaluation).
7. **Keep fan screens focused on football.** Detailed traces, model names, token
   usage and technical qualifications belong in expandable supporting views or
   operational tools. Meaningful coverage still needs to be represented honestly;
   unavailable metrics must never masquerade as observed zeros.
8. **Keep Azure Container Apps.** No demonstrated need for AKS. ACA already
   supports jobs, revisions, traffic splitting and scaling. Stay within the
   approved US$75 total budget and avoid adding services for appearance alone.
9. **Useful later architecture work:** managed-identity model authentication,
   request-level OpenTelemetry/Application Insights, and the career-index ingestion
   bridge. These are proposed, not completed by this review.

## Product proof to aim for

**Follow Enzo Clarke → see his live milestone → ask why it matters → replay the
goal.** This connects the data foundation, personalization, explanation and
broadcast presentation in one understandable journey.

Preferences initially stay on the device. Cloud accounts and cross-device
preference synchronization require a deliberate identity/storage design later.
Matchday stays highlights-only; Match Centre has four featured matches; wider
career history remains in player and club profiles. Never count highlights as
additional matches. No new general model agent is implied by a suggested question.

## Implementation follow-up — 20 October 2026

The personalization workspace and calibrated analytics are now implemented
locally. The first [grounded Footie assistant](../grounded-assistant.md) follows the
answer → visual → action direction above. Azure selects a bounded query plan;
Python owns all statistics and explanations. A separate `#assistant` workspace
supports profiles, comparison, form, club contributors and goal milestones, with
a handoff to the existing replay. The career-index ingestion bridge and embedding
the assistant into live viewing remain later work. This note updates implementation
status without changing the saved review or its historical findings.

The subsequent narrative layer now offers calculated rates, comparison gaps,
score impact and milestones as evidence-bound sentences. A second bounded Azure
request chooses emphasis and order; Python still owns the facts and wording.
This adopts the reference application's story-first presentation without
introducing unrestricted generated factual prose. Both calls share the original
20-attempt hourly allowance. See [narrative verification](../verification/footie-narration.md).

## Finishing review — 21 October 2026

The published application now includes Clubhouse, contextual Footie panels and
unified Watch/Breakdown views. The original review's missing fan-facing assistant
is therefore no longer a gap. The remaining priorities are repeatable assistant
question evaluation, the live career-index bridge, assistant request tracing,
and managed-identity model access. Retain ACA and evidence-bound sentences.

The first [question benchmark](../verification/footie-question-benchmark.md) found
14 offline failures and a live model tendency to narrow career questions to the
current season. Local fixes now pass 58 authored regression cases; captured-model
responses and two fresh targeted Azure checks verify the scope guard. Preserve
the initial 5/10 live-sample result: a complete post-fix live sample is still
pending the evaluation allowance renewing. No streaming bridge or cloud release
was performed in this step.

## Follow-through: career revision bridge (21 October 2026, local)

The career-index gap described above now has a local implementation: distinct
career Action envelopes through the existing Event Hubs consumer, a dataset-pinned
atomic correction journal (SQLite locally; existing Cosmos container in cloud),
and Web PubSub refresh hints. Compound Clubhouse/personalization/Footie reads
refresh the same durable state. Browser revision checks invalidate outdated
statistics and assistant answers without automatic model calls. This is not yet
a hosted deployment or an update to the independent archive replay contracts.
See [implementation and activation boundaries](../career-revision-bridge.md).
