# Shared Cosmos DB history

Stage 9 adds a Cosmos DB adapter behind the existing `HistoryStore` contract.
Local development defaults to SQLite. Azure activation and live restart evidence
are recorded separately in the progress log; offline tests are not proof of a
successful cloud deployment.

## Atomicity and replay

Each scenario identifies one synthetic match history and occupies one logical
partition (`/scenario_id`). A `head` item contains the schema and opaque commit
version. A `history` item contains the fixture metadata, append-only delivered
events, evidence/publication revisions, checkpoints and model/workflow audits.
All the existing identifiers, occurrence/availability times and window semantics
remain intact. This namespace is for the curated single-match scenarios; future
streaming must map its stable match IDs to the same storage scope deliberately.

A transactional batch creates or replaces both items together. Replacement
requires the head's ETag. A conflicting writer rereads and rebuilds from the
winner, up to four attempts. Callbacks must be pure and retry-safe; model calls
belong outside a storage transaction. Shared validation rejects history rewrites,
backward checkpoints, duplicate identities and records from a different match.
Ingestion still performs roster, possession, timing and revision validation.

Readers point-read the small head on every call. A bounded cache reuses validated
history only when its version matches that head. A changed version loads the body;
if a commit lands between the two reads, version mismatch triggers a bounded
retry. Readers never combine source records from one commit with another commit's
evidence. Session consistency applies; this is not a global strong-consistency
claim. ETag preconditions protect writes across client sessions. Storage failures
return sanitized 503 responses and never silently fall back to SQLite, cached
history or fixture-only output.

The current adapter rejects bodies above **1,800,000 serialized bytes** before
writing. Its two-operation batch stays below the Cosmos item/batch limit. All eight
current scenario histories fit. This is bounded demo storage, not an unbounded
full-match event store: segment the journal and evidence before larger feeds or
long audit histories. No TTL or data deletion is configured. A timeout can leave
a caller uncertain whether a commit succeeded; reread/replay the same deliveries
rather than inventing new event identities. Duplicate delivery remains idempotent.

Microsoft references: [transactional batches and limits](https://learn.microsoft.com/en-us/azure/cosmos-db/transactional-batch),
[optimistic concurrency](https://learn.microsoft.com/en-us/azure/cosmos-db/nosql/database-transactions-optimistic-concurrency),
[data-plane roles](https://learn.microsoft.com/en-us/azure/cosmos-db/nosql/reference-data-plane-security).

## Configuration and identity

| Variable | Meaning |
| --- | --- |
| `COUNTERPRESS_STORAGE` | `sqlite` (default) or explicit `cosmos` |
| `COUNTERPRESS_COSMOS_ENDPOINT` | Private runtime configuration; never a frontend/build variable |
| `COUNTERPRESS_COSMOS_DATABASE` | Defaults to `counterpress` |
| `COUNTERPRESS_COSMOS_CONTAINER` | Defaults to `histories` |
| `COUNTERPRESS_COSMOS_CLIENT_ID` | User-assigned history identity client ID in Azure |
| `COUNTERPRESS_COSMOS_AUTH` | `managed-identity` by default; explicit `azure-cli` for separately authorized local data access |

No Cosmos key or connection string is supported. Missing/invalid cloud config
fails startup. The app does not create databases or containers. API and ingestion
CLI use the configured store; the existing standalone model/workflow command-line
tools still use local SQLite and are not cloud workers.

`infra/cosmos.bicep` creates a single-region serverless account, database, history
container and a separate user-assigned history identity. Key authentication is
disabled; TLS 1.2 is required. Network access uses the authenticated public service
endpoint. Private networking is a later extension, not claimed here. A custom
container-scoped role allows metadata access plus item read/create/replace; it
does not allow item deletion, query execution, throughput or account management.
The existing registry-pull identity remains separate.

The existing app template keeps SQLite unless `useCosmos=true` is explicitly
passed. In that mode it binds the history identity and server-side configuration.
The app remains at zero-to-one replicas while the demo workload is bounded.
This does not enable hosted model adaptation or add a public ingestion endpoint.

## Deployment and costs

Set `CP_DB_REGION` to the reviewed database region. A different database region
adds cross-region latency and potential transfer costs; this is not multi-region
replication. Use the existing-group inventory, private target configuration, incremental
deployment and cost checks in [the deployment guide](deployment.md). Compile
`infra/cosmos.bicep`, review its what-if, then create the named deployment:

```sh
az deployment group what-if --resource-group "$CP_GROUP" \
  --template-file infra/cosmos.bicep --parameters location="$CP_REGION" databaseLocation="$CP_DB_REGION" --mode Incremental
az deployment group create --name counterpress-cosmos --resource-group "$CP_GROUP" \
  --template-file infra/cosmos.bicep --parameters location="$CP_REGION" databaseLocation="$CP_DB_REGION" --mode Incremental --output none
```

After the locked image passes tests and its code is reviewed, upload it to the
private registry. Preview `infra/app.bicep` with `useCosmos=true`, then deploy the
exact image digest. Allow time for data-role propagation. Record sanitized
read-back checks and run the live verification below. Never put resolved endpoint,
identity, subscription or account identifiers into committed command logs.

[Serverless Cosmos](https://learn.microsoft.com/en-us/azure/cosmos-db/serverless)
charges for consumed RUs and storage, with no provisioned-throughput minimum.
This stage uses the existing USD 5 storage/monitoring/networking allocation inside
the USD 75 total trial envelope; no budget increase is authorized. The checked
East US 2 retail request rate is USD 0.25 per million RUs, plus storage. A USD 1
planning target allows roughly four million RUs before storage; it is not a cap
or measured workload estimate. Writes replace the bounded history, so costs grow
with history size; unchanged browser polls read the small head only. Monitor actual
usage, close unused replay tabs and retain the trial spending limit. Cost data and
budget alerts can lag. Do not treat a missing/throttled cost result as zero spend.

## Verification

```sh
UV_CACHE_DIR=.uv-cache uv run --frozen pytest -q
bash scripts/test_container.sh counterpress:cosmos
```

Offline tests simulate atomic batches, ETag conflicts and failures. They cover
all eight scenario restarts without fixture files, correction-driven withdrawals,
duplicate delivery, distinct concurrent changes, head/body read races, cache
refresh, append-only/size guards, bounded conflicts and sanitized failures.

Run these commands **inside the configured Azure container**, with a unique
verification scope. Between commands, restart the hosted revision and wait for
readiness. The second process must restore the existing history without fixtures.

```sh
python -m counterpress.cosmos_check seed --scope YOUR-UNIQUE-SCOPE
# Restart the hosted revision, then:
python -m counterpress.cosmos_check verify --scope YOUR-UNIQUE-SCOPE
```

Expected successful output for each phase:

```text
PASS: 93 source records, create/update/withdraw/create, historical 4/3/none/2, immutable evidence, fixture-free recovery
```

The check uses an isolated verification partition, retains its small synthetic
history for inspection and does not change the public `increase` scenario. It
prints no endpoint, credentials or source payloads. Run the regular hosted HTTP
smoke too. A process restart check proves persistence across that restart; it does
not prove regional disaster recovery or an untested restore procedure.
