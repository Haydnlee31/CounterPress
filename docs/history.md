# Durable history and corrections

Stage 5 stores the original fixture manifest, append-only Event revisions and
versioned insight/evidence publications in SQLite. `HistoryStore` is the small
storage boundary; `SQLiteHistoryStore` is its local implementation. No new Python
or frontend dependencies are required. Azure is not used.

## Startup and persistence

Start the API and frontend using the README commands. The API creates
`var/counterpress.sqlite3` on first history access. `COUNTERPRESS_DB_PATH` selects
another SQLite file; `COUNTERPRESS_FIXTURE_DIR` selects the initial fixture directory.
Relative paths resolve from the working directory. Database files are ignored by Git.

Each scenario is seeded once. Editing a fixture after seeding does not rewrite
history. Use a new database path to try a different authored seed. Once seeded,
that scenario can recover from the database even if its fixture file is unavailable.
The small replay rebuilds match state from stored canonical records on each read;
there is no lossy checkpoint or assumed contiguous source sequence.

The application factory accepts an explicit database path for integration tests.
`create_app()` without a path uses an isolated in-memory store; the exported
Uvicorn `app` uses the persistent path described above.

## Append corrections

The local CLI uses the same storage interface as the API. With the API's default
database path, run from the project root:

```sh
UV_CACHE_DIR=.uv-cache uv run --frozen python -m counterpress.ingest increase fixtures/faults/recovery_corrections.json
```

Use `--db PATH` when the API uses a different database. The four authored revisions
have the following independently checked results:

| Availability | Source revisions | Current count | Publication |
| --- | --- | --- | --- |
| 58:00 | Original fixture | 4 | create r1 |
| 58:05 | p053 r2, x=65 | 3 | update r2 |
| 58:10 | p064 r2 and p075 r2, x=65 | 1 | withdraw r3 |
| 58:15 | p053 r3, x=72 | 2 | create r4 |

Baseline count stays one; both comparison windows remain `(48:00,53:00]` and
`(53:00,58:00]`. Later availability changes our knowledge of these fixed windows,
not their bounds. The later match times extend the replay slider to 58:15.
A paused viewer is offered **View latest corrections** and is not moved automatically.
At 58:10 the card and markers disappear; seeking back to 58:00 restores the original
1-to-4 comparison. At 58:15 the new card cites p043 r1, p053 r3 and p086 r1.

Delivering the array again, even from a new process, adds zero records or messages.
An exact duplicate preserves its source identity and payload. Conflicting identities,
reused source sequences, unstable occurrence order, invalid actors or contradictory
possession reject the entire batch. SQLite commits source records and their derived
publications together; concurrent writers serialize using `BEGIN IMMEDIATE`.
Readers see a consistent committed history.

This local ingestion adapter treats `available_at` as actual availability on the
synthetic timeline. A new delivery cannot backdate it before the persisted replay
horizon (initially 58:00). Occurrence may be earlier. Equal availability is allowed;
records with the same availability in one batch are projected together. Separate
commits at the same time remain ordered by publication revision, and a snapshot
at that time returns the newest committed publication. Older evidence stays
addressable by version. Arbitrary historical imports need a separate rebuild workflow.

Sequence gaps and out-of-order source sequence numbers are supported. The maximum
source sequence is identity metadata, not a durable delivery checkpoint. The store
tracks each event/revision independently. A correction moving an occurrence outside
a window supersedes the old revision before the window is filtered.

## Publication and viewer contract

A stable insight/evidence identity represents one match, subject, metric rule and
pair of windows. Publication revisions and evidence versions increase together.
A lifecycle message contains `create`, `update` or `withdraw`, its availability,
the frozen evidence bundle and its exact source revisions. `withdraw` has no Insight.
Updates also occur when a supporting source revision changes without changing counts.
Previously excluded records are reconsidered on correction.

Every replacement identifies the older evidence version in `invalidates`. Stage 6's first increment stores approved wording attempts against evidence versions;
there are no audience variants or recaps yet. Later stages must key those artifacts to the
exact evidence version, discard invalidated artifacts and compare versions again
before committing an asynchronous result. Stored historical evidence is retained
for audit and rewind; it is never overwritten by an invalidation.

`GET /api/scenarios/{scenario}/snapshot?at_ms=780000&scope_id=viewer-example` returns
a full authoritative snapshot with the latest lifecycle message available at that
cutoff, plus `history_version` and `replay_end`. `history_version` counts committed
source records, including revisions; it is producer metadata, not a football metric.
Polling full snapshots permits recovery after missed publications without a stream
resume protocol. `GET /api/scenarios/{scenario}/evidence/{version}?at_ms=...` retrieves
immutable evidence only when that publication was available by the requested cutoff.
The scenario path scopes the stable evidence identity; no arbitrary file paths are accepted.

Each seek, reset or scenario change creates a new client scope and fetches its
snapshot. Forward playback and paused polling keep that scope. Within it, the client
rejects an older history version, earlier playback time or lower insight revision.
It retains the withdrawal revision even when the visible card is null. A new scope
can accept an older historical revision; responses for an obsolete scope are ignored.
A scope is a presentation correlation token, not authentication. No viewer changes
the producer's event journal or another viewer's playhead.

## Verification and limits

`tests/test_history.py` covers restart without fixtures, exact historical cutoffs,
duplicate delivery after restart, update/withdraw/re-create, same-count source
changes, newly qualifying sources, corrections outside the window, source sequence
gaps, atomic rejection, concurrent duplicate writers, two viewers and database errors.
`frontend/src/App.test.tsx` checks paused polling, withdrawal tombstones, stale updates,
new-scope rewind and discovery of a longer horizon alongside the existing UI tests.
Exact commands, output and browser checks are recorded in `docs/archive/development-history.md`.

This is a small local implementation with full history reads and full state rebuilds.
It has no stream transport, authentication, cloud replication, database migration
framework or retention pruning. The single-call model adapter is described in [adaptation](adaptation.md); agents,
audience variants, recaps and Azure deployment remain subsequent stages. Existing source action types and one-period
replay limits are unchanged.


## Cloud storage

Local SQLite remains the default. The hosted app now selects the shared Cosmos DB
adapter through explicit server-side configuration. It preserves this history and
publication contract using atomic batches and ETag concurrency. See [Cosmos DB
history](cosmos.md) for the bounded item size, identity permissions, costs and live
restart checks. Standalone model/workflow CLIs remain local SQLite tools.
