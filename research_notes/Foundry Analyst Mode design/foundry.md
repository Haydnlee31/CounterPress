# Foundry-native orchestration for Footie Analyst Mode

Research checked 26 October 2026. This is design research, not a deployment record. No Azure account queries or mutations were performed. Public Microsoft documentation and retail-pricing APIs were read; local installed SDK signatures and the existing monitoring document were inspected.

## Which Foundry runtime should Footie use?

### Takeaway

Use **one small Foundry-hosted coordinator executing bounded Python/Agent Framework orchestration, with three or four native Foundry prompt-agent specialists**. This best satisfies genuinely Foundry-owned execution, causal replay control, hard per-call token limits, deterministic fan-out, and the US$200 total project ceiling. A native prompt coordinator with A2A-connected prompt specialists is the lowest hosting-cost alternative, but its nested execution limits need live proof before treating it as a hard-budget implementation.

### Cited Findings

- Prompt agents are managed definitions of instructions, model and tools; hosted agents run developer code on Foundry-managed infrastructure. Both are genuine Foundry runtime approaches. Merely registering external Container App agents for tracing is a different arrangement. [Agent Service overview](https://learn.microsoft.com/en-us/azure/ai-foundry/agents/overview?view=foundry)
- **Do not implement new declarative workflow agents**: Microsoft says the visual workflow feature retires **1 December 2026**, recommends Microsoft Agent Framework, and says code/YAML workflows can continue when deployed as hosted agents. [Workflow migration](https://learn.microsoft.com/en-us/azure/foundry/agents/concepts/workflow)
- Classic Connected Agents is absent from the new Foundry API; A2A is the replacement. The classic tool also has depth and citation limitations. [Migration tool matrix](https://learn.microsoft.com/en-us/azure/ai-foundry/agents/how-to/migrate?view=foundry); [Classic connected-agent limits](https://learn.microsoft.com/en-us/azure/ai-foundry/agents/how-to/connected-agents)
- GA A2A1.0 allows one native prompt agent to invoke another native prompt agent. Incoming native A2A is text-only, JSON-RPC-only for1.0, and nonstreaming. Explicitly select1.0 because unspecified version can resolve to preview0.3. [Incoming A2A](https://learn.microsoft.com/en-us/azure/foundry/agents/how-to/enable-agent-to-agent-endpoint)
- The separate new Azure OpenAI automatic multi-agent Responses capability is a **GPT-5.6 preview** and does not support `max_tool_calls` in that mode. It is not a suitable replacement for this project's existing mini deployment and fixed budget. [Responses multi-agent preview](https://learn.microsoft.com/en-us/azure/foundry/openai/how-to/responses-multi-agent)

### Inferences

Proposed execution graph:

```
Canonical event store -> Container App causal snapshot/admission gateway
  -> Foundry hosted Analyst Director (one bounded session per match generation)
       -> Foundry prompt Build-up specialist
       -> Foundry prompt Chance/Threat specialist
       -> Foundry prompt Defensive/Transition specialist
       -> Foundry prompt Player/Context specialist (only when relevant)
       -> validate specialist findings -> bounded synthesis -> validated output
  -> versioned findings store -> Web PubSub notification -> Analyst Mode UI
```

Keep canonical statistics in deterministic code; ask specialists to test competing interpretations against those statistics, compare windows, identify the consequential change, express uncertainty and suggest what to watch next. Do not spend inference calculating sums, distances or percentages.

The director can use Python to decide eligible specialists and a semaphore of2; each specialist remains a separately registered/versioned Foundry agent. A final short native prompt director may synthesize results if useful; orchestration code and the dispatch loop still execute in the Foundry hosted runtime. Existing Footie chat stays intact.

Cheaper alternative: native prompt director with three A2ATools and no specialist tools. This genuinely orchestrates in Foundry and introduces no hosted compute charge. However model-selected delegation is less deterministic, one specialist may be skipped/recalled, and coordinator usage may not include all nested-agent costs. Do not promise bounded calls merely by prompting “call each once.”

### Gaps

- No live proof yet of deployed resource compatibility, nested A2A token accounting, or hard forwarding of specialist output caps. Account audit belongs to the other researcher.
- Three versus four specialists depends on the reference repository's actual metrics; the separate reference researcher owns that mapping.
- Hosted SDK adapter packages are not installed in the current app environment; add and lock them in an isolated runtime dependency set, then smoke-test exact deployed protocol handling.

## What exact APIs and schemas can implement this?

### Takeaway

The installed `azure-ai-projects`2.9.0 already contains current agent versioning, endpoint configuration, A2A tools, structured text formats and hosted-agent definitions. Register versions during provisioning, pin them for runs, and send small immutable evidence packets rather than growing chat histories.

### Cited Findings

- Microsoft current Python examples use `AIProjectClient`, `PromptAgentDefinition`, `agents.create_version`, and `get_openai_client` with the project endpoint. The2.x API is incompatible with1.x. [Prompt-agent quickstart](https://learn.microsoft.com/en-us/azure/foundry/agents/quickstarts/prompt-agent)
- The current project Responses contract exposes `agent_reference`, `max_output_tokens`, `max_tool_calls`, `parallel_tool_calls`, background responses and structured `text.format`. [Responses REST contract](https://learn.microsoft.com/rest/api/aifoundry/project/responses)
- Python incoming-A2A configuration uses `agents.update_details`, an agent card and an endpoint protocol configuration. It is not yet a portal setting. [Enable A2A](https://learn.microsoft.com/en-us/azure/foundry/agents/how-to/enable-agent-to-agent-endpoint)
- The native A2A tool uses a project connection ID and `A2AProtocolVersion.V1_0`. [Outgoing A2A examples](https://learn.microsoft.com/en-us/azure/foundry/agents/how-to/tools/agent-to-agent)
- Hosted deployment uses `HostedAgentDefinition`, a container image, CPU/memory and a Responses protocol version; current sample handler uses `ResponsesAgentServerHost`. [Hosted deployment](https://learn.microsoft.com/en-us/azure/foundry/agents/how-to/deploy-hosted-agent)
- Structured output support has conflicting documentation: current agent API/SDK exposes JSON-schema text formatting, while an older general Azure OpenAI guide still says Foundry Agent Service unsupported. Prefer current API, but require live schema smoke tests and always validate returned output. [Current agent-framework structured output guide](https://learn.microsoft.com/en-us/agent-framework/agents/structured-outputs); [Conflicting general guide](https://learn.microsoft.com/en-us/azure/ai-services/openai/how-to/structured-outputs)

### Inferences

Local inspection (no network): `azure-ai-projects=2.9.0`, `openai=3.31.0`, `azure-identity=1.26.0`, `agent-framework-core=1.21.0`. Existing [monitoring document](../../docs/footie-foundry-monitoring.md) explicitly describes external-agent registration, not native execution. `foundry-admin` is currently optional; a hosted runtime calling prompt agents needs this dependency in its runtime lock.

Illustrative code, adapted to the verified installed model signatures; **not cloud-tested**:

```python
from azure.ai.projects import AIProjectClient
from azure.ai.projects.models import (
    PromptAgentDefinition, PromptAgentDefinitionTextOptions,
    TextResponseFormatJsonSchema,
)
from azure.identity import DefaultAzureCredential

project = AIProjectClient(endpoint=PROJECT_ENDPOINT,
                          credential=DefaultAzureCredential())
agent = project.agents.create_version(
    agent_name="footie-analyst-chances",
    definition=PromptAgentDefinition(
        model=EXISTING_MODEL_DEPLOYMENT,
        instructions=VERSIONED_SPECIALIST_INSTRUCTIONS,
        tools=[],
        text=PromptAgentDefinitionTextOptions(
            format=TextResponseFormatJsonSchema(
                name="analyst_findings", schema=STRICT_SCHEMA, strict=True
            )
        ),
    ),
    metadata={"definition_hash": DEFINITION_HASH},
)
# Persist name/version/hash in deployment manifest. Do not create on each request.
client = project.get_openai_client()
response = client.responses.create(
    input=CANONICAL_PACKET_JSON,
    max_output_tokens=700,
    parallel_tool_calls=False,
    extra_body={"agent_reference": {
        "type": "agent_reference", "name": agent.name, "version": agent.version
    }},
)
# Validate response status/refusal/schema, then validate evidence and arithmetic.
```

Specialists with no tools produce one bounded completion; no recursive loops. A richer variant can expose a small set of read-only evidence tools, but the tool server must bind a signed snapshot scope and reject arbitrary match IDs, future cutoffs or unrestricted queries. Tool output is untrusted evidence, never instructions.

A2A alternative setup, after specialist creation:

```python
from azure.ai.projects.models import (
    A2AProtocolConfiguration, AgentCard, AgentCardSkill, AgentEndpointConfig,
    ProtocolConfiguration, ResponsesProtocolConfiguration, A2ATool,
    A2AProtocolVersion,
)
project.agents.update_details(
    agent_name=agent.name,
    agent_endpoint=AgentEndpointConfig(protocol_configuration=ProtocolConfiguration(
        responses=ResponsesProtocolConfiguration(), a2a=A2AProtocolConfiguration()
    )),
    agent_card=AgentCard(version="1.0", description="Evidence-grounded chance analysis",
        skills=[AgentCardSkill(id="chances", name="Chance analysis",
                              description="Analyze only the supplied snapshot")]),
)
connection = project.connections.get(A2A_CONNECTION_NAME)
tool = A2ATool(a2a_version=A2AProtocolVersion.V1_0,
              project_connection_id=connection.id)
# Put tool in the director's PromptAgentDefinition.tools.
```

For a Foundry target, the A2A connection points to
`https://{account}.services.ai.azure.com/api/projects/{project}/agents/{agent}/endpoint/protocols/a2a`
with audience `https://ai.azure.com`. Use service/agent identity rather than embedding a bearer token in a prompt. A2A endpoint version selection is separate from agent-version pinning; freeze the endpoint's version selector for reproducible pilot deployments.

Hosted registration shape:

```python
from datetime import timedelta
from azure.ai.projects.models import (
    HostedAgentDefinition, ContainerConfiguration, SessionConfiguration,
    ProtocolVersionRecord, AgentEndpointProtocol,
)
coordinator = project.agents.create_version(
    agent_name="footie-analyst-director",
    definition=HostedAgentDefinition(
        cpu="1", memory="2Gi",
        container_configuration=ContainerConfiguration(image=PINNED_IMAGE_DIGEST),
        protocol_versions=[ProtocolVersionRecord(
            protocol=AgentEndpointProtocol.RESPONSES, version="2.0.0")],
        session_configuration=SessionConfiguration(
            idle_timeout_seconds=timedelta(seconds=120)),
        environment_variables={"SPECIALIST_MANIFEST": VERSIONED_MANIFEST},
    ),
)
```

Do not blindly reuse old hosted examples with replica scaling: current docs describe per-session isolation and idle timeout. Runtime handler package/API must be pinned to the current documented protocol before shipping.

Recommended original input contract:

```json
{
  "schema_version": "analyst.snapshot.v1",
  "match_id": "stable-match-id",
  "generation_id": "seek-or-revision-generation",
  "packet_id": "content-hash",
  "cutoff": {"period": 2, "occurrence_ms": 2815000,
             "available_at": "ISO-8601", "delivery_sequence": 1234},
  "window": {"start_ms": 2755000, "end_ms": 2815000,
             "interval": "(start,end]"},
  "coverage": {"events": true, "measured_tracking": false,
               "recipients": false, "video_frames": false},
  "metrics": [], "events": [], "comparison": {}, "player_context": [],
  "allowed_evidence_ids": [], "prior_supported_findings": []
}
```

Recommended output fields: `match_id`, `generation_id`, `packet_id`, `specialist`, `as_of`, `findings[]`; each finding has `title`, `explanation`, `why_now`, `evidence_ids[]`, `metric_ids[]`, `interpretation`, `alternative_explanation`, `confidence_band`, `watch_next`, `expires_after_ms`. Add `insufficient_evidence` outcomes. All JSON-schema objects disallow extra properties and explicitly require fields, with nullable values where needed. Citation validity is enforced by backend membership/revision checks, not by trusting generated URLs. Numerical claims must be traceable to metric records with denominators, units and coverage.

### Gaps

- The samples above are a compatible implementation blueprint, not a claim of tested cloud functionality. A real smoke test must verify schema acceptance, structured output plus tool behavior, immutable version invocation, refusal handling and native trace visibility.
- Current public docs do not establish a per-specialist hard token cap inherited through native A2A. A hosted coordinator calling specialist Responses explicitly avoids that uncertainty.

## How should causal replay, budget, and operations work?

### Takeaway

Reuse Footie's causal event model and shared admission ledger. Schedule analysis around completed phases or meaningful changes; do not invoke agents on every event/frame/viewer. Treat each seek/revision as a new immutable generation and discard stale completion results even if cancellation fails.

### Cited Findings

- Hosted sessions use separate sandbox compute, preserve state through idle, allow idle timeout2–60minutes (default15), and accrue CPU/memory costs while active. The documented regions include EastUS2, SwedenCentral and SoutheastAsia. [Hosted sessions and regions](https://learn.microsoft.com/en-us/azure/foundry/agents/concepts/hosted-agents)
- Agent Service imposes128tools and1000versions per agent; model rate limits apply at deployment level. Hosted regional session quotas are far above our intended concurrency but are not spending controls. [Quotas](https://learn.microsoft.com/en-us/azure/foundry/agents/concepts/limits-quotas-regions)
- Background calls can be polled/resumed; hosted per-turn cancellation is preview, cooperative and requires `background=true`. It does not guarantee already-running model work costs disappear. [Background responses](https://learn.microsoft.com/en-us/agent-framework/agents/background-responses); [Hosted cancellation](https://learn.microsoft.com/en-us/azure/foundry/agents/how-to/cancel-hosted-agent-turn)
- Foundry prompt-agent creation/runtime has no additional platform charge; model tokens and tools are billed. Hosted execution adds compute. [Pricing](https://azure.microsoft.com/en-us/pricing/details/foundry-agent-service/)
- Public retail API returned **EastUS2 USD** hosted CPU **0.0994 per vCPU-hour** and memory **0.0118 per GiB-hour**, effective1February2026. [Public retail query](https://prices.azure.com/api/retail/prices?$filter=productName%20eq%20%27Foundry%20Agents%27%20and%20armRegionName%20eq%20%27eastus2%27)
- The public API returned GPT4.1-mini Global input **$0.0004/1K**, output **$0.0016/1K**, cached input **$0.0001/1K**; regional input/output **$0.00044/$0.00176 per1K**. These are public list rates, not subscription bill/credit balance. [Retail model query](https://prices.azure.com/api/retail/prices?$filter=contains%28meterName%2C%20%274.1%20mini%27%29%20and%20armRegionName%20eq%20%27eastus2%27)
- Incoming agent requests use Entra authentication. A2A callers require Foundry Agent Consumer or higher on target scope; connection creation may require Foundry Project Manager. Agent-identity/shared authentication is available for app-only calls. [Endpoint auth](https://learn.microsoft.com/en-us/azure/foundry/agents/how-to/configure-agent); [A2A auth](https://learn.microsoft.com/en-us/azure/foundry/agents/concepts/agent-to-agent-authentication)
- GPT4.1-mini deployment availability varies by deployment type/region. Verify the actual existing deployment rather than using the classic-agent region matrix. [Current model region table](https://learn.microsoft.com/azure/foundry/foundry-models/concepts/models-sold-directly-by-azure-region-availability)

### Inferences

**Causal/state design**

1. Packet construction resolves event revisions using both occurrence cutoff and revision availability/delivery cutoff. Never append final score or full-match career result into an earlier live window.
2. A generation key includes match, playback seek epoch, cutoff, revision digest, agent-version manifest and calibration version. Cache by canonical packet+agent manifest. User language/favorite club affects presentation keys, not the source truth.
3. Avoid persistent unbounded conversations. Each call receives current bounded snapshot, rolling previous window and only earlier verified findings. Never carry a later response/conversation ID into an earlier seek.
4. On seek, cancel pending dispatch and increment epoch immediately. If a provider call already started, attempt supported cancellation but still reconcile charged usage; completion must pass epoch/hash check before publication.
5. Coalesce incoming revisions while one run is active; schedule only the latest packet. Distinguish stale card, pending refresh, unsupported metric and no meaningful change in UI.
6. Pause ends dispatch; resuming only schedules if the evidence changed. No inference on render ticks. Share the same analysis across viewers.
7. Deterministic metrics refresh immediately. LLM insight is asynchronous and time-labeled; do not freeze match playback while waiting.

**Invocation budget example (proposed, not measured performance)**

- Initial pilot: one shared active match, coordinator concurrency1; specialist concurrency2; at most3 specialists plus1 synthesis per scheduled window; no recursive delegation; one retry only on explicitly transient pre-result errors.
- Prefer phase boundaries, shot/turnover triggers and sustained-change thresholds, with30–60s minimum spacing and per-match window cap. At180windows for90minutes and4calls/window, the workload is720calls: this exceeds the current production400/day model-call guard. Either start a smaller45–90window pilot or explicitly integrate the new shared workload allowance. Do not silently multiply600 evaluation calls into production.
- Example3specialists at2500input+500output tokens plus one synthesis3000input+700output:10,500input+2200output perwindow. At Global mini list rates, **$0.00772/window**, **$1.39/180windows** before retries/tools/hosting. This is an estimate from chosen token caps, not a guarantee or actual spend.
-1vCPU+2GiB hosted list cost is **$0.123/hour**;90min+2minidle is about**$0.189**. Leaving one session continuously active720hours would cost**$88.56**, so lifecycle matters more than a single demo run. Lower CPU tiers may save further, but must be validated for package memory/cold-start behavior.
- Reserve worst-case call cost atomically in Cosmos before dispatch; reconcile returned token usage once; retain charge reservation on unknown timed-out results until reconciled. Separate per-request, hourly, rolling24h and lifetime allowance. Include retries and tests.
- Total remaining allowance =200 minus existing Azure usage minus projected hosting/services reserve minus already-reserved inference. Azure budget notifications alone cannot enforce this. App must deny paid dispatch when the ledger or configured hard reserve is exhausted. Prefer fail-closed cached/metrics-only mode on unavailable admission storage.
- Hosted runtime owns its limited provider credentials/access; browser never receives a Foundry token. Stop idle sessions and have a scheduled cleanup/quota backstop. Session admission must prevent one sandbox perviewer; match-level sharing still needs user privacy separation for private questions.

**Video/tracking boundary**

Canonical event packets are the best initial grounding. Rendered pitch animation screenshots do not add independent observation: they depict our interpolation and cannot prove real pressure, speed or off-ball shape. If actual captured footage is introduced later, a separate vision perception stage should emit timestamped observations with confidence, tracking IDs, calibration and source frame references. Use direct vision-capable Responses calls or a hosted perception process; native A2A currently cannot carry image modality. Do not fabricate measured speed from event timestamps or infer verified pressing from an animated dot trajectory.

**Required rollout proof**

Test deterministic packet cutoffs/revisions, first-half versus second-half occurrence order, seekback/no-future leakage, pause/resume, stale result suppression, duplicated deliveries, malformed/refused outputs, evidence mismatch, partial specialist timeout, admission races, idempotent retries, cache isolation and no new insight on unsupported sparse windows. Then run a small paid native smoke test verifying agents appear as native definitions and their actual runs/versions/traces are visible. UI should show specialist lenses and their support, not a wall of raw chain-of-thought or unsupported confidence numbers.

### Gaps

- Actual subscription spend, credits, SKU/region, identities, project age, image registry access and policy support are not checked here. No cloud mutation was made.
- Public price queries give list rates, not guaranteed account prices; other regions and currencies differ. Hosted runtime telemetry/storage/tool charges are additional.
- No claim that a continuous90-minute hosted session will be needed; request/session lifecycle and latency must be measured in the pilot. Latency targets need empirical verification.
- End-to-end cancellation of native A2A descendants is not established by the researched docs. Stale-generation rejection remains mandatory regardless of runtime.

Follow-up for the confirmed East US project (26 October): **East US hosted is supported**, and its public retail API returned the same0.0994CPU/0.0118memory hourly USD rates. [East US price query](https://prices.azure.com/api/retail/prices?$filter=productName%20eq%20%27Foundry%20Agents%27%20and%20armRegionName%20eq%20%27eastus%27). Deployment docs require **Foundry Project Manager** at project scope, not merely User, because deployment can create role assignments for a dedicated automatically created agent identity. Runtime hosted identity is that per-agent service principal; the Container App's existing managed identity is not automatically reused. Grant runtime only the model/project/evidence permissions needed. No universal hosted-preview registration prerequisite is listed in the current deployment documentation; subscription policy/capacity still require the pilot check. [Deploy prerequisites](https://learn.microsoft.com/en-us/azure/foundry/agents/how-to/deploy-hosted-agent)

Official minimal handler excerpt shape, adapted; image startup command/package pin must follow selected server package version:

```python
from azure.ai.agentserver.responses import (
    CreateResponse, ResponseContext, ResponsesAgentServerHost, TextResponse,
)
app = ResponsesAgentServerHost()

@app.response_handler
async def handler(request: CreateResponse, context: ResponseContext, cancellation_signal):
    packet_json = await context.get_input_text() or ""
    # Parse strict packet; acquire central budget permit before any paid call.
    # Bound parallel native specialist Responses calls; validate all findings.
    # Check cancellation_signal between steps and generation before publishing.
    result_json = await run_bounded_analysis(packet_json, cancellation_signal)
    return TextResponse(context, request, text=result_json)
```

Session lifecycle exact SDK operations verified locally: `agents.create_session(agent_name, version_indicator=...)`, `get_session(agent_name, session_id)`, `list_sessions(agent_name)`, `stop_session(agent_name, session_id)`, `delete_session(agent_name, session_id)`. Creation/provisioning state and invocation conventions need the first hosted proof; do not assume `stop_session` deletes persisted state. Stop on completed pilot or loss of shared viewers; delete expired/private sessions; configure two-minute idle timeout and external cleanup backstop. Version creation is separate from session compute. [Manage hosted agents](https://learn.microsoft.com/en-us/azure/foundry/agents/how-to/manage-hosted-agent)
