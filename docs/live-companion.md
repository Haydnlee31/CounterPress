# Live Companion

The first implementation lives inside Matchday, immediately below its animated
pitch. Open a highlight, choose **Listen**, then play. **Follow the play** opens
location detail, three questions and the last three completed actions. The
existing English/Chinese preference applies throughout.

This is the first migration away from producer script preparation toward an
optional companion for viewers. Studio remains available under Tools; this change
does not alter its saved work or approval controls.

## Delivered

- Optional device speech, off by default, synchronized to the pitch playhead.
- Completed-action commentary with optional location descriptions.
- Questions about the latest completed action, recent build-up and sequence totals.
- Expandable source actions behind each answer, without JSON in the viewer UI.
- Pause, seek, revision and language invalidation; a bounded speech summary buffer.
- Text remains usable if speech is unsupported or fails. Backgrounding the page
  stops speech. A natural finish can complete its final spoken cue.

The evidence selector gates both presentation order and revision availability.
It chooses the highest available revision for each event in the current match.
Answers and displayed evidence are discarded on playhead or source changes.
Counts refer to the displayed sequence so far, never full-match totals. Build-up
uses at most four completed actions within 30 seconds, stopping at a recovery or
half boundary. It describes recorded actions, not inferred tactical causes.

## Architecture and scope

Existing snapshot API → MatchPitch playhead → completed-event selector →
deterministic answers and text → optional browser SpeechSynthesis.

No new API, model calls, credentials, Azure service or recurring charge is added.
Azure Speech configuration was not present in the local configuration check.
Device speech is not Azure Speech; voices and pronunciation depend on the browser
and installed voices. Text is derived from event records, not a transcript of an
original broadcaster. This is not complete video audio description, and the
illustrative off-ball positions are not used as analytical evidence.

The current release covers Matchday highlight/sequence playback. It does not yet
provide a full-match paced stream, free-form conversational AI, microphone input,
translation of broadcast audio, or broadcast overlays. These are subsequent
integration work, not hidden capabilities of the question buttons.

## Next integration

1. Run the synthetic full-match feed through a viewer-specific clock, preserving
   pause/seek and source revision availability; compute scores and statistics
   only from that clock's available event prefix.
2. Add Azure Speech behind server-side configuration and a bounded cache, retaining
   the text experience and device fallback. Review cost against the $75 total
   project allowance before enabling paid usage.
3. Add authenticated, rate-limited free-form questions using the existing model,
   with evidence selection at the viewer clock and cancellation on seek/revision.
   Keep immediate action commentary deterministic so model latency cannot delay goals.
4. Test comprehension and controls with football viewers, including blind/low-vision
   and deaf/hard-of-hearing participants, before claiming accessibility outcomes.

## Verification

Run `npm --prefix frontend test -- --run` and `npm --prefix frontend run build`.
Regression tests cover future-outcome exclusion, source availability, revisions,
match isolation, build-up boundaries, answer invalidation, opt-in speech,
cancellation, natural endings and speech failure. Browser verification:
`node scripts/test_live_companion.cjs http://127.0.0.1:8010` (Playwright required).


## 19 October 2026 — speech pacing correction

The original implementation cancelled speech on every pending/resolved playhead
transition. Fast highlights therefore repeatedly interrupted sentences. Commentary
now waits for the browser utterance's `end` event before starting the next update.
Pending setups update text only. While a sentence plays, up to four completed
actions are retained: consecutive completed passes by the same side become a
short passing summary; otherwise the latest action is used. A pending shot takes
priority over routine actions at the next sentence boundary. This deliberately
omits routine actions when playback outpaces speech instead of building a backlog.

Pause, explicit seeking (including seeking to the end), mute, source corrections,
language/detail changes and leaving the page invalidate both current and queued
speech. Natural playback completion drains the bounded summary. Generation checks
ignore callbacks from cancelled utterances. No fixed speech-duration estimate or
forced increase in voice speed is used by the scheduler.

Reference: [browser speech completion event](https://developer.mozilla.org/en-US/docs/Web/API/SpeechSynthesisUtterance/end_event).

`node scripts/test_companion_speech.cjs http://127.0.0.1:8010` runs three real
highlight animations at 1.5× with an instrumented four-second voice. It checks
sentence completion, zero routine interruptions, a completed goal announcement
and a drained queue. This tests scheduling, not audible device voice quality.
