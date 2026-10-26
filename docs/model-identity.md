# Model authentication with managed identity

Implementation and guarded deployment support prepared through 26 October 2026.
The default remains API-key authentication until an explicit configuration change
is reviewed and staged inference succeeds. A role assignment or successful local
test alone does not establish hosted model access.

## Configuration

Existing settings continue to work:

- `AZURE_OPENAI_ENDPOINT`: Azure resource HTTPS endpoint or `/openai/v1/` base URL.
- `AZURE_OPENAI_DEPLOYMENT`: existing model deployment name.
- `AZURE_OPENAI_API_KEY`: secret, required in the default mode.
- `AZURE_OPENAI_AUTH_MODE=api_key`: optional explicit default.

For managed identity, set `AZURE_OPENAI_AUTH_MODE=managed_identity` and
`AZURE_OPENAI_MANAGED_IDENTITY_CLIENT_ID` to the client ID of the identity already
attached to the Container App. `AZURE_CLIENT_ID` is a secondary alias. The model
specific setting is preferable when other Azure clients use different identities.
A host using a system-assigned identity can omit the client ID; the current
CounterPress app has multiple user-assigned identities and must select one.

A legacy API-key environment variable is ignored in identity mode. Authentication
failure never silently falls back to that key, Azure CLI credentials, environment
client secrets or a developer account. `ManagedIdentityCredential` is used
explicitly rather than a broad credential chain. Managed identity does not work
on an ordinary laptop; local API-key mode and mocked identity tests remain
available. A future developer-login mode would require its own explicit setting.

## Shared code boundary

`counterpress.adaptation.azure.model_auth` owns one authentication context:

```python
async with model_auth(config) as auth:
    headers = await auth.headers()       # Direct HTTP adapter
    options = auth.sdk_kwargs()          # Existing async OpenAI SDK client
```

The SDK options use an async token callable, not a token captured once at startup.
Keep the SDK inside the authentication context. The helper closes its asynchronous
credential on success, failure and cancellation. Token acquisition is bounded to
four seconds; cleanup to two. The Azure bearer provider supplies caching and
refresh within the context, without a global credential tied to an old event
loop. The multiagent workflow now opens this context once per question and shares
one request-owned HTTP connection pool across its stages. Each stage keeps its
own SDK wrapper, schema, role and usage count; closing a stage cannot close the
borrowed pool. Concurrent questions have separate credentials and pools. A short
lock protects initial token acquisition without serializing specialist inference.
Success, partial provider failure, cancellation and constructor failure are tested
for cleanup. This is verified local behavior, not a claim of hosted identity activation.

SDK/model retries remain disabled by existing callers. Existing request
budgets and overall workflow deadlines remain authoritative.

Only Azure resource HTTPS hosts already permitted by `AzureConfig` are accepted.
The helper revalidates copied configuration before creating a credential.
Callers must continue to disable redirects. Exceptions expose fixed reason codes,
never token contents, private identity endpoints, model URLs or raw provider
errors. Identity mode sends a bearer Authorization header and no API-key header.

The installed OpenAI Python 3.31.0 `AsyncOpenAI` supports an async callable in its
`api_key` parameter, and the installed Agent Framework accepts that supplied SDK
through `OpenAIChatCompletionClient(async_client=...)`. Tests verify the resulting
HTTP headers, rather than only inspecting configuration objects.

## Token audience and role

The implementation fixes the inference audience to
`https://ai.azure.com/.default`, matching the current Microsoft Azure OpenAI v1
managed identity examples. Do not substitute an Azure Resource Manager audience.
Older Azure OpenAI examples use `https://cognitiveservices.azure.com/.default`;
those examples do not justify a silent audience retry in this implementation.
Validate the configured v1 endpoint in staging before switching production.

Microsoft recommends the **Cognitive Services OpenAI User** role for a managed
identity calling Azure OpenAI inference. Scope it to the existing model resource,
not the subscription or resource group. Role assignment propagation can take
several minutes.

Sources checked 23 October 2026:

- [Microsoft: Azure OpenAI managed identity authentication](https://learn.microsoft.com/en-us/azure/foundry-classic/openai/how-to/managed-identity)
- [Microsoft: Foundry keyless authentication and v1 token audience](https://learn.microsoft.com/en-us/azure/foundry/foundry-models/how-to/configure-entra-id)

## Deployment audit and scoped role assignment

The app has four user-assigned identities: `counterpress-pull`,
`counterpress-history`, `counterpress-stream`, and `counterpress-feed`.
`counterpress-history` already serves application data/monitoring work and is a
candidate for reuse. The initial read-only audit found no applicable model roles.
On 26 October, the existing identity received **Cognitive Services OpenAI User**
on `counterpress-dev-01` only. Readback confirmed the assignment and preserved the
existing assignments. No additional identity or service was created, and this
step did not change the app's authentication configuration. Private role and
rollback receipts remain outside version control; no tokens, model endpoints or
keys were printed.

## Guarded deployment controls

`stage.yml` accepts `model_authentication=managed_identity` for the candidate only.
The original production revision retains 100% traffic; the candidate receives 0%
and a separate review label. Staging disables stream consumers and career
ingestion, retains shared model admission, and selects the already attached
`counterpress-history` identity explicitly. Its environment contains no
`AZURE_OPENAI_API_KEY` reference.

Cleanup reconstructs the candidate from the immutable original revision and the
permitted authentication change. Unrelated environment, resource or scaler
changes fail validation. Cleanup restores the original template and single
revision mode; it never promotes the candidate.

After successful staged inference and cleanup, `deploy.yml` accepts
`model_authentication=managed_identity`. `preserve` is the default. The explicit
`api_key` option restores the retained server-side `editorial-key` secret
reference for rollback. This is an operator action, never an automatic runtime
fallback. Deployment preserves secret configuration, model deployment,
production limits and attached identities. The old secret is retained for
rollback; removing its runtime environment reference does not revoke the key.

## Activation sequence after the core gate

1. Finish wiring and validating every model caller against the shared helper.
   Direct HTTP intent/wording calls and Agent Framework calls must both use it.
2. Review the exact resource-scoped role assignment for the existing identity.
3. Assign only the inference role, then wait for propagation as needed.
4. Deploy a staging revision selecting managed identity and its explicit client
   ID. Keep live traffic on the previously verified revision.
5. Test one bounded, supported model request, check the requested identity and
   successful trace, then run the release smoke cases. Never print a token as a
   troubleshooting step.
6. Measure additional first-token/identity acquisition latency and confirm the
   request deadline and model budgets still hold.
7. Switch traffic only after the staged checks pass. Remove the app's obsolete
   model-key reference after a verified rollback path exists; do not revoke shared
   keys used by other consumers without reviewing those consumers.

These steps create no new Azure service. They do not establish that the existing
US$125 total project budget has sufficient remaining credit; model checks remain
subject to the shared usage gate and the actual spend review.

## Local verification

```sh
.venv/bin/python -m pytest -q tests/test_model_identity.py tests/test_adaptation.py
.venv/bin/pytest -q tests/test_model_identity.py tests/test_deployment_model_auth.py tests/test_deployment_guard.py tests/test_staging_guard.py tests/test_staging_model_identity.py tests/test_phase4_guard.py
```

Tests cover explicit mode selection, legacy compatibility, secret-safe errors,
HTTPS enforcement, token caching and refresh, SDK bearer headers, direct HTTP
headers, identity failure without key fallback and credential cleanup after
cancellation. Tests use fake credentials and mock transports, never live Azure
model calls. Hosted RBAC, audience acceptance and end-to-end latency remain
separate deployment checks.
