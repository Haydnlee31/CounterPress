# Footie multi-agent monitoring in Microsoft Foundry

Footie continues to execute inside the existing `counterpress` Azure Container
App. Foundry registers the external agents and displays their OpenTelemetry
traces. Registration does not proxy user traffic, host Python, or grant the
agents more access to football data. It does not create a second model runtime.

## Components and identities

| Component | Responsibility |
| --- | --- |
| Container App `counterpress` | FastAPI, routing, specialist agents, deterministic tools, admission and evidence validation |
| Foundry project `counterpress-dev-01/CounterPress` | External-agent registration and trace exploration |
| Application Insights `counterpress-agents` | Sanitized traces, linked to existing `counterpress-logs` workspace |
| Foundry connection `footie-agent-monitoring` | Associates that component with the project |
| Existing `counterpress-history` managed identity | Entra-authenticated telemetry export; Monitoring Metrics Publisher on this component only |
| Existing `counterpress-deploy` identity | Reader on the monitoring component and history identity metadata, for guarded OIDC release configuration |
| Cosmos history control partition | Existing shared inference allowance, concurrency and cache admission |

The three external registration IDs exactly match exported `gen_ai.agent.id`:
`footie-orchestrator`, `footie-match-analyst`, `footie-career-analyst`.
External registration and its Foundry UI support are currently a Microsoft
preview. If that UI is unavailable, the same traces remain queryable in
Application Insights; runtime execution does not depend on Foundry registration.

## What is recorded

Explicit request, routing, specialist-query, tool, validation and final-selection
spans can carry fixed agent roles, operation/status enums, generated request IDs,
provider/tool/claim counts, token counts, cache/fallback flags and timing. Parent
span and trace IDs connect the work. The implementation uses the Azure Monitor
OpenTelemetry exporter with a final allowlist before transmission.

Raw questions, answers, tool arguments/results, exception messages, model
endpoints, model deployment names, connection strings, credentials, player names,
HTTP URLs and automatic SDK spans are excluded. Exported resource metadata is
only `service.name=footie-agents`. The final Azure envelope retains only the fixed
cloud role and operation name/trace/parent IDs; hostnames, device IDs, role-instance
names and SDK-added resource metrics are excluded. No HTTP, logging or browser
auto-instrumentation is installed. Sensitive GenAI message capture is not needed. This intentionally
limits portal transcript inspection and content-based evaluation: the benchmark
runner provides correctness evidence separately. Do not enable raw content
capture in the production app to make the portal more detailed.

The Azure exporter currently has no public envelope-processing callback. Its
conversion adds host metadata after OpenTelemetry span processing, so a small
subclass sanitizes the final envelope and disables independent resource/event
envelopes. These are private SDK hooks tested against exporter `1.0.0b58`, pinned
in `uv.lock`. Before updating that lock, rerun `tests/test_agent_observability.py`:
its actual SDK conversion/export tests reproduce the original host-tag leak and
verify the outgoing envelope, correlation and absence of resource metrics with
transmission mocked. An SDK upgrade requires reviewing these hooks again.

Sampling defaults to 100% for the bounded pilot. It is configurable with
`COUNTERPRESS_AGENT_TRACE_SAMPLE_RATIO` from 0 to 1. The exporter has a bounded
queue, no disk retry cache, no independent SDK-stats channel, and sanitized failure
logs. Its failure does not block football answers. A missing trace can result from
sampling, queue drops, exporter outage or ingestion caps; it is not proof that the
agent was never called.

## Provision and bind

Deploy `infra/agent-monitoring.bicep` to the existing resource group after
reviewing the planned changes. It adds one workspace-backed Application Insights
component, its scoped publisher role assignment, two scoped metadata Reader
assignments for the deployment identity, and the project connection. It
does not modify model deployments, Container App capacity or workspace limits.
Application Insights local authentication is disabled. The Foundry connection
uses its documented `AppInsights`/`ApiKey` connection schema, but the application's
actual ingestion authenticates with managed identity.

```sh
az deployment group create --resource-group counterpress-dev \
  --name footie-agent-monitoring \
  --template-file infra/agent-monitoring.bicep --output none

uv run --extra foundry-admin python scripts/configure_agent_monitoring.py \
  --register
```

The helper reads only the relevant project/component/identity metadata, verifies
the project's telemetry connection resolves the same component and creates missing
external registrations. It never calls a
model, changes the app, lists existing app secret values, or prints private
destinations. The registration operation is idempotent for these stable IDs.
An optional `--runtime-config` argument writes a new mode-600 settings file for
controlled diagnostics; keep that file outside the repository and delete it
afterward. The normal release script reads the relevant Azure metadata directly.

The guarded release step's `assistant_tracing=enable` option resolves these settings:

| Environment variable | Value |
| --- | --- |
| `COUNTERPRESS_AGENT_TRACING` | `azure` |
| `APPLICATIONINSIGHTS_CONNECTION_STRING` | Secret reference `agent-monitor-connection` |
| `COUNTERPRESS_AGENT_TRACING_CLIENT_ID` | Existing history managed-identity client ID |
| `COUNTERPRESS_AGENT_TRACE_SAMPLE_RATIO` | `1.0` initially |

For fresh infrastructure, `infra/app.bicep` exposes `useAgentTracing`; it requires
the existing Cosmos identity. For the existing app, use the guarded image release
path so unrelated environment variables, secrets, identities and scaling survive.
Do not redeploy the entire app template merely to turn tracing on.

An ARM configuration update resupplies the three known model-secret values from
the existing private GitHub `CP_EDITORIAL_MODEL` configuration, and the monitoring
connection from its resource metadata. It does not assume omitted values survive
the update, and it never lists the application's secret values. Unknown secrets
or incomplete private configuration stop the release. A working model-backed
answer after deployment is required to verify the resulting model connection.

## Verification and review

1. Verify the new Container App revision is healthy and its image corresponds to
   the tested commit. Confirm the four settings are present without printing
   their private values.
2. Ask one bounded player comparison and one compound match/career question.
   Record the response request IDs and whether the answers were model-backed or
   calculated fallbacks. A cache hit may legitimately have no specialist calls.
3. In Foundry, open the `CounterPress` project, then **Build > Agents**, choose the
   external agent and open **Traces**. Use a time range that covers the check and
   allow several minutes for ingestion. Portal labels can vary as preview rolls
   out; the same component is available under the project's connected resources.
4. Verify the same trace contains parent and child stages, expected roles, bounded
   model-call counts and token usage. Inspect `counterpress-agents` directly if
   the Foundry trace list is empty. A registration mismatch affects portal
   correlation without necessarily stopping Application Insights ingestion.
5. Confirm the exported properties have no prompt, response, exception body,
   private endpoint or credentials. Run privacy regression tests after SDK changes.

In the existing workspace's Logs blade:

```kusto
AppDependencies
| where TimeGenerated > ago(24h)
| where AppRoleName == "footie-agents"
| extend Agent=tostring(Properties["gen_ai.agent.id"]),
         RequestId=tostring(Properties["footie.request_id"]),
         ProviderRequests=toint(Properties["footie.provider_requests"]),
         InputTokens=toint(Properties["gen_ai.usage.input_tokens"]),
         OutputTokens=toint(Properties["gen_ai.usage.output_tokens"])
| project TimeGenerated, Name, Agent, OperationId, ParentId, RequestId,
          DurationMs, Success, ProviderRequests, InputTokens, OutputTokens
| order by TimeGenerated desc
```

Token counters are per stage; do not sum a request aggregate and all its children
as separate usage. Filter to provider stage spans to estimate provider usage.

If ingestion fails, check the identity is attached to the app, the configured
client ID selects it, its role assignment exists at the Application Insights
scope, role propagation has completed, and workspace ingestion is not capped.
Reviewers need permission to read the connected monitoring resource/workspace.
No new broad Azure administrator role is required by the runtime.

## Cost and rollback

The total authorized project budget is US$125 including previously incurred
charges. Azure budgets alert; they do not stop spending. The existing workspace
has a 0.025 GB/day configured ingestion guard and 30-day retention. That guard is
shared with streaming telemetry, is not a guaranteed billing ceiling, and may
cause missing traces when reached. Inspect actual ingestion rather than assuming
the theoretical cap is enforced immediately. No new compute pool is provisioned.

The previous admission state retained only one hour of reservations. Upgrading
migrates those retained reservations into weighted accounting but cannot recover
earlier usage in the preceding 24 hours from that old state. New weighted entries
are retained for 24 hours. This migration limitation does not erase prior Azure
charges: the US$125 budget includes all actual usage before and after the upgrade.

Turn `COUNTERPRESS_AGENT_TRACING=off` to stop exporting on the next revision.
Rollback multi-agent behavior independently using the assistant workflow setting.
Keep existing registrations and monitoring data during diagnosis; removing them
does not fix an application issue. Retention handles stored telemetry normally.

## Primary references

- [Register external agents](https://learn.microsoft.com/en-us/azure/foundry/agents/how-to/register-external-agent)
- [Configure framework tracing](https://learn.microsoft.com/en-us/azure/foundry/observability/how-to/trace-agent-framework)
- [Connect Application Insights to Foundry](https://learn.microsoft.com/en-us/azure/foundry/observability/how-to/trace-agent-setup)
- [Application Insights Entra authentication](https://learn.microsoft.com/en-us/azure/azure-monitor/app/azure-ad-authentication)
- [Foundry project connection ARM schema](https://learn.microsoft.com/en-us/azure/templates/microsoft.cognitiveservices/2025-06-01/accounts/projects/connections)

Checked 23 October 2026. This runbook describes the integration design; deployment
and live trace evidence must be recorded in the release verification report.
