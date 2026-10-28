# Highlights workspace

Match Centre is the landing page and first navigation tab. Highlights is the second tab, followed by Clubhouse and Footie. The existing curated replays remain available under **Preloaded highlights**; legacy `#matchday` and breakdown links continue to work.

## Review locally

```sh
npm --prefix frontend run build
.venv/bin/python scripts/run_footie_local.py --azure --port 8019
```

Open `http://127.0.0.1:8019`:

1. Open **Moments**, choose an action, then **Save to Highlights**.
2. Select **Open highlight**. The replay appears above Footie’s summary.
3. Select **Red pen** to pause and draw on the pitch. Choose **Finish drawing** to return to normal player hover behaviour. Resuming playback hides the marks; **Saved frame** returns to an annotated frame.
4. Add coaching notes, save, reload, and reopen the same highlight.
5. Return to Match Centre. **Watch full match** opens the inline full-match replay. Its separate **Analyst Mode** button opens the existing analysis interface. See [Analyst Mode](analyst-mode.md) for the discussion and report workflow.

The Azure option uses the existing server-side `.env` model configuration. Credentials never enter browser storage or requests. Omit `--azure` for offline statistics summaries.

## Persistence and AI behaviour

- The collection is local to this browser and origin, under `footie.highlights.v1`. Collections do not sync across accounts or devices. Moving to another localhost port or the deployed site creates a separate collection.
- Save is independent of analysis: the replay reference is saved before any model call. Duplicate imports retain the original notes and drawings. Up to 50 highlights, 30 strokes per highlight, and 2,000 characters of notes are supported. A storage failure is shown rather than reported as saved.
- Imports resolve the selected event’s canonical revision/availability clock and invoke the existing `/api/fan/assistant/summary` service. Imported moments send a server-built, revision-pinned evidence window ending at the selected action. Existing server admission, grounding and model limits apply.
- **Footie’s Summary** is model-authored prose, not a selection of fixed sentences. A separate model call reviews every factual claim against the source packet. Code additionally checks citation IDs, goal ordinals, wrong own-goal net references, and invented dribbles when no carries are recorded. Rejected output is withheld; one corrective retry is allowed within the shared model-call limit. Automated semantic review is not a proof of factual correctness; the curated summaries also receive manual review.
- An import makes one summary request containing two model calls, or up to four if factual correction is needed. Opening or refreshing a highlight does not trigger paid inference. A failed request offers an explicit retry and never removes the saved replay. In-flight requests are deduplicated within the tab, have a 90-second client timeout, and cannot recreate a deleted highlight.
- The saved source signature contains the match fixture digest and the replay sequence. When loaded records change, old replay drawings and analysis are withheld until the user accepts the updated play. Updating retains written notes and clears frame-specific marks and old summaries.
- Drawings are stored in the 105 × 68 metre pitch coordinate system and attached to a paused replay frame. The same coordinates work on the rotated mobile pitch. Pointer capture keeps strokes continuous; cancellation discards the unfinished stroke. A text note provides an alternative to pointer drawing.

## Verification

```sh
npm --prefix frontend test -- --reporter=dot
npm --prefix frontend run build
```

Browser checks cover actual Azure summaries for an own goal, normal goal and pass; save/reload; drawing in desktop and rotated mobile layouts; duplicate prevention; navigation to Analyst Mode; and horizontal overflow at 390, 768 and 1440 pixels. This change is intentionally awaiting user review before publication.

## Preloaded highlight summaries

All six curated highlights have a prepared Azure OpenAI summary directly below the pitch widget. The model writes natural prose from the complete sequence; a separate model reviews the result against the data. Accepted prose is prepared once rather than making paid calls whenever a user opens a page. The card checks the complete event projection and final score against the prepared asset; mismatched records withhold stale analysis.

Validate source freshness offline:

```sh
.venv/bin/python scripts/prepare_preloaded_summaries.py
```

Regenerate when fixtures change (two model calls per changed highlight, with at most one corrective retry):

```sh
.venv/bin/python scripts/prepare_preloaded_summaries.py --generate
```

The assets contain verified prose, evidence projections and token counts, with no model endpoint or credentials. Preloaded summaries are currently English, including when the surrounding interface is Chinese. Ask Footie now sits within the pitch heading beside the replay title on wider screens and wraps within the same header on phones.

## Pitch notes and the assistant drawer

Preloaded replays now have **Pen**, **Clear**, and saved-frame controls at the bottom-right of the pitch canvas. Drawing pauses the replay. Clear removes only the selected frame’s strokes. Notes persist per source version in browser storage; updates to the source reset old-frame drawings. The existing imported-highlight replay also offers Clear.

Ask Footie uses the same 420-pixel right-side drawer as Match Centre on desktop and the existing bottom sheet on phones. The control remains in the pitch heading.
