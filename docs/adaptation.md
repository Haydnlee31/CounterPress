# Single-call model adaptation (Stage 6, first increment)

The adapter passed offline checks and one live Azure call on 15 October 2026.
The configured `REDACTED-DEPLOYMENT` deployment returned an accepted draft in 3170 ms;
a fresh API instance recovered the matching approved wording from SQLite.
The subsequent [Analyst/Producer workflow](workflow.md) is now implemented and
verified separately. This guide covers the original single-call adapter.

## What this call can change

One frozen EvidencePacket, its registered team name and a server-assigned expiry
are sent to an explicitly configured Azure OpenAI deployment. The draft must echo
all evidence IDs, versions, counts, window bounds, period, name and expiry exactly.
Pydantic rejects unknown fields, coercions and unsupported template choices.

The model chooses one of two approved wording templates. Code inserts the verified
facts into that template and enforces a 240-character limit. Arbitrary model prose,
tactical explanations, titles and new claims are not accepted. The original Insight
and EvidencePacket remain unchanged. The snapshot's optional `adaptation` contains
only accepted wording for the matching evidence version.

The provider uses Azure's `/openai/v1/chat/completions` endpoint with a strict
`json_schema` response format generated from the Pydantic Draft contract. Every
field is required and additional properties are forbidden. Supported deployment
capability must be confirmed in the live check; a deployment name is not assumed
to be a model name. References: [Microsoft structured outputs](https://learn.microsoft.com/en-us/azure/foundry/openai/how-to/structured-outputs)
and [OpenAI structured outputs](https://developers.openai.com/api/docs/guides/structured-outputs).

## Local configuration and one live check

Use an Azure OpenAI deployment supporting structured outputs. Fill the endpoint,
actual deployment name and API key locally using `.env.example` as the template.
The key stays in the ignored `.env` file. This increment implements API-key auth;
Entra ID and cloud deployment are not configured. Azure CLI is not required.

The application never loads `.env` implicitly. The installed uv supports explicit
`--env-file` loading. From the repository root:

```sh
UV_CACHE_DIR=.uv-cache uv sync --locked
cp .env.example .env
# Edit .env locally to supply your actual Azure values before continuing.
UV_CACHE_DIR=.uv-cache uv run --env-file .env --frozen python -m counterpress.adapt increase --at-ms 780000
```

Do not repeat `cp` over an existing configured `.env`. The adaptation command makes
at most one provider request, without retries, and prints a sanitized JSON audit
record. It exits zero only for `accepted`; other recorded outcomes exit two.
Invalid configuration or unreadable history also exits two with a generic error.
Do not share keys in chat. A failed quota/rate-limit request is recorded as a provider
error; the command does not retry automatically.

For a database containing the Stage 5 correction fixture, use `--at-ms 795000`
to adapt the latest eligible version. A superseded historical packet is rejected
before calling Azure. The API, ingestion CLI and adaptation CLI must use the same
database path; `--db PATH` overrides it for a command.

Start the API using that configuration:

```sh
UV_CACHE_DIR=.uv-cache uv run --env-file .env --frozen uvicorn counterpress.api.main:app --host 127.0.0.1 --port 8000
npm --prefix frontend run dev
```

With the screen at the eligible playback position, run the adaptation command in
another terminal. Paused polling discovers the approved wording. All counts,
markers and evidence still refer to the original authoritative packet. The wording
expires after at most sixty seconds and the factual explanation returns. Model calls
are explicit CLI actions in this increment; snapshot reads and page loads never
spend tokens. There is no automatic generation endpoint or agent loop.

## Bounds, fallback and audit

The runner allows one provider request, an eight-second total asynchronous deadline,
800 completion tokens, and a 64 KiB response limit. Redirects and transport retries
are disabled. HTTP timeouts, refusals, invalid drafts, truncated responses and
provider errors are recorded without storing raw provider text or credentials.
The HTTP adapter uses the existing httpx dependency, now a runtime dependency.

The expiry is wall-clock Unix milliseconds, separate from synthetic match time.
A valid response must echo the exact server-assigned expiry. Expired results are
rejected before commit. Both snapshot selection and the frontend check expiry;
the frontend schedules a return to factual wording even between polling requests.

No database transaction spans the network call. A short SQLite write transaction
rechecks the latest authoritative evidence immediately before appending an accepted
result. If evidence changes or is withdrawn during the call, the result is recorded
as `stale` with no text. New corrections also suppress previously accepted wording
on every subsequent snapshot, including historical rewinds to a superseded version.
The old factual history remains available for rewind. A correction after a response
has been sent becomes visible on the next poll, as with other snapshot facts.

The append-only `adaptations` table records attempt ID, status, deployment, prompt
version, evidence identity/version, requested playback time, wall-clock start/expiry,
duration, provider request count and a fixed reason code. Accepted approved text is
stored; rejected provider output is not. Adding this table preserves existing Stage 5
source and lifecycle records. Accepted wording remains usable after process restart
only while its evidence is current and its expiry has not passed.

## Verification

```sh
UV_CACHE_DIR=.uv-cache uv run --frozen pytest -q
npm --prefix frontend test
npm --prefix frontend run build
```

`tests/test_adaptation.py` exercises the actual HTTP adapter with an in-process
mock transport, plus delayed providers and real SQLite transactions. Checks include
accepted wording, every echoed fact field, extra tactical prose, length, missing
configuration, no-increase and early cutoffs, refusal, rate limit, redirects,
malformed/truncated/oversized responses, timeout cancellation, expiry, restart and
correction invalidation. While a provider is suspended, another service reads
metrics and ingests corrections; the stale result is then discarded.

Frontend tests check approved text, unchanged counts, evidence-version matching
and automatic expiry fallback. These tests make no network or Azure calls. They do
not establish that a particular live Azure deployment is reachable or supports the
request schema. A separate live check now passed for the configured deployment;
its exact output is recorded in `docs/progress.md`. See the [workflow guide](workflow.md)
for the separately bounded Analyst/Producer increment.
