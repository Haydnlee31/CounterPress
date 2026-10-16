# Deployment and operational telemetry

The `Deploy Azure` GitHub Action publishes a tested image to the existing registry
and updates the existing CounterPress app. Azure resource provisioning stays a
separate reviewed Bicep operation. The deployment preserves Cosmos, Event Hubs,
Web PubSub, managed identities, telemetry and zero-to-one scaling.

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
`repo:Haydnlee31/CounterPress:environment:azure-demo` from the GitHub token issuer.
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
It does not send new fixture events. Resolved Azure settings and command stderr
are not printed or uploaded as workflow artifacts. Model adaptation remains off.

## Bootstrap and rollback

Provision `infra/deployment-identity.bicep` once using an authorized local Azure
identity after reviewing its incremental what-if. Configure the GitHub environment
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

`infra/monitoring.bicep` creates a dedicated pay-as-you-go Log Analytics workspace,
a workspace transformation and the saved query **Streaming failures and delivery
timing** in category **CounterPress**. Deploy it first with `enableCollection=false`
to create the workspace, table and transformation, then with
`enableCollection=true` to associate the transformation and route console logs.
Keep the flag true on subsequent deployments. Enable app telemetry separately
with `useTelemetry=true` while preserving the other app parameters.

The app emits one compact JSON record per minute while a replica is running,
plus startup/shutdown records. The transformation retains only the fixed numeric
operational schema, rebuilding the JSON from an allowlist. Other console lines,
event bodies, exception text, URLs and tokens are not part of this retained schema.
HTTP access logging remains off; system/HTTP diagnostic categories are not enabled.
The existing Container Apps environment's log destination stays `azure-monitor`.

In Azure Portal, open **Log Analytics workspaces → counterpress-logs → Logs**.
Run the saved query, or paste `infra/monitoring/operations.kql`. It shows:

| Field | Interpretation |
| --- | --- |
| Processed | Successfully notified and checkpointed deliveries; includes duplicates. Not a count of new source events. |
| Rejected | Invalid deliveries durably quarantined and checkpointed. |
| Retries | Failed processing attempts retried on the same offset. |
| PublishFailures / CheckpointFailures | Failures in those pipeline stages; source may already be committed. |
| ConsumerFailures | Receive-loop failures before it reconnects. |
| MaxDeliveryAgeSeconds | Event Hubs enqueue-to-completion age, or age of the pending delivery. Not football occurrence time or measured browser latency. |
| MaxPendingSeconds | Time spent on the current delivery across retries. |
| ObservedBacklog | Latest sequence minus current sequence from the SDK's last received service metadata; an observed estimate, not a continuously polled queue-depth guarantee. |

Repeated failures, pending age above two minutes, or sustained backlog deserve
inspection. Use the existing quarantine and checkpoint runbook; do not skip a
failed offset, delete history or broaden RBAC as a shortcut. No rows can mean a
scaled-to-zero app, collection delay, daily-cap suspension or a monitoring failure;
it does not prove health. Metrics reset on process restart and are not an audit
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

Daily caps can overshoot and collection stops when reached. Transform processing,
other services and usage can add cost. The guard is not a hard spending limit;
review actual spend in Cost Management and remove unused services after the trial.
Log tables contain normal private Azure resource metadata even though application
records contain only numeric counters. Restrict workspace access and do not publish
raw query responses or Azure command logs.

References: [Azure OIDC authentication](https://learn.microsoft.com/en-us/azure/developer/github/connect-from-azure-openid-connect),
[GitHub environment controls](https://docs.github.com/en/actions/how-tos/deploy/configure-and-manage-deployments/manage-environments),
[Container Apps log routing](https://learn.microsoft.com/en-us/azure/container-apps/log-options),
[console table and transformations](https://learn.microsoft.com/en-us/azure/azure-monitor/reference/tables/containerappconsolelogs),
[workspace transformations](https://learn.microsoft.com/en-us/azure/azure-monitor/logs/tutorial-workspace-transformations-api),
[daily cap limitations](https://learn.microsoft.com/en-us/azure/azure-monitor/logs/daily-cap).
