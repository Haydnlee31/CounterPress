# Producer Studio

Studio is the authenticated producer review workspace at `#studio`. This slice is
controlled by a separate deployment switch. The protected release workflow records
when it is enabled on the hosted app. Public Matchday remains available without sign-in. Studio uses factual templates;
opening it, reviewing, approving and exporting never invokes a model.

## Using Studio

1. Open **Producer Studio** from Matchday and select **Sign in with Microsoft**.
   Use the account assigned the API's `CounterPress.Editor` role.
2. Choose a story, story language (English or Simplified Chinese), and detail level.
   The workspace labels remain English. Studio always reviews the latest available
   source history, not a historical replay selection.
3. Read every story and its qualification. Expand **Evidence reference** to inspect
   exact evidence/revision IDs, metric disclosure and supporting recorded events.
4. Select **I reviewed this version · Approve**. This authorizes that precise
   presentation, including all displayed statements and the selected perspective.
5. Open the clean preview or download the approved, script-free HTML snapshot.
   Neither operation publishes to a broadcaster. The downloaded file includes
   synthetic-data disclosure, citations, cutoff, comparison windows and approval ID.
6. **Revoke this approval** disables preview/export. **End Studio session** clears
   the in-memory app token cache and hides the review; it does not sign out of the
   wider Microsoft account or cancel a request already accepted by the server.

A new delivery, correction, withdrawal, changed wording or perspective changes the
fingerprint. Old approval cannot authorize the new artifact. The page polls every
five seconds, hides preview during rechecks, and locks actions on failed checks.
Background browser throttling can delay polling. Approval and export always check
current server state; an already downloaded snapshot cannot be recalled. Exports
are valid at their canonical read, not a promise that facts never change afterwards.

## Architecture and authorization

React loads Microsoft Authentication Library for JavaScript only when Studio opens.
MSAL uses authorization-code/PKCE popup sign-in with a five-minute interaction timeout, a dedicated `/auth.html` redirect
bridge and memory-only access-token caching. No token, account identity, model key
or model endpoint is saved in app preferences or bundled into the frontend.
The callback follows [Microsoft's redirect bridge guidance](https://learn.microsoft.com/en-us/entra/msal/javascript/browser/login-user#redirecturi-considerations).

FastAPI checks each request independently: fixed-tenant RS256 signature, issuer,
audience, lifetime, allowlisted SPA client, delegated `Editorial.Run` scope and
`CounterPress.Editor` role. There is no anonymous preview/export API or trusted
client-side role check. `/api/studio/config` exposes only public identity metadata
when enabled. It never returns model/storage endpoints or credentials.

`StudioService` reconstructs a factual recap from immutable history. A SHA-256
fingerprint covers presentation version, exact recap (including preferences,
cutoff, windows, wording and citations), complete source records and displayed
supporting evidence. Approval/revocation records contain that fingerprint, a
pseudonymous actor, decision ID and UTC epoch milliseconds. They append to the
same scenario history as the evidence. SQLite serializes writers; Cosmos uses the
existing partition's conditional transactional batch. A conflicting correction
forces recomputation and rejects the old approval. Repeated approval/revocation
clicks are idempotent; concurrent approvals share one recorded decision.

The local SQLite migration adds `studio_decisions`. Cosmos stores the additive
field in history with the existing managed identity and container permissions;
no new resource or role grant is needed. **After decisions have been written, do
not roll back to a build that cannot read this field.** Disable Studio while keeping
a schema-compatible image if rollback is necessary. API responses never expose
stored actor hashes to the browser.

This slice intentionally does not approve expiring AI presentations. Integrating
a model attempt requires binding that attempt and its expiry to approval first.
The existing private editorial API remains independently disabled.

## Local startup and later Azure activation

Default startup remains safe and requires no Azure configuration:

```sh
uv sync --locked
npm --prefix frontend ci
npm --prefix frontend run build
COUNTERPRESS_STATIC_DIR=frontend/dist uv run --frozen uvicorn counterpress.api.main:app --host 127.0.0.1 --port 8000
```

Open `http://127.0.0.1:8000/#studio`. Without activation it shows a clear disabled
sign-in screen. A durable SQLite path is selected by default; `:memory:` is rejected
when Studio is enabled.

To activate real browser sign-in later:

1. Register a separate **single-tenant SPA** in the existing Entra tenant. Register
   the exact local callback `http://localhost:8000/auth.html` (and, for Vite,
   `http://localhost:5173/auth.html`). Use the matching `localhost` origin in the
   browser. For hosted activation, register the exact app HTTPS `/auth.html` URL.
   Do not reuse the existing desktop client's `http://localhost` callback as a SPA.
2. Give the SPA the existing API's delegated `Editorial.Run` permission and
   preauthorize that scope on the API, preserving the existing desktop client.
   Keep API user assignment required and the editor role restricted to intended
   producers. No client secret or Microsoft Graph permission is required.
3. Supply private runtime configuration (actual values never committed):
   `COUNTERPRESS_STUDIO=entra`, `COUNTERPRESS_STUDIO_CLIENT_ID`,
   `COUNTERPRESS_ENTRA_TENANT_ID`, `COUNTERPRESS_ENTRA_AUDIENCE`.
   Studio separately allows only its configured SPA client. Keep
   `COUNTERPRESS_EDITORIAL=off`; Studio needs no model configuration.
4. Verify an assigned account, a rejected unassigned account, approval/revocation,
   correction invalidation and restart using isolated history. Then release the
   reviewed image through the protected workflow and verify hosted behavior.
   The protected deployment workflow now supports explicit `studio_mode`
   enable/disable/preserve and a private identity-metadata secret; see the
   [deployment runbook](deployment.md#studio-activation-through-the-protected-workflow).
   Do not enable it on an older incompatible image.

[Real browser SPA sign-in and new Studio decisions against live Cosmos](verification/studio-integration.json)
have now passed, including local browser download/revocation/correction handling
and restoration in a fresh cloud process. The protected release records hosted
activation and anonymous-access smoke results separately. Human producer review
and a separate real unassigned-account test remain pending.

## Verification

[Local verification results](verification/studio-local.json) record the tested source,
commands, output and limits: 550 backend tests, 57 frontend tests, build and browser QA.

```sh
UV_CACHE_DIR=.uv-cache uv run --frozen --offline pytest -q
npm --prefix frontend test -- --reporter=dot
npm --prefix frontend run build
```

Automated coverage includes missing/invalid/unassigned/wrong-client tokens,
unauthenticated exports, storage failures, language/detail mismatch, no eligible
story, durable revocation, concurrent approvals, a correction between review and
commit, a Cosmos ETag conflict during commit, source changes with unchanged totals,
withdrawal/reappearance, escaping, session-end races and browser lockout on errors.
Cosmos transaction tests use the service double, not a new live Azure verification.

For repeatable local fixture browser QA (Playwright must be available to Node):

```sh
UV_CACHE_DIR=.uv-cache uv run --frozen --offline python scripts/prepare_studio_qa.py
npm --prefix frontend run dev
# In another terminal:
node scripts/test_studio.cjs http://127.0.0.1:5173
```

`CHROME_EXECUTABLE` optionally selects installed Chrome. This generates only ignored
`frontend/var/` fixture files and `var/studio-*.png` screenshots. Authentication is
mocked in this harness; it is never a production auth bypass or bundled build entry.
It checks 360/390/760/1365px layouts, source evidence, approval, preview, revocation,
session end and page errors. Stop the dev server after use.

The editorial **regression** source lock is now `studio-regression-v1` because
history/API source changed. The original paid pilot lock and report are preserved;
no new model benchmark or human usability score is claimed. Vitest was updated to
the patched 5.x line after npm audit identified vulnerabilities in its older
transitive test dependencies; the complete existing frontend suite still passes.
