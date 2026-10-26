# Native Foundry Analyst Mode

Analyst Mode has a separate native runtime. Existing Footie chat is unchanged.
The Container App computes a causal, immutable evidence snapshot and reserves a
bounded paid run. A Foundry **hosted** director fans out to four versioned native
prompt agents: Chance, Defence, Control and Players. Each specialist ranks supplied,
deterministically rendered candidate readings and returns only a `candidate_id` or
null. It cannot write or translate factual prose. A fifth native editor checks the
selected candidates and ranks their usefulness for the viewer. Published readings
are exact copies of supplied candidates; the editor cannot add measurements or text.

The earlier free-prose/verifier design failed independent adversarial tests despite
using the intended deployed GPT-5 mini verifier. It is superseded by candidate
selection: factual correctness no longer depends on an LLM approving another LLM's
claims. The backend constructs localized facts, comparison windows and supported
interpretation variants. Native AI chooses relevance, perspective and priority.

The native instruction definitions live in
`integrations/analyst_foundry/definitions.py`; they are registered as actual
Foundry prompt agents, not external monitoring records. Deterministic dispatch,
validation, cancellation and token caps execute in the hosted director.

## Runtime boundaries

- At most five model calls, two concurrently, no retries.
- Specialist output600tokens; verifier1500tokens (including reasoning). Input24000characters
  and32000UTF-8bytes maximum. Four specialists use GPT4.1mini; the verifier uses
  the existing GPT5mini deployment with minimal reasoning.
- Native director deadline110seconds; each specialist request32seconds maximum.
- One paid run per hosted session, enforced with a persistent SQLite permit.
  Process restart or idle resumption does not reset that permit.
- Hosted session idle timeout120seconds. The caller sends an explicit new UUID in
  `agent_session_id` and stops/deletes it in `finally`, including on timeout.
- The caller's durable Cosmos admission ledger controls the global/hourly/daily
  allowance. The runtime's local permit is an additional session bound, not a
  substitute for global admission.
- Missing/invalid evidence, unavailable metrics, invented references, unsupported
  numerical prose, certainty and coaching orders are rejected. Numeric prose must
  match explicitly cited scalar metrics (with legitimate rounding and matching
  units) or the supplied window duration. An uncited roster number cannot justify
  an invented percentage. The independent verifier also checks attribution, units,
  windows and heuristic-versus-measured distinctions. This syntax/evidence gate cannot prove every
  natural-language inference is true; human benchmark review is still required.
- At most eight supplied candidates, scoped by role. Unknown candidate IDs, cross-role
  selections and extra model-authored prose fail closed. With no candidates there
  are zero model calls.
- The editor only selects a validated specialist role; summary strings are copied
  exactly from that reading. Failed specialists yield partial/insufficient status.
- No unrestricted tools, web access, recursive delegation or model-defined metrics.
- Fresh snapshot inputs only; no previous response or persistent conversation is
  supplied. A seek or revision creates another snapshot; stale results are rejected
  by the Container App before publication.

## Native API contract

Input is a JSON string containing `snapshot_id`, `match_id`,
`cutoff:{period,elapsed_ms}`, `through_sequence`, `clubs`, `score`, `metrics`,
`players`, `evidence`, `signals`, optional `windows`/`methods`/`triggers`, and
`language` (`en` or `zh-Hans`), `depth`, `focus_player_id`, and `candidates`.
Each candidate is `{id, role, reading}`, where reading has the existing published
Reading schema. Candidate IDs and every cited event/metric must be valid before any
paid call. The backend also checks returned readings equal its canonical candidates.

Output contains echoed snapshot identity/cutoff, `status`, validated `readings`,
`summary` or null, `usage:{input_tokens,output_tokens,model_calls}` and sanitized
`failed_roles`. A provider timeout retains the caller's worst-case reservation;
reported usage is not a reason to refund an uncertain failed run.

The caller uses the dedicated native agent Responses endpoint with:

```json
{
  "input": "<compact immutable snapshot JSON>",
  "stream": false,
  "store": false,
  "agent_reference": {
    "type": "agent_reference",
    "name": "FootieAnalystDirector",
    "version": "<pinned version>"
  },
  "agent_session_id": "<fresh caller-generated UUID>"
}
```

Cleanup routes: POST
`{project}/agents/FootieAnalystDirector/endpoint/sessions/{id}:stop?api-version=v1`,
then DELETE the same path without `:stop`. They require Entra authentication,
with audience `https://ai.azure.com`. Never send this token to the browser.
See [Responses contract](https://learn.microsoft.com/rest/api/aifoundry/project/responses)
and [session isolation](https://learn.microsoft.com/en-us/azure/foundry/agents/how-to/isolate-sessions-per-user).

## Provisioning

`python scripts/configure_analyst_foundry.py` prints a local plan only. Register
using `--apply --image <registry/image@sha256:digest> --manifest <path>` with the
private `FOUNDRY_PROJECT_ENDPOINT` environment variable. The script reuses matching
content-hashed versions, then explicitly pins each isolated Analyst endpoint to its
registered version with a single 100% FixedRatio rule and reads the selector back.
Request-body agent_reference alone is not treated as a routing pin. Native child
responses must report the expected agent name and version. The manifest fingerprint
includes the coordinator version and code hash, so runtime-only changes invalidate
cached snapshots. The script neither invokes models nor creates sessions or grants
roles. Existing Footie agent names are not modified. Deployment identity requires Foundry
Project Manager. Runtime invocations use the dedicated native agent endpoints.
The existing counterpress-history caller and new FootieAnalystDirector identity
need only the approved Foundry Agent Consumer role on the CounterPress project.
This grants endpoint interaction, not keys, secrets, agent editing or model deployment.
Session cleanup permission must be verified by the cloud smoke, with idle timeout
as a backstop. Do not grant the broader Foundry User role.

Build the dedicated Dockerfile with only `integrations/analyst_foundry` in its
context. Do not send the entire working directory to ACR. Native runtime packages
are pinned in its own requirements file; agentserver's web stack must not be
installed over the main FastAPI application.

Current official SDK: `azure-ai-agentserver-responses2.3.0`, core2.2.0,
projects2.9.0. The app starts `ResponsesAgentServerHost.run()` on PORT8088 and
supports `/readiness` and the standard `/responses` lifecycle. Automatic HTTP and
message-content instrumentation is disabled in this container. Native agent
versions/runs remain visible in Foundry; this is not raw reasoning-log capture.

## Costs and proof

East US public retail rates checked26October2026: hostedCPU$0.0994/vCPU-hour,
memory$0.0118/GiB-hour. 1vCPU/2GiB is$0.123/hour while active. Idle timeout and
explicit teardown are required; one continuously active sandbox can cost$88.56
in720hours. Four native specialists use the existing GPT4.1mini deployment; the verifier uses
the existing GPT5mini deployment. Both are explicitly pinned in the manifest. Azure
budget alerts alone do not stop spend; global admission remains fail-closed.

```sh
.venv/bin/python -m pytest tests/test_analyst_foundry_runtime.py -q
```

The protocol test additionally requires the dedicated agentserver dependencies.
The implementation was exercised against the actual official SDK ASGI host with
mocked native-model calls, including `/readiness` and nonstreaming `/responses`.
The normal application environment can skip that isolated dependency test; the
native-runtime validation environment must run it before any new image deploy.

Cloud smoke evidence and pinned deployment manifest are recorded separately after
provisioning; local mocked tests are not proof that native cloud invocation works.

Native ZIP deployment is also supported with `--code` instead of `--image`. The
allowlisted deterministic ZIP contains only runtime Python files and requirements;
Foundry remotely builds dependencies using `python_3_13`. This avoids ACR Tasks,
which the current trial subscription rejects. Multipart upload must include a
filename ending `.zip`. The coordinator source hash/version is pinned in the manifest.

The runtime derives human-readable clock/window labels. It rejects premature
halftime/fulltime/closing-minute claims and incomplete sentences before verification.
Counterpoints must explain the observed pattern, not invent a future tactical event.
[Reasoning effort support](https://learn.microsoft.com/azure/foundry/openai/how-to/reasoning)
supports minimal effort for GPT5mini.

Native endpoint routing follows the server-side version selector, as documented in
[agent configuration](https://learn.microsoft.com/azure/foundry/agents/how-to/configure-agent)
and [hosted agent management](https://learn.microsoft.com/azure/foundry/agents/how-to/manage-hosted-agent).
The earlier v7 smoke receipt proves transport and cleanup only; its free-prose
quality benchmark failed. A newer candidate-based version requires fresh local and
native acceptance checks before activation.
