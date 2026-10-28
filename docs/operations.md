# Deployment and operational telemetry

The `Deploy Azure` GitHub Action publishes a tested image to the existing registry
and updates the existing CounterPress app. Azure resource provisioning stays a
separate reviewed Bicep operation. The deployment preserves Cosmos, Event Hubs,
Web PubSub, managed identities, telemetry and the existing replica minimum (zero or one), with a maximum of one.

Live release and retained-metric checks are recorded in
[verification/operations-live.json](verification/operations-live.json).

## Deploy a reviewed change

1. Merge a PR through the existing required checks.
2. Wait for the `CI` run on that exact `main` commit to pass.
3. Open **Actions → Deploy Azure → Run workflow → main**.
4. Check the deployment summary for the source commit, image digest and successful
   public HTTPS and historical-correction checks.

Equivalent CLI:

```sh
gh workflow run deploy.yml --repo Haydnlee31/CounterPress --ref main
```

This is manual deployment, not automatic deployment on every merge. The
`azure-demo` environment permits the `main` branch only, not tags. The workflow
also refuses a stale main commit or one without successful push CI. Deployments
are serialized and do not cancel an in-progress update. No additional human-review
gate is configured for this single-owner hackathon; branch protections and manual
dispatch provide the release controls. A team production environment should add
an independent required reviewer.

The job rebuilds and smoke-tests the container without cloud configuration, then
uses GitHub OIDC with a dedicated Azure user-assigned identity. Azure trusts only
`repo:Haydnlee31@<owner-id>/CounterPress@<repository-id>:environment:azure-demo`
from the GitHub token issuer. This repository uses GitHub’s immutable subject
format; the IDs are taken from the repository API and must match the emitted claim.
There is no client secret or service-principal password. Environment secrets hold
client, tenant and subscription IDs plus private target metadata; none are model
credentials. They are masked in logs and never passed into Docker builds.

The identity has app-scoped read/write, registry-scoped AcrPush/Reader and existing
environment Reader. It cannot assign roles or directly access Cosmos, Event Hubs,
Blob data or the model. **App write can change the app configuration and deployed
code**, so this is a trusted deployment identity, not an Azure-enforced image-only
permission. The workflow itself only updates the image and verifies all other
runtime configuration stayed unchanged. Treat write access to protected main and
GitHub environment administration as privileged.

The script uses an immutable registry digest, waits for the new revision to become
ready, then checks the public app and the saved 4/3/withdrawn/2 correction history.
Readiness must identify the specifically requested revision; an older ready
revision cannot satisfy the gate.
It does not send new fixture events. Resolved Azure settings and command stderr
are not printed or uploaded as workflow artifacts. Model adaptation remains off.

## Bootstrap and rollback

Provision `infra/deployment-identity.bicep` once using an authorized local Azure
identity after reviewing its incremental what-if. Supply the public immutable
`githubOwnerId` and `githubRepositoryId` from `gh api repos/Haydnlee31/CounterPress`;
do not switch GitHub back to a legacy subject format. Configure the GitHub environment
with a custom deployment branch policy allowing branch `main`, and these secrets:

| Environment secret | Source |
| --- | --- |
| `AZURE_CLIENT_ID` | Dedicated deployment managed identity client ID |
| `AZURE_TENANT_ID` | Existing tenant ID |
| `AZURE_SUBSCRIPTION_ID` | Existing trial subscription ID |
| `CP_AZURE_TARGET` | JSON with `resource_group` and `registry_name` only |

Do not put resolved values in repository files. No model API key or model endpoint
belongs in any of these values. A local CLI owner provisions identity/RBAC;
the deployment workflow has no authority to provision or expand its own roles.

A failed verification makes the workflow fail. It does not automatically revert
source history or silently redeploy another image. For rollback, use the prior
successful run's digest and the reviewed manual `infra/app.bicep` deployment with
`useCosmos=true`, `useStreaming=true`, `useTelemetry=true`. Review what-if and keep
the same region and name prefix. The active image digest is also readable in Azure.
The temporary runner-local rollback file is intentionally not a public artifact.
A code rollback does not undo Cosmos commits or Event Hubs checkpoints.

## Monitor ingestion

`infra/monitoring.bicep` creates the pay-as-you-go Log Analytics workspace with
30-day retention and a daily ingestion guard. For a new installation, leave
`enableCollection=false`; console export is not the active collection path.
Then deploy `infra/telemetry-ingestion.bicep` to create the typed
`CounterPressOperations_CL` table, a Direct data collection rule, and the saved
query **Acknowledged streaming operations** in category **CounterPress**.
It grants the streaming managed identity Monitoring Metrics Publisher on that
rule only. No monitoring key is stored. Finally deploy the app with
`useTelemetry=true`, preserving Cosmos, streaming and the current image digest.
The app template resolves the private ingestion endpoint and rule ID at deployment.

The app submits one fixed numeric record per minute while a replica is running,
plus startup/shutdown records, using the Azure Monitor Logs Ingestion API. Each
upload requires HTTP 204 acknowledgement. Records contain a timestamp, a fixed
schema marker and allowlisted numeric counters; event bodies, exception text,
URLs and tokens are excluded. Upload errors are bounded and sanitized and do not
stop event processing. Failed windows are not retried or durably buffered;
`ExportFailures` appears in the next successful window. Counters are operational
signals, not a lossless ledger. The app also writes the same numeric record to its
console for local diagnosis. HTTP access logging remains off.

The earlier environment diagnostic export produced no retained records in live
checks, so it is replaced by direct ingestion. Disable/delete its
`counterpress-ops` diagnostic setting when migrating an existing installation;
do not enable that route alongside direct ingestion. Its empty console table and
workspace transform are not used by the direct custom stream.

In Azure Portal, open **Log Analytics workspaces → counterpress-logs → Logs**.
Run the saved query, or paste `infra/monitoring/direct-operations.kql`. It shows:

| Field | Interpretation |
| --- | --- |
| Processed | Successfully notified and checkpointed deliveries; includes duplicates. Not a count of new source events. |
| Rejected | Invalid deliveries durably quarantined and checkpointed. |
| Retries | Failed processing attempts retried on the same offset. |
| PublishFailures / CheckpointFailures | Failures in those pipeline stages; source may already be committed. |
| ConsumerFailures | Receive-loop failures before it reconnects. |
| ExportFailures | Failed or timed-out metric uploads since the prior window; gaps may undercount processing. |
| MaxDeliveryAgeSeconds | Event Hubs enqueue-to-completion age, or age of the pending delivery. Not football occurrence time or measured browser latency. |
| MaxPendingSeconds | Time spent on the current delivery across retries. |
| ObservedBacklog | Latest sequence minus current sequence from the SDK's last received service metadata; an observed estimate, not a continuously polled queue-depth guarantee. |

Repeated failures, pending age above two minutes, or sustained backlog deserve
inspection. Use the existing quarantine and checkpoint runbook; do not skip a
failed offset, delete history or broaden RBAC as a shortcut. No rows can mean a
scaled-to-zero app, collection delay, daily-cap suspension or a monitoring failure;
it does not prove health. New custom tables can take several minutes to show
the first records; an upload acknowledgement alone is not proof of retention.
Metrics reset on process restart and are not an audit
ledger. Cosmos and checkpoints remain the durable sources of truth.

No email/webhook alert, Application Insights auto-instrumentation, always-on
monitoring worker or paid dashboard tier is enabled in this increment. The saved
KQL query provides on-demand operational visibility without a recurring alert-rule
charge. It does not promise unattended incident response.

## Cost and privacy limits

The workspace retains 30 days and has a 0.025 GB/day ingestion guard. East US
Analytics ingestion was checked at USD 2.30/GB on 16 October 2026. At the nominal
guard, 28 days is about USD 1.61 before other charges; normal one-record-per-minute
telemetry should use less. This remains within the existing USD 5 combined storage,
monitoring and network allowance and USD 75 total envelope. There is no budget
increase. Current actual spend could not be retrieved from the cost API.

Daily caps can overshoot and collection stops when reached. Other services and usage can add cost. The guard is not a hard spending limit;
review actual spend in Cost Management and remove unused services after the trial.
Log tables contain normal private Azure resource metadata even though application
records contain only numeric counters. Restrict workspace access and do not publish
raw query responses or Azure command logs.

References: [Azure OIDC authentication](https://learn.microsoft.com/en-us/azure/developer/github/connect-from-azure-openid-connect),
[Immutable GitHub subjects](https://github.blog/changelog/2026-04-23-immutable-subject-claims-for-github-actions-oidc-tokens/),
[GitHub environment controls](https://docs.github.com/en/actions/how-tos/deploy/configure-and-manage-deployments/manage-environments),
[Container Apps log routing](https://learn.microsoft.com/en-us/azure/container-apps/log-options),
[Logs Ingestion API](https://learn.microsoft.com/en-us/azure/azure-monitor/logs/logs-ingestion-api-overview),
[Ingestion API sample and initial delays](https://learn.microsoft.com/en-us/azure/azure-monitor/logs/tutorial-logs-ingestion-code),
[daily cap limitations](https://learn.microsoft.com/en-us/azure/azure-monitor/logs/daily-cap).


## Judging-period warm replica

During judging, the production app uses **minimum 1 / maximum 1** so an idle app does not scale to zero. This is a scaling-only change: the image, model configuration, storage, identities and event-stream rules remain unchanged. Image deployments and staging preserve the existing minimum; their configuration invariants reject an unrequested change. Provisioning templates retain their scale-to-zero default and should not be reapplied to override the judging setting.

The judging window closes on **11 November 2026 at 15:59 Singapore time**. A Codex follow-up is scheduled for 16:10 to review the deadline and restore the previous minimum of zero, unless subsequent instructions or an extended deadline require keeping the app warm. This follow-up depends on the automation host having Azure access; it is not an Azure-side expiry policy.

To inspect scaling without reading credentials:

```sh
az containerapp show -g counterpress-dev -n counterpress \
  --query '{ready:properties.latestReadyRevisionName,min:properties.template.scale.minReplicas,max:properties.template.scale.maxReplicas}' -o json
```

To restore scale-to-zero after judging, change **only** the minimum, then verify the new ready revision, traffic and public health:

```sh
az containerapp update -g counterpress-dev -n counterpress --min-replicas 0 \
  --query '{latest:properties.latestRevisionName,ready:properties.latestReadyRevisionName,min:properties.template.scale.minReplicas}' -o json
curl --fail https://counterpress.icyplant-0eb80d8e.eastus.azurecontainerapps.io/health
```

Do not disable ingestion, delete replicas or change the application image to adjust the idle scaling policy. A successful update response can precede the new revision becoming ready; check that the requested revision is ready before considering the rollout complete.
