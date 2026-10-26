# Native Foundry Analyst Mode

Analyst Mode has a separate native runtime. Existing Footie chat is unchanged.
The Container App computes a causal, immutable evidence snapshot and reserves a
bounded paid run. A Foundry **hosted** director fans out to four versioned native
prompt agents: Chance, Defence, Control and Players. A fifth native verifier checks every reading against its cited evidence, metrics and
canonical signals, then selects an accepted reading. It cannot introduce new prose
or measurements. If verification fails, no unchecked reading is published.

The native instruction definitions live in
`integrations/analyst_foundry/definitions.py`; they are registered as actual
Foundry prompt agents, not external monitoring records. Deterministic dispatch,
validation, cancellation and token caps execute in the hosted director.

## Runtime boundaries

- At most five model calls, two concurrently, no retries.
- Specialist output600tokens; editor700tokens. Input24000characters maximum.
- Native director deadline110seconds; each specialist request32seconds maximum.
- One paid run per hosted session, enforced with a persistent SQLite permit.
  Process restart or idle resumption does not reset that permit.
- Hosted session idle timeout120seconds. The caller sends an explicit new UUID in
  `agent_session_id` and stops/deletes it in `finally`, including on timeout.
- The caller's durable Cosmos admission ledger controls the global/hourly/daily
  allowance. The runtime's local permit is an additional session bound, not a
  substitute for global admission.
- Missing/invalid evidence, unavailable metrics, invented references, unsupported
  numerical prose, certainty and coaching orders are rejected. Numbers are shown
  from deterministic metric cards. This syntax/evidence gate cannot prove every
  natural-language inference is true; human benchmark review is still required.
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
`language` (`en` or `zh-Hans`), `depth`, `focus_player_id`.

Output contains echoed snapshot identity/cutoff, `status`, validated `readings`,
`summary` or null, `usage:{input_tokens,output_tokens,model_calls}` and sanitized
`failed_roles`. A provider timeout retains the caller's worst-case reservation;
reported usage is not a reason to refund an uncertain failed run.

The caller uses the project Responses API with:

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
content-hashed versions. It neither invokes models nor creates sessions or grants
roles. Existing agent names are not modified. Deployment identity requires Foundry
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
in720hours. Native prompt calls use the existing GPT4.1mini deployment. Azure
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
