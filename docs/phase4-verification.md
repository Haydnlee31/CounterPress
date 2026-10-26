# Isolated personalized revision verification

Status: implementation prepared locally on 26 October 2026. Hosted outcomes are
recorded separately; code and local doubles do not establish Azure delivery.

The public career fixture has immutable replay digests. Restoring a withdrawn
goal restores statistics, not its authored animation. Do not send these test
corrections to the public `deliveries` hub or `histories` container.

## Boundaries

The temporary `counterpress-phase4` app uses the same checksum-pinned fixtures and
compiled frontend, with a separate Cosmos `histories-phase4` container, Event Hub
`deliveries-phase4`, checkpoint and quarantine Blob containers ending `-phase4`,
and Web PubSub hub `counterpress_phase4`. A dedicated managed identity has access
to those data resources; the existing pull identity only downloads the image.
There are no model keys, AI/voice/Studio endpoints or inference calls.

The Web PubSub role is service-scoped; its hub separation is enforced by the
server configuration, not a separate Azure IAM boundary. This follows the
[Microsoft managed-identity authorization model](https://learn.microsoft.com/en-us/azure/azure-web-pubsub/howto-authorize-from-managed-identity).
Cosmos item access is container-scoped and uses point reads/create/replace only;
[metadata permission](https://learn.microsoft.com/en-us/azure/cosmos-db/nosql/reference-data-plane-security)
is included for the SDK. No new service tier or throughput unit is provisioned.

The normal production deployment guard rejects these isolated destinations.
The verifier refuses a mixed configuration and exposes only read-only APIs.
Its operational counters are not AI-agent traces or proof of model reasoning.

## Build and deploy

1. Require exact-commit CI, including backend tests, career ledger audit, frontend
   build, container smoke and Bicep compilation.
2. Dispatch **Build isolated Phase4 image** on that main commit. It uses existing
   GitHub federation to build/publish only. It does not acquire deployment rights
   or change either application. Record the reported commit and image digest.
3. With the existing authorized Azure CLI account, prepare a private receipt:

```sh
python scripts/phase4_azure.py plan --commit "$BUILD_COMMIT" \
  --image-digest "$IMAGE_DIGEST" --state /private/tmp/footie-phase4-receipt.json
python scripts/phase4_azure.py deploy --apply \
  --state /private/tmp/footie-phase4-receipt.json
python scripts/phase4_azure.py verify --state /private/tmp/footie-phase4-receipt.json \
  --proof /private/tmp/footie-phase4-proof.json
```

The plan requires all twelve exact targets to be absent. Its template hash,
image/tag binding, intended cleanup manifest and production fingerprint are
persisted before mutation. Plans expire after four hours. The `expiresOn` tag
is descriptive; it does not automatically stop or delete resources. Keep the
test bounded and clean up promptly within the US$125 project allowance.

## Verify delivery

Set `FOOTIE_PHASE4_TEST_URL` and `FOOTIE_PHASE4_PRODUCTION_URL` privately from
validated app metadata. Never commit endpoints, access tokens or local receipts.
The verifier binds the test origin to the control-plane proof using a hash.

```sh
.venv/bin/python scripts/check_phase4_hosted.py baseline \
  --state /private/tmp/footie-phase4-observations.json \
  --proof /private/tmp/footie-phase4-proof.json \
  --output /private/tmp/footie-phase4-baseline.json
```

Open the equalizer highlight in two browsers with casual and analyst preferences
before applying any correction. Pause both at the same completed moment. For
`correction`, `retraction`, `duplicate`, `restoration`, then `late`, run `prepare`
with the same state/proof and a distinct output file. This only writes a locally
validated event envelope. Review it, start the bounded `watch` command, and send
it from the **isolated app's dedicated identity** using the existing
`counterpress.streaming.send_career --send` module. Validate the isolated runtime
configuration before invoking that sender. Never invoke it inside the public app.

Run `check --step ...` after each send. Expected generations are 1, 2, 2, 3, 4.
The harness checks both audience variants, unchanged historical observations,
expiry, actual processed-counter increments (including duplicate delivery), and
unchanged production generation, match fingerprints and highlight catalog.
`watch` verifies a receive-only WebSocket hint, reconnects, and rereads authority;
it never trusts a notification as football evidence. Keep tokens in memory only.

Inspect both browser views: the original clock and facts remain fixed until
explicit review, withdrawn animation stays hidden, and restored cards reflect
the new evidence. Read the actual checkpoint with `check_phase4_checkpoint.py`
inside the isolated container before cleanup. Save only sanitized results.
Successful API checks alone do not prove browser recovery or durable checkpoints.

## Cleanup and recovery

Stop sending, verify the consumer caught up, save evidence, then:

```sh
python scripts/phase4_azure.py cleanup --apply --discard-test-data \
  --state /private/tmp/footie-phase4-receipt.json
```

Cleanup requires the matching ARM deployment to be terminal, checks ownership
again while resuming, deletes only the exact initially absent test targets, and
rechecks production throughout. If deployment times out, do not start deletion
while ARM is still creating resources. Use the same prewritten receipt once the
deployment is terminal; never broaden deletion to the resource group. Public
career ingestion remains disabled until the hosted verification gate passes and
an explicit production rollout is completed.
