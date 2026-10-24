# Review a Footie revision without switching production

This workflow is implemented locally and tested with an offline Azure state
machine. **It has not been activated or verified against Azure yet.** It creates
no service and does not promote a candidate. The normal deployment workflow is
unchanged and still deploys directly to production in Single revision mode.

## Before staging

- Merge the reviewed commit to `main` and require successful exact-commit CI.
  Staging builds and smoke-tests the Linux/amd64 image before Azure login, then
  repeats the current-main CI check before pushing its digest-pinned image.
- The existing `azure-demo` GitHub environment and OIDC configuration are reused.
  `CP_AZURE_TARGET` remains a secret. No model keys, model endpoints, raw Azure
  configuration, access tokens, or rollback snapshots are printed or uploaded.
- The existing app-scoped deployment role must permit
  `Microsoft.App/containerApps/read`, `Microsoft.App/containerApps/write`,
  `Microsoft.App/containerApps/revisions/read`, and
  `Microsoft.App/containerApps/revisions/deactivate/action`. The staging script
  never assigns these permissions. Apply the separately reviewed identity change
  before running it. A failed revision read stops before app mutation.
- Production must be healthy, in Single mode, with one unambiguous 100% route,
  no other active revision, existing Cosmos storage, and zero-to-one replica
  limits. Unexpected runtime settings/scalers stop the operation.
- Keep the US$125 project envelope. Two revisions can temporarily run one
  replica each; 0% traffic does not mean free hosting. Azure budget alerts are
  notifications, not a shutdown control.

## Stage and review

In GitHub Actions, choose **Review Azure candidate**, branch **main**, operation
**stage**. Leave the cleanup revision inputs blank. The workflow shares the same
concurrency lock as production deployment; those operations cannot run together.

The script:

1. Reads the healthy production revision and prints its name, the deterministic
   candidate name, and an explicit cleanup command before app mutation.
2. Uses one configuration-only JSON Merge PATCH to pin that exact production
   revision at 100% and enable Multiple mode atomically. This does not create a
   revision. It verifies the pin before changing the image/template. It never
   leaves `latestRevision=true` as the routing policy during staging.
3. Creates the candidate from the immutable production template with only the
   reviewed image, revision suffix and isolation changes: streaming is off,
   career streaming is off if configured, and the Event Hub scaler is removed.
   HTTP scaling remains at zero-to-one replicas. All identities, secrets, model
   configuration, Cosmos configuration, assistant admission partition, and
   hourly/daily allowances are preserved.
4. Polls the **specific candidate revision**, including delayed appearance,
   successful provisioning, active status and healthy probes. A different
   `latestReadyRevisionName` cannot satisfy readiness. It checks the candidate
   template against the expected transformation and verifies production stays
   pinned throughout.
5. Assigns `footie-review` to the candidate at **0% application traffic**, keeping
   the original revision at 100%.

Open Azure Portal → Container Apps → `counterpress` → **Revisions and replicas** →
the printed candidate revision → **label URL** for `footie-review`. Use that URL
for review; the ordinary app URL still serves production.

**The label URL is public and is not an authentication or access-control
boundary.** Anyone with that URL can reach the existing application routes and
consume the existing shared allowance. Existing Entra-protected routes retain
Entra protection. This approach isolates production routing and background
consumption; it is not a private staging environment or a separate data copy.
Do not distribute the label broadly. Remove it by running cleanup promptly.

The workflow makes **no live AI inference request**. After readiness, perform a
separately bounded check through the candidate URL: one supported answer, correct
revision/evidence context, and its sanitized trace. Confirm current shared model
allowance before any paid checks. Follow with the approved release smoke cases;
record findings separately from the offline results. Managed-identity activation
is not part of this workflow; current model authentication is preserved.

Candidate streaming is deliberately disabled: it cannot take production Event
Hub partition ownership, publish revision notices, or run the career correction
consumer. Its streaming/revision-negotiation UI will therefore differ. Validate
those integrations through the controlled production rollout after cleanup;
do not interpret this staging review as an end-to-end streaming test.

## Cleanup and restoration

Run **Review Azure candidate** again on **main**, operation **cleanup**. Paste the
original production and candidate revision names printed by staging. Cleanup
requires no image build, registry push or currently successful CI, so a later CI
failure cannot block restoration. It still uses the protected GitHub environment
and the shared deployment concurrency lock.

The equivalent command in an already authorized operator environment is:

```sh
python3 scripts/stage_azure.py cleanup \
  --production counterpress--gh-ORIGINAL_RUN-ATTEMPT \
  --candidate counterpress--stage-STAGING_RUN-ATTEMPT
```

Use the actual numeric run/attempt values from the staging output. Keep
`CP_AZURE_TARGET` in the existing private environment; do not paste its content
into a terminal transcript or chat.

Cleanup validates the supplied names against Azure's immutable revision
configuration and the current production route. It refuses unexpected active
revisions, a changed candidate template, changed allowances, unrelated latest
revisions, or traffic sent to the candidate. It then:

1. Removes the public review label while retaining the original production pin.
2. Recreates the **original production image and settings** as a fresh
   `restore-…` revision. Production traffic stays on the original until this
   exact restoration revision passes readiness. This matters because simply
   changing to Single mode could otherwise select the newer candidate.
3. Routes 100% to the healthy restoration revision, explicitly deactivates the
   candidate, confirms it is inactive, then returns to Single mode with the
   restored revision as latest. It verifies the original template and unchanged
   app-scoped identity/configuration again.

The old and restoration revisions can briefly run identical streaming consumers
while restoration becomes healthy. They use the existing consumer group and Blob
checkpoint coordination, so expect a normal ownership rebalance during this
controlled handoff. The candidate never runs those consumers. Shared admission
reservations and pending leases are not deleted, refunded, or moved.

An interruption before candidate creation can return the original revision to
Single without creating a restoration revision. An interruption during restoration
can resume against the same deterministic restoration revision. After completed
cleanup, Azure's existing inactive-revision retention may purge the original;
if so a later redundant cleanup refuses rather than guessing an old template.

If any safety check fails, the script stops with a sanitized error. It does not
promote the candidate, automatically undo an unrelated operator's changes, reset
limits, or fall back to a different resource. Read the printed cleanup identities
and inspect routing before retrying cleanup. If Azure accepted a request but the
client lost its response, inspect the live revision state; failure is not proof
that no cloud change occurred. Do not switch traffic to “latest” manually.

Once cleanup is confirmed, the ordinary **Deploy Azure** workflow may deploy the
reviewed commit using its existing production safeguards. Promotion from staging
is deliberately not implemented here.

## Budget and trial boundary checked 24 October 2026

The resource-group budget reported US$4.73 actual spend and US$37.90 forecast
against US$125; these are delayed accounting values. The credit lot's US$200
closed balance is a last-invoice balance, not real-time remaining credit.
Actual credit expiry is **13 November 2026 at 14:09:17 Singapore time**
(06:09:17 UTC), earlier than the budget's 14 November 00:00 UTC end. Use the
credit expiry for cleanup planning. Recheck current billing before activation.

## Azure readback normalization

The read-only activation preflight on 24 October found that the application and
its immutable revision serialize equivalent settings differently. Comparison now
normalizes only the observed, documented cases: omitted/null/empty `value` beside
an existing nonempty secret reference; ordering of distinctly named scale rules;
omitted/null KEDA cooldown and polling values versus their 300/30-second defaults;
and omitted/null ephemeral storage versus 2 GiB for this single-container,
no-init-container, 0.5-vCPU/1-GiB replica shape.

This changes comparison only. Candidate and restoration PATCH templates still
come from the immutable original revision. Nondefault scale/storage settings,
CPU/memory, replica limits, secret references or nonempty values, probes, scaler
identities/thresholds, and model allowances remain significant differences.
Other replica shapes do not receive inferred storage defaults. Duplicate rule
names are rejected. This is not a general relaxation of template parity.

Sources: [KEDA defaults in the 2025-07-01 API](https://learn.microsoft.com/en-us/rest/api/resource-manager/containerapps/container-apps/get?view=rest-resource-manager-containerapps-2025-07-01)
and [ephemeral storage by vCPU allocation](https://learn.microsoft.com/en-us/azure/container-apps/storage-mounts?pivots=azure-portal).

## Sources and local verification

The 2025-07-01 update API explicitly uses JSON Merge Patch. The script sends only
routing/mode or revision template fields; it does not round-trip the secret
collection with omitted values.

- [Container Apps JSON Merge PATCH](https://learn.microsoft.com/en-us/rest/api/resource-manager/containerapps/container-apps/update?view=rest-resource-manager-containerapps-2025-07-01)
- [Microsoft blue-green revision and label guidance](https://learn.microsoft.com/en-us/azure/container-apps/blue-green-deployment?pivots=azure-cli)
- [Revision modes, readiness and labels](https://learn.microsoft.com/en-us/azure/container-apps/revisions)
- [Revision deactivation stops its replicas](https://learn.microsoft.com/en-us/azure/container-apps/revisions-manage)

```sh
.venv/bin/python -m pytest -q tests/test_staging_guard.py tests/test_deployment_guard.py
```

Offline tests model the merge-patch/routing state transitions, preservation of
shared configuration, candidate isolation, delayed revision appearance, failures
and resumable cleanup. They cannot establish actual Azure RBAC, ARM
normalization/propagation, label reachability, hosted health, or inference success.
Those remain explicit activation checks.
