# Existing Footie implementation and Azure readiness

Read-only audit, 26 October 2026. This note concerns the current application/account, not the separate MatchMind source review or current Foundry API research. No cloud resources, permissions, application code, budgets, or production settings were changed.

## Where should Analyst Mode integrate without disrupting Footie?

### Takeaway

Add a separate lazy-loaded `#analyst` experience with an explicit Matchday “Watch full match” entry. Reuse canonical event/career services and replay components where their contracts fit; leave the existing Footie assistant and its provider path intact. Do not simply relabel the legacy `#live` page.

### Cited Findings

- App routing currently distinguishes `#assistant`, `#football…`, `#live`, `#gi`, Studio and Tools, then defaults to Matchday/Breakdown. There is no Analyst route. Matchday has Watch/Breakdown navigation; its file has no current Watch Full Match entry. — [App router](/Users/haydn/Documents/CounterPress/frontend/src/App.tsx), [Matchday](/Users/haydn/Documents/CounterPress/frontend/src/matchday/Matchday.tsx)
- `#live` imports `frontend/src/live/FullMatch.tsx`, an older single-match replay with its own clock, pitch and companion. Current Match Centre uses `gi/PlaySequence.tsx` for continuous full-match and selected-sequence playback, with faces/initials, speed, roster, player hover and new observation integration. The sequence component owns its clock internally and has no external clock-change callback in its current props. A shared callback/controlled clock seam would be needed to synchronize an independent analyst surface. — [legacy FullMatch](/Users/haydn/Documents/CounterPress/frontend/src/live/FullMatch.tsx), [PlaySequence](/Users/haydn/Documents/CounterPress/frontend/src/gi/PlaySequence.tsx)
- GI's catalog and backend allowlist contain **three** matches. The fourth canonical career showcase is present in personalization data but is explicitly excluded from the Clubhouse “Open Match Centre” link; it must not be advertised as an already supported full-match GI replay. — [GI catalog](/Users/haydn/Documents/CounterPress/frontend/src/gi/catalog.ts), [GI service](/Users/haydn/Documents/CounterPress/backend/counterpress/gi/service.py), [Clubhouse history detail](/Users/haydn/Documents/CounterPress/frontend/src/football/FootballHub.tsx:164), [fourth fixture](/Users/haydn/Documents/CounterPress/fixtures/personalization/career-showcase-southbank-redhaven.json.gz)
- FastAPI startup creates a shared canonical career service, then installs fan, assistant, GI and live routes separately. A new `install_analyst(application, career_service, …)` seam can preserve that separation. — [API assembly](/Users/haydn/Documents/CounterPress/backend/counterpress/api/main.py:79)
- Current existing multiagent orchestration runs in Python using Agent Framework. Its tasks are bounded to at most two specialists, roles are orchestrator/match/career, and maximum provider requests are four. Foundry records are external-agent registrations and tracing, explicitly not native project execution. — [multiagent runtime](/Users/haydn/Documents/CounterPress/backend/counterpress/assistant/multiagent.py), [Foundry monitoring design](/Users/haydn/Documents/CounterPress/docs/footie-foundry-monitoring.md)

### Inferences

- Recommended new file boundaries: `backend/counterpress/analyst/{contracts,metrics,evidence,foundry,service,api}.py`, `frontend/src/analyst/{AnalystMode.tsx,analyst.css,data.ts}`, and a separately named Foundry provisioning script. Keep new Foundry agent names/versioned definitions distinct from `footie-orchestrator`, `footie-match-analyst`, `footie-career-analyst` external registrations.
- The UI should make the match the primary surface, with one active insight, a compact change timeline, and a secondary specialist/evidence drawer. Avoid presenting an always-expanded grid of agents or duplicating every metric around the pitch. Mobile should prioritize replay, current insight, then specialist details.
- Safest first implementation is a supported three-match canonical replay adapter, with fourth-match capability enabled only after roster, event ID, pitch-orientation and clock parity tests. A new canonical replay adapter may be preferable if it avoids coupling new agents to GI's static source format.

### Gaps

- No browser visual verification was performed in this read-only audit.
- Native Foundry invocation/orchestration API and hosted workflow feasibility are covered by the separate Foundry research agent; this audit does not claim that creating prompt-agent definitions alone constitutes Foundry-hosted orchestration.

## What evidence and metrics are trustworthy today?

### Takeaway

The application has rich event evidence and career context, but not measured all-player tracking or local match footage. New agents should calculate from the evidence boundary and clearly distinguish authored telemetry, observed events and unavailable measurements in their machine-readable results.

### Cited Findings

- Canonical actions preserve match/event IDs, revisions, delivery sequence, occurrence order, period/time and separate availability period/time. They include actors, recipients/opponents/keepers, coordinates, goals/restarts, optional expected-goal/completion probabilities and authored flight duration. `telemetry_basis` is `authored_physics` or `unavailable`. — [Action schema](/Users/haydn/Documents/CounterPress/backend/counterpress/personalization/contracts.py:78)
- Existing reductions calculate event counts/rates, xG, expected completions, pass distance and authored flight-based speed. Coverage explicitly reports tracking unavailable; speeds require authored time and coordinates. — [metric reducers](/Users/haydn/Documents/CounterPress/backend/counterpress/personalization/metrics.py)
- Existing intelligence tools reconstruct goal buildup, player involvement and comparative windows, with caveats on incomplete possessions and no tracking. The latest local interpretation work adds qualified explanations such as dangerous regains and failed-pass consequences using conservative temporal/spatial/event continuity tests. — [intelligence tools](/Users/haydn/Documents/CounterPress/backend/counterpress/assistant/intelligence.py), [local interpretation](/Users/haydn/Documents/CounterPress/backend/counterpress/fan/interpretation.py), [local observation documentation](/Users/haydn/Documents/CounterPress/docs/live-observations.md)
- The fan service accepts playback cutoffs and delivery-sequence caps and generates fingerprints. The new observation handoff pins evidence, preferences and cutoff. Revisions therefore must invalidate old analyst outputs, not merely append a new chat message. — [fan service](/Users/haydn/Documents/CounterPress/backend/counterpress/fan/service.py), [observation assistant](/Users/haydn/Documents/CounterPress/backend/counterpress/assistant/observation.py), [frontend observations](/Users/haydn/Documents/CounterPress/frontend/src/gi/LiveObservation.tsx)
- GI itself reads cached static fixtures and exposes illustrative full-team reconstruction. Source match links exist, but the UI documentation explicitly says video timing is unverified and player movements are not continuous tracking. — [GI endpoint](/Users/haydn/Documents/CounterPress/backend/counterpress/gi/api.py), [GI source display](/Users/haydn/Documents/CounterPress/frontend/src/gi/GI.tsx)
- `rg --files fixtures frontend var -g '*.mp4' -g '*.webm' -g '*.mov' -g '*.m3u8'` returned no files during this audit. Existing local media found was speech audio. This search only establishes absence within those three trees, not elsewhere on the computer.

### Inferences

- Useful specialist boundaries are **chance creation/finishing**, **progression/transitions**, **defensive exposure**, and **player/career significance**, with Footie choosing and reconciling the strongest supported insight. All should consume one immutable as-of evidence packet, not fetch independently unbounded snapshots.
- Trigger bounded analysis on meaningful event transitions/windows; cache by match, cutoff bucket, revision fingerprint and audience. Do not send 22 player positions to a model every animation frame. Model-generated prose can explain a verified calculation, but cannot create physical measurements.
- A MatchMind parity checklist must explicitly separate event metrics already computable, derived estimates, authored synthetic tracking and actual video-derived measurements. A future video/CV pipeline requires footage rights/access, calibration, tracking and validation; current replay animation is not a substitute for those measurements.
- Validate no future-event leakage, revision retraction, half changes, backwards seek, stale async responses, incomplete source outcomes, and partial specialist failure. Reuse existing shared admission/cache/origin safeguards so a new public playback route cannot silently bypass model-call limits.

### Gaps

- This audit does not attest to MatchMind's metric coverage; use the dedicated repository research for the parity matrix.
- No direct frame-by-frame source footage validation or new model call was performed.

## Is the existing Azure account ready, and what is the budget position?

### Takeaway

Existing Foundry infrastructure and suitable model deployments can be reused. Native project execution needs a scoped runtime-role review. US$200 is the newly authorized total; current billed subscription spend is approximately US$5.97, with billing lag and credit expiry still unknown.

### Cited Findings

- Read-only `az account show` reports AzureCloud, enabled, default account. ARM resource listing confirms the existing `counterpress-dev-01/CounterPress` project, Container App, Cosmos, Event Hubs, Blob Storage, Web PubSub, Speech, Log Analytics and App Insights. All except Cosmos are in East US; Cosmos is East US 2. Source: sanitized Azure CLI queries executed 26 October 2026.
- Foundry account is `AIServices`, S0, system-assigned identity, project management enabled, public network enabled. Project is succeeded, system-assigned identity and has a project endpoint. Its private endpoint value was not recorded in this note. Source: ARM account/project GET, API `2025-06-01`, 26 October 2026.
- Existing succeeded deployments: `gpt-4.1-mini` version `2025-04-14`, GlobalStandard capacity100; `gpt-5-mini` version `2025-08-07`, GlobalStandard capacity125; `text-embedding-3-small` version1, Standard capacity120. These capacities are deployment configuration, not a cost ceiling or guaranteed request throughput. Source: `az cognitiveservices account deployment list`, 26 October 2026.
- Live app is healthy/provisioning succeeded at revision `counterpress--gh-40280008703-1`; minimum replicas0, maximum1. Existing assistant/tracing settings are present. Source: sanitized Container App ARM read, 26 October 2026.
- ARM role assignments found for runtime identity `counterpress-history`: Cognitive Services OpenAI User on the model account and Monitoring Metrics Publisher on the monitoring component. No Foundry project AI User role was returned. This does not inventory Cosmos data-plane roles. Source: read-only role-assignment list, 26 October 2026.
- Cost Management ActualCost query, current month: **CounterPress resource group US$5.9150230346**, latest usage date2026-10-26. Subscription MonthToDate total: **US$5.9663838346**. Existing resource-group budget: **US$125**, Quarterly, start2026-10-01/end2026-11-14; its lagging `currentSpend` is US$5.8270161458. Source: CostManagement query API `2025-03-01` and Consumption budgets GET `2024-08-01`, 26 October 2026. No budget mutation performed.

### Inferences

- Conservative nominal headroom against the user's US$200 total is **US$194.03**, before unreported usage and future hosting. This is not the remaining trial-credit balance. Do not equate budget end date with actual credit expiry.
- Verify native project execution under the app identity, add only required project-scoped roles once the chosen Foundry API is established, and run a bounded live smoke before activation. Existing OpenAI model access alone is not proof of agent-project access.
- Reuse the existing project, models and telemetry; do not provision another model account or vector database simply to host specialist instructions. Preserve production limits until new global/session/session-duration controls are explicitly implemented and reviewed. Portal budgets alert rather than enforce a stop.

### Gaps

- Trial-credit balance/expiration were not obtainable from the queries performed. Cost numbers are billed/available usage, not real-time spend.
- No native agent creation, deployment, project-role grant, model inference or resource mutation was attempted.

## How should this be validated and released?

### Takeaway

Preserve the current uncommitted local work, build the new mode independently, then use the existing protected exact-commit release path after evidence, UI and live connection checks.

### Cited Findings

- Local HEAD is `413aaa7`, the merged Foundry quality/managed-identity release. The working tree includes earlier live-observation/diagnostic changes and tests, plus research directories. This audit did not reset or alter them. Source: `git log -1 --format='%h %s'` and `git status --short`, 26 October 2026.
- CI runs locked Python dependencies, pytest, personalization verification, frontend tests/build, and container smoke checks. Deployment only executes on main, verifies successful CI for the exact current main commit, builds and smoke-tests before OIDC login, then uses guarded existing-app update logic. — [CI](/Users/haydn/Documents/CounterPress/.github/workflows/ci.yml), [deployment](/Users/haydn/Documents/CounterPress/.github/workflows/deploy.yml), [deploy helper](/Users/haydn/Documents/CounterPress/scripts/deploy_azure.py)
- Existing `foundry-admin` dependency is optional `azure-ai-projects>=2.3,<3`; registration script currently uses `ExternalAgentDefinition`. New native runtime support needs deliberate dependency/image packaging rather than assuming the admin extra is installed in production. — [project dependencies](/Users/haydn/Documents/CounterPress/pyproject.toml:29), [registration helper](/Users/haydn/Documents/CounterPress/scripts/configure_agent_monitoring.py)
- Backend source hashes are present in the editorial controls lock. Changes require regenerating/reviewing the intended lock, not weakening the test. — [controls lock](/Users/haydn/Documents/CounterPress/fixtures/evaluation/editorial_controls_lock.json)

### Inferences

- Add deterministic specialist evidence tests, orchestration contract/malformed-output/cancellation tests, and a benchmark distinguishing insight usefulness from factual correctness. Include causal restraint, uncertainty, replay cutoffs, shared costs, cache races and retried response duplication.
- Useful existing regression harnesses: `tests/test_assistant_admission.py`, `tests/test_agent_observability.py`, `tests/test_observation_assistant.py`, `tests/test_fan_intelligence.py`, `tests/test_gi.py`, `frontend/src/gi/PlaySequence.test.tsx`, `frontend/src/gi/LiveObservation.test.tsx`, and `scripts/test_live_observations.cjs`.
- Test UI desktop/mobile, keyboard focus, scrubbing, speed changes, paused/offscreen behavior and a complete replay before release. Native Foundry smoke must verify the actual deployed definition/version and project identity, not merely mocked transport or external trace registration.

### Gaps

- This audit is not a fresh test run and does not assert the new feature works. Parent implementation/testing must record the exact resulting commands, outputs and live evidence.
