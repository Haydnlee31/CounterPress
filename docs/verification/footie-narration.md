# Footie contextual narrative verification — 20 October 2026

## What changed

`assistant/narrative.py` builds evidence-bound sentences from the calculated
answer. It adds explicit per-appearance rates for goals, assists, saves and shots;
gaps and ties for compatible, completely covered comparisons; and the existing
causal score-change and milestone statements. Sentence references bind exact
subjects, metrics, scopes, values and source evidence through a fingerprint.

Azure receives the question and candidate sentences, then returns only sentence
IDs. It selects a lead and up to one supporting sentence for casual fans, or two
for analysts. There is no free-form factual prose to validate by merely finding
the same number somewhere in a response. Model selection can still choose an
unhelpful emphasis; this is a usability limitation, not a correctness guarantee
about understanding every question.

The API rejects invalid IDs, arbitrary extra text, repeated IDs and excess
sentences. Failed selection uses the calculated story. It re-reads the answer
after the network request so a correction cannot leave old sentences attached to
fresh facts. Unavailable measures do not become zeroes; partial coverage prevents
a ranking-gap assertion. Unsupported questions do not invoke either model.
English stories are added; Chinese retains its existing localized factual answer.

Both stages share the existing allowance of 20 model attempts per hour, with at
most two attempts per question. The second stage is capped at 180 output tokens
and a six-second total deadline. No new Azure resources, push or cloud deployment.
The local preview was refreshed at port 8017 with both stages enabled.

## Checks and exact outputs

```sh
.venv/bin/pytest -q
```

```text
765 passed, 1 warning in 94.32s (0:01:34)
```

The warning is the existing experimental Azure evaluation warning. After a final
same-player wording refinement, relevant backend and source-lock checks were rerun:

```sh
.venv/bin/pytest -q tests/test_assistant.py tests/test_assistant_narrative.py tests/test_editorial_controls.py tests/test_editorial_evaluation.py
```

```text
106 passed, 1 warning in 20.72s
```

```sh
npm --prefix frontend test
npm --prefix frontend run build
```

```text
Test Files  28 passed (28)
Tests  167 passed (167)
✓ built in 1.03s
```

The new interface leads with the story, while original statements remain under
**Figures and context** and source facts under **Check the numbers**. UI tests
check both remain inspectable and profile navigation is preserved.

```sh
NODE_PATH=/Users/haydn/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules node scripts/test_footie.cjs http://127.0.0.1:8018
```

```text
PASS Footie: desktop, 390/360px, 75-goal answer, readable evidence, follow-up season, scope reset, milestone-to-replay, unsupported request, no browser errors.
```

That temporary preview had Azure disabled and was closed after testing. Desktop
and mobile screenshots were reviewed from `var/footie-answer-*.png`.

## Bounded Azure verification

```sh
.venv/bin/python scripts/check_footie_narration.py --azure
```

```text
stats: accepted (3270 ms)
seasons: accepted (1591 ms)
club_leaders: accepted (1835 ms)
match: accepted (1773 ms)
Saved sanitized results: docs/verification/footie-narration-azure.json
```

These four calls exercised the actual deployment's strict narrative schema.
[Results](footie-narration-azure.json) retain the original wording. The awkward
same-player comparison was subsequently refined. One complete HTTP request on
the refreshed server then verified both planner and narrator:

```text
Question: Compare Mateo Cross goals in 2025-26 and 2026-27
mode: azure
narrative.mode: azure_selected
duration_ms: 4429
```

[Integrated result](footie-narration-integrated.json) shows 14 goals in 22
appearances versus 7 in 9, with calculated rates of 0.64 and 0.78 per appearance.
This is context for unequal exposure, not a claim of improved ability.

The six total live calls reported **5,008 input tokens + 120 output tokens =
5,128 tokens**. No retries or additional live model calls were used in this stage.
These token counts are not an Azure billing total or dollar estimate. This small
canary verifies integration, not statistical accuracy over arbitrary questions.

## Changed files

- `backend/counterpress/assistant/narrative.py`: verified contextual sentences,
  selection validation, calculated fallback and Azure selector.
- `backend/counterpress/assistant/planner.py`: shared bounded structured-request
  transport; existing planner contract retained.
- `backend/counterpress/assistant/api.py`: second stage, shared budget,
  revision recheck, separate usage and fallback fields.
- `frontend/src/assistant/Footie.tsx`, `footie.css`, `Footie.test.tsx`: story-first
  answers and inspectable original figures.
- `tests/test_assistant_narrative.py`, `scripts/check_footie_narration.py`,
  `scripts/test_footie.cjs`: correctness, adversarial, live and browser checks.
- `scripts/run_footie_local.py`: startup help.
- `fixtures/evaluation/editorial_controls_lock.json`: reviewed source hashes.
- README, assistant guide, progress, saved Reactor context and this verification:
  implementation status, costs, boundaries and reproducible results.

Career fixtures, player statistics and portraits were not regenerated.
