# First local interface and evidence card

For a nontechnical walkthrough of the current hosted app, see the
[demo user guide](demo-guide.md).

The interface connects a React TypeScript screen to the deterministic Python replay.
The API supplies authoritative counts, eligibility, insight text and source records.
The browser controls its own playback position and renders the returned facts.

## Start locally

From the project root, terminal one:

```sh
UV_CACHE_DIR=.uv-cache uv sync --locked
UV_CACHE_DIR=.uv-cache uv run --frozen uvicorn counterpress.api.main:app --host 127.0.0.1 --port 8000
```

Terminal two:

```sh
cd frontend
npm ci --cache ../.npm-cache --no-audit --no-fund
npm run dev
```

Open <http://127.0.0.1:5173/>. Use a Node version supported by the package's
`engines` field; this build was checked with Node 26.5.0. Dependency versions are
locked in `package-lock.json`. Vite proxies `/api` to the backend on port 8000.
No credentials or cloud services are needed. Stage 5 creates local SQLite history;
see [durable history](history.md) for paths and correction ingestion. Stop both processes with Ctrl+C.

The screen starts paused at 48:00. Play runs at the selected speed; pause preserves
the position; reset returns to 48:00 and clears the card and evidence. The slider
supports seeking. **Go to comparison** jumps to 58:00. Select the control scenario
to see the explicit no-increase state. Switching scenarios resets playback.

Show evidence reveals the actual baseline and current source records. Selecting
an event on the pitch or in the table highlights its location and opens its full
JSON record. The table includes window membership, occurrence time, player ID,
coordinates and revision. Provenance includes the rule, evidence identity/version
and availability cutoff. The SVG plots only recorded locations, with no inferred
movement arrows. On narrow screens the evidence table scrolls horizontally.

## HTTP contract

- `GET /health`: existing process liveness endpoint.
- `GET /api/scenarios`: the two allowlisted scenario labels and playback bounds.
- `GET /api/scenarios/{scenario_id}/snapshot?at_ms=...`: state, current metrics,
  comparison windows/status and, when eligible, an Insight and EvidenceBundle.

`at_ms` is milliseconds since the second-half kickoff, so 180000 means 48:00,
540000 means 54:00, and 780000 means 58:00. Positions are accepted from 48:00 through the latest persisted availability,
initially 58:00. Correction deliveries can extend the horizon without extending the
fixed comparison windows. The snapshot includes `replay_end`.
Unknown scenarios return 404, invalid positions return 422, and unreadable or
invalid history or seed fixtures return 503. Error responses do not expose filesystem paths.
Snapshot responses use `Cache-Control: no-store`.

Each scenario is seeded once into SQLite. Each request selects its stored canonical
records through the cutoff and rebuilds the facts. Before 58:00 the comparison
status is `collecting`; it contains no insight or evidence packet. At 58:00, an
increase produces a factual card; the control produces `no_increase`. A later
correction can update the card or withdraw it. State references and metric IDs
exclude source records unavailable at the requested cutoff.

The fixture directory defaults to this checkout's `fixtures/`; override it with
`COUNTERPRESS_FIXTURE_DIR`. Existing persisted scenarios do not reload edited
fixture files. Submit new event revisions using `python -m counterpress.ingest`,
or choose a new database path to seed a different authored scenario.

## Evidence integrity and viewer scopes

The card and frozen EvidencePacket use the same calculated values and windows.
The bundle contains the exact source revisions supporting both counts. Stage 5
keeps a stable comparison identity and increasing insight/evidence revisions.
SQLite retains earlier bundles for audit and historical playback.

Snapshots include the latest `lifecycle` message available at the cutoff, with
`create`, `update` or `withdraw`, the publication revision and invalidated evidence
versions. The visible Insight and Evidence are null after withdrawal. Historical
evidence can be retrieved from
`GET /api/scenarios/{scenario_id}/evidence/{version}?at_ms=...`; a future version
returns 404 at an earlier cutoff. All snapshot/evidence responses disable caching.

The browser creates a new `scope_id` on seek, reset and scenario change, clears the
old display and fetches a full snapshot. It sends that ID with each request and
rejects responses for another scope or position. Within a scope it retains the
highest insight revision, including a withdrawal tombstone, and rejects older
history versions or playback positions. A delayed create/update cannot restore a
withdrawn card. An explicit rewind starts a new scope and can restore historical
facts. The server stores no shared viewer playhead.

Playback requests a snapshot every tick (250 ms) and paused views poll every two
seconds. A newly discovered correction horizon extends the slider and offers
**View latest corrections** without advancing a paused viewer. The correction
fixture extends playback to 58:15: 58:05 shows the updated card, 58:10 shows
**Insight withdrawn**, and 58:15 shows a newer card. The original 58:00 facts remain
available when seeking backward. An error pauses playback, clears displayed facts
and offers Retry; successful polling can recover the connection.

Rendering components remain independent of transport. The browser's presentation
clock does not change source timestamps, ingestion or calculations for other viewers.
The transport is full-snapshot HTTP polling, with no stream server. Snapshot reads
never call a model. Stage 6 adds optional approved adaptation text for an exact
evidence version; the browser checks its expiry and restores the factual wording
when it expires. See [adaptation](adaptation.md) for the explicit single-call CLI.

## Validation and captures

```sh
UV_CACHE_DIR=.uv-cache uv run --frozen pytest -q
npm --prefix frontend test
npm --prefix frontend run build
```

Backend checks cover endpoint cutoffs, frozen evidence, count/reference agreement,
control suppression, revisions, invalid requests and unavailable files. Durable
history tests cover restart, transaction rollback, duplicate writers and viewer isolation.
Frontend checks cover evidence inspection, reset/replay, control switching,
backward seeks, stale responses, retries, pause, speed changes, withdrawal tombstones
and correction-horizon discovery.

Manual browser checks use the real backend through Vite. Captures are stored in
`docs/screenshots/`: the completed evidence screen, the 54:00 state, the control,
and the narrow-screen layout. Typography optionally loads Google Fonts; system
fallback fonts keep the interface usable without that external font request.

Stage 5 captures: `stage5-withdrawal.jpg` and `stage5-restored-evidence.jpg`,
showing the persisted withdrawal and the newer card with p053 revision 3.
