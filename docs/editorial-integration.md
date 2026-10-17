# Editorial identity and cloud integration

This document records the pre-activation identity/storage checks. The later
[Studio AI pilot](verification/studio-editorial-live.json) adds verified hosted
authorization and an explicit model action for the assigned editor. Participant
review remains pending; these integration checks do not establish usefulness.

**Real Entra sign-in and both managed-identity Cosmos phases passed.** The
[sanitized verification record](verification/editorial-integration.json) separates
real identity, real storage and mocked model behavior.

## Entra registration

Two single-tenant registrations were configured on 17 October 2026:

- **CounterPress Editorial API:** v2 access tokens, delegated `Editorial.Run`
  scope and user role `CounterPress.Editor`. Assignment is required on its service
  principal. The role is assigned only to the operator who completed sign-in.
- **CounterPress Local Editor:** a public desktop client with `http://localhost`
  redirect URI. Its only declared API permission is the CounterPress delegated
  scope. The API preauthorizes that client for that scope.

Neither registration has a client secret or Microsoft Graph permission. No tenant
policy or subscription role was changed. Registration/object identifiers remain
in ignored, private `var/editorial-entra.json`; no tokens are saved there.
The client is for local integration, not the future browser Studio. Studio will
need its own correctly registered redirect and client flow.

The user completed Microsoft sign-in. The check verified the real token's
signature and required claims, exercised the local protected context endpoint,
rejected missing/invalid tokens, rejected the same signed token when its client
was excluded, and verified that an ineligible request does not call a model.
This proves real Entra authentication against the local API. It is not a deployed
Container Apps authentication test or an unassigned-second-user sign-in test.

Repeat explicitly from the repository root:

```sh
uv run --frozen python scripts/check_editorial_identity.py \
  --config var/editorial-entra.json
```

The script opens Microsoft's supported interactive sign-in through MSAL. Tokens
and the MSAL cache remain in memory and disappear when the process exits. Output
contains only boolean/status results. The private config requires `tenant_id`,
`api_client_id` and `client_client_id`; use the intended registrations.
No private model configuration is loaded by this check.

References: [MSAL token acquisition](https://learn.microsoft.com/en-us/entra/msal/python/getting-started/acquiring-tokens),
[public client configuration](https://learn.microsoft.com/en-us/entra/msal/python/getting-started/client-applications),
[role assignment API](https://learn.microsoft.com/en-us/graph/api/serviceprincipal-post-approleassignedto?view=graph-rest-1.0).

## Cosmos verification

The portal operator has Cosmos Data Reader access. An initial local probe was
denied at write admission; no verification item was created. Keep that account
read-only. Run the cloud probe with the app's existing managed history identity,
whose custom role permits metadata access and item read/create/replace in the
histories container. Do not grant a broad contributor role just for this check.

The probe uses fresh `verify-editorial-*` partitions for admission, leases and
presentation, plus an isolated synthetic history. It never uses the production
`editorial-control-v1` partition or demo histories. Verification records are
retained; it performs no deletion, provisioning, role or throughput change.

```sh
python scripts/check_editorial_cosmos.py seed --scope YOUR-FRESH-SCOPE \
  --output /tmp/editorial-cosmos-seed.json
# Run in a new process with the same scope and Cosmos settings:
python scripts/check_editorial_cosmos.py verify --scope YOUR-FRESH-SCOPE \
  --output /tmp/editorial-cosmos-verify.json
```

The process must explicitly have `COUNTERPRESS_STORAGE=cosmos` and the existing
private Cosmos configuration. Use managed identity inside Azure. A seed refuses
to reset an already used scope. The tests synchronize two reads to force a real
create/ETag conflict, assert one admission/dispatch claim, exhaust shared quota,
and check that an old lease owner cannot dispatch or finish replacement work.
Lease handover uses controlled timestamps, without a 30-second sleep.

The presentation test uses actual Agent Framework/editor code with a synthetic
in-memory model transport and real Cosmos persistence. It checks cached reuse,
correction invalidation and fixture-free restoration of the single-editor audit
and historical 4/3/withdrawn/2 counts in a fresh process. It makes **zero external
model calls**. This is storage evidence, not a live model-quality result.

Both phases ran from CI-verified source `b729d3f` in separate processes inside the
existing app container under its existing managed identity. A temporary source
archive was fetched at that exact revision and checked against its SHA-256 before
execution; temporary files were removed on exit. The serving app's revision,
template, configuration and identities were unchanged. The seed observed a real
409 conflict; fresh-process verification preserved the exhausted quota and
single-editor audit without reading fixture files. The initial Azure console
connection returned 404 before execution; after a readiness check, a shorter
verified bootstrap succeeded. The exact cause of that console failure is unconfirmed.

`tests/test_editorial_live_checks.py` tests the probe assertions offline with
generated signing keys and a transactional Cosmos double. MSAL is now a direct
dependency; its pinned version is unchanged. The current regression lock is
`editorial-controls-regression-v2`; the original paid pilot remains unchanged.

## Remaining activation gates

Studio sign-in, exact-version review and the bounded authenticated hosted model
check are now complete for the assigned-editor pilot. Human usefulness research
remains the gate for broader use. No new hosting service was added.
