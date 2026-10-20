# Embedded Footie context — 20 October 2026

## User flow

- Clubhouse player and club profiles expose **Ask Footie**, preserving subject,
  season and library date. Suggested player questions use role-appropriate metrics.
- Linked Matchday highlights, Match Centre sequences, full-match replay and career
  highlight dialogs pause and carry the currently displayed event ID/revision.
- The assistant dialog freezes context. Opening it does not submit a question or
  call Azure. Source-time resolution for legacy clips is a read-only request.
- Closing restores focus and leaves playback paused at the same position.
  A sticky close button stays visible during answer scrolling.
- Preloaded reconstructions remain separate; they have no canonical career-match
  handoff. No source clip is silently counted as an extra career appearance.

## Temporal and grounding checks

The new `moment.py` reducer answers the selected canonical action. Passes name
their recorded actor/recipient and, when available, their geometric start-to-end
distance. Shots and challenges use recorded outcomes. Goals use the existing
score-impact/milestone reducer at that goal's availability time. Selecting an
earlier goal does not silently explain a later one.

Pending actions return an unfolding message with no facts. Missing, retracted or
mismatched revisions return clarification, not substituted evidence or career
totals. Event references require a match, revision and playback cutoff.

The first browser run caught an availability mismatch: the older `level-first`
presentation ends its goal at parent occurrence time 2,094,786 ms, but the current
career record releases the outcome at 2,094,886 ms. The source-reference resolver
now returns canonical availability for resolved actions and the instant before
occurrence for unresolved actions. Tests pin both values. No fixed timing fudge
was added. Match Centre's native adapter also preserves source availability.

## Exact verification commands and outputs

```sh
.venv/bin/pytest -q
```

```text
772 passed, 1 warning in 107.57s (0:01:47)
```

The warning is the existing experimental evaluation warning.

```sh
npm --prefix frontend test
npm --prefix frontend run build
```

```text
Test Files  29 passed (29)
Tests  171 passed (171)
✓ built in 985ms
```

```sh
NODE_PATH=/Users/haydn/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules node scripts/test_footie_context.cjs
```

```text
PASS Footie context: profile season, no automatic questions, source-time highlight handoff, Match Centre event revision, pause/return, focus restoration, mobile layout, no browser errors.
```

The browser used a temporary non-Azure preview on port 8018. Desktop and
390/360-pixel checks passed. Screenshots were reviewed in
`var/footie-context-profile.png` and `var/footie-context-mobile.png`.

The main local server was refreshed on port 8017 with Azure enabled. Two real HTTP
questions, one selected pass and one selected goal, each passed both Azure stages:

```text
pass e00003: answered, azure / azure_selected, 6220 ms
goal e01178: answered, azure / azure_selected, 4656 ms
```

[Sanitized requests/results](footie-context-azure.json) preserve event IDs,
cutoffs, evidence bindings and returned text. Four total model calls reported
**6,548 input + 115 output = 6,663 tokens**. This is not a dollar billing total.
No new resources, cloud deployment or Git push. The 20-attempt shared hourly
allowance is unchanged.

## Files changed

- `assistant/contracts.py`, `service.py`, `moment.py`, `api.py`, `planner.py`,
  `narrative.py`: selected-event requests, canonical timing, grounding and routing.
- `gi/service.py`, `gi/synthetic.py`: preserve native revision availability.
- `frontend/src/assistant/AskFootie.tsx`, `context.ts`, `ask-footie.css`,
  `Footie.tsx`, `footie.css`: context dialog, frozen clock, focus and cancellation.
- Clubhouse `FootballHub.tsx`, `HighlightPlayer.tsx`; Matchday `MatchPitch.tsx`,
  `Matchday.tsx`; Match Centre `GI.tsx`, `PlaySequence.tsx`, `data.ts`; and
  `live/FullMatch.tsx`: context entry points and pause behavior.
- `tests/test_assistant_moments.py`, assistant frontend tests and
  `scripts/test_footie_context.cjs`: boundary and browser regression checks.
- Editorial source lock, README, assistant guide and progress: updated evidence
  and current usage instructions.

Career statistics, fixtures and player portraits were not regenerated.
