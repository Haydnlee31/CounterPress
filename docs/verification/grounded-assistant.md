# Grounded Footie — local verification, 20 October 2026

**Result: implemented and running locally.** The preview at
http://127.0.0.1:8017/#assistant uses the existing Azure OpenAI deployment for
bounded question interpretation. No hosted deployment or Git push was performed.

## Exact checks

```text
.venv/bin/pytest -q
749 passed, 1 warning in 84.67s (0:01:24)
```

The warning is the existing experimental evaluator notice. Thirty dedicated
assistant cases cover fixed routing, reviewed values, subject/metric association,
season follow-ups, recent-form exposure, unsupported questions, unavailable
metrics, explicit favorite resolution, replay cutoff boundaries, goal retractions,
cache invalidation, model-plan rejection, timeout fallback, body/origin limits,
HTTP rate limits, the twenty-attempt model allowance and structured Azure output.
The offline/mocked source lock is `grounded-footie-v1`; no paid editorial pilot
was rerun or modified.

```text
npm --prefix frontend test
Test Files  28 passed (28)
Tests       166 passed (166)
Duration    8.76s

npm --prefix frontend run build
✓ 295 modules transformed.
✓ built in 868ms
```

Four dedicated interface tests cover suggested questions, readable evidence,
profile links, follow-up context, reset, failed-request retry, session-only chat,
late-response cancellation after a scope change, and unavailable chart values.

```text
NODE_PATH=/Users/haydn/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules node scripts/test_footie.cjs http://127.0.0.1:8018
PASS Footie: desktop, 390/360px, 75-goal answer, readable evidence, follow-up season, scope reset, milestone-to-replay, unsupported request, no browser errors.
```

Headless Chrome used a separate local lookup-only preview, with no browser-triggered
model calls. The first run found mobile navigation overflow; the final run checks
both page width and the visibility of the Footie navigation link at 390 and 360px.
Desktop and mobile screenshots were inspected. Screenshots remain under ignored
`var/footie-*.png`. The temporary preview processes were closed after verification.

```text
.venv/bin/python scripts/container_smoke.py http://127.0.0.1:8017
PASS: health, readiness, frontend/assets, Studio access, evidence/recaps, replay goals, GI attribution, 44 career profiles, four featured matches, nine personalized highlights, causal milestone, 22-player focus, audience fact parity, preference isolation, private-path 404s
```

The final startup command is:

```sh
.venv/bin/python scripts/run_footie_local.py --azure
```

Read-only HTTP checks confirmed that Footie and Azure interpretation are enabled,
its configuration has `private, no-store` caching, and the normal fan capabilities
advertise the assistant. These checks made no extra model request. The actual
configured model key and endpoint were checked against assistant deliverables and
the browser bundle: no matches. Canonical fixtures and analytics are unchanged.
`git diff --check` passed with no output.

## Live Azure canary

Eight bounded model attempts were made through the existing deployment. The first
six questions covered player totals, club assist leaders, per-90 comparison,
recent assist form, season comparison, and match-milestone explanation.

Four initial plans were accepted. One recent-form request timed out; one match
plan was rejected. Both produced the correct supported direct-lookup answer
rather than publishing unverified model output. The match prompt was clarified to
require an empty player list, null club/season fields and the selected match;
the output schema now enumerates valid metrics. The two follow-up checks were
accepted, at 3.22s and 2.38s respectively. Initial accepted requests took
2.18–4.59s; the initial timeout/fallback took 9.06s.

The [sanitized results](footie-azure.json) retain the initial failures, answers,
scopes and follow-up results. This small, deliberately selected canary is not a
statistical accuracy benchmark. Structured output validates shape; server checks
and deterministic readers validate the facts. Semantic routing can still need
clarification for ambiguous or unsupported requests.

Seven responses reported **19,022 input tokens and 309 output tokens**, totaling
**19,331 tokens**. The timed-out attempt has unknown reported usage and may have
been billed. These figures do not establish total Azure spending. No new Azure
resource, registry image, deployment or monthly service commitment was created.

## Files and boundaries

- `backend/counterpress/assistant/`: strict query contracts, bounded Azure planner,
  validated read-only data operations, deterministic explanations and API controls.
- `backend/counterpress/api/main.py`, `fan/api.py`: registration and availability.
- `frontend/src/assistant/`: separate Footie workspace, charts, evidence expansion,
  scope controls, session conversation, replay handoff and UI tests.
- `frontend/src/App.tsx`, `shell/AppHeader.tsx`, `shell/shell.css`: route, navigation
  and small-screen navigation sizing. Existing Clubhouse/profile screens and
  portraits were not edited.
- `scripts/run_footie_local.py`, `scripts/test_footie.cjs`,
  `tests/test_assistant.py`, `tests/test_fan_personalization.py`: startup and checks.
- `fixtures/evaluation/editorial_controls_lock.json`: offline source lock only.
- [User/architecture guide](../grounded-assistant.md), progress and saved Reactor
  context: current status and limitations.

The career-index ingestion bridge, public paid-inference authorization/shared
quotas, free-form research, video uploads and embedding chat in live playback are
not implemented by this stage. The first interface intentionally answers a
bounded set of data questions; it does not promise an unrestricted football agent.
