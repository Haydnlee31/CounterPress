# Follow by ear: integration audit

Read-only source audit, 23 October 2026. No audio, UI or cloud settings were changed.

## Existing behavior worth preserving

- Six preloaded/generated scenario highlights have whole-highlight reviewed
  scripts in `live/highlight_narrative.py`, pinned to exact source hashes.
- Azure Speech produces one continuous recording with actual speech bookmarks.
  The backend verifies audio/source hashes, duration and marker alignment.
- `companion/highlightTrack.ts` buffers the complete recording before Play,
  validates decoded duration, maps seek positions through the same markers, and
  uses `playbackRate` with pitch preservation. Tests cover 2× playback, cancellation
  and stale-owner cleanup after seek/speed changes.
- Legacy event commentary coalesces up to four pending observations and never
  cancels a sentence for each routine arrival. This is separate from the reviewed
  whole-highlight narration path.
- Speech synthesis has rate limits, reserved character budgets and a private Blob
  cache. No unrestricted user text/SSML is accepted at the public speech boundary.

## Current coverage gaps

The speech corpus uses immutable scenario fixtures plus the legacy simulated
full-match source. It does not contain the new canonical career highlight events.
The live career correction journal therefore does not automatically revise those
scripts or recordings. A source hash is checked against its authored fixture,
not a live career-journal epoch. Do not present that as correction-aware career
narration.

The current whole-highlight narrator maps animation to speech bookmarks. This
already solves the previous cut-off-word problem, but it is an audio-led replay
mode. Adding new analytical sentences into that recording would alter the map
and require regenerated/reviewed assets. It is not an independent spatial
accessibility description synchronized to unchanged match footage.

## Smallest useful next integration

Add an optional **completed-play spoken explanation**, after the existing
highlight narration finishes, using the exact verified buildup card already
shown on screen. Keep the existing recording and pitch timing intact. Do not
synthesize every pass or insert analytical speech into a sentence in progress.

The server should accept a bounded insight identity/context (match, goal revision,
cutoff, audience), recompute its facts, and derive reviewed short wording. The
client must never supply arbitrary narration prose. Cache by evidence fingerprint,
audience/language and voice version. Reuse the existing Speech resource and its
cost gate; no new model call is necessary to read a calculated card.

Before playback, recheck the insight fingerprint. Cancel preparation and discard
queued audio on highlight switch, seek, revision change or card withdrawal. Do
not interrupt ongoing narration for routine passes. One pending completed-play
explanation is sufficient; a later relevant insight replaces an obsolete queue.
Use the same text as captions and label the requested playback mode clearly.

For now, existing backend replay endpoints return 409 after canonical corrections
until the replay is reauthored. Spoken insight support must honor that boundary:
updated statistics do not establish that an old animation became correct.

## Tests required before shipping

Test first-audio delay, real audio playback, captions, pause/resume, seeking,
0.5–2× speeds, zero overlapping voices, highlight switches, revision withdrawal,
late-synthesis completion, reconnect recovery, no-provider fallback and duplicate
requests. Use actual browser audio checks in addition to fake-audio unit tests.
The current audit establishes none of those new-path results; it defines the
smallest safe extension to implement after the core intelligence release gate.
