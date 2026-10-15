# Bounded Analyst/Producer workflow

Stage 6 adds an explicit, asynchronous Microsoft Agent Framework graph. The CLI
invokes the Analyst, validates its decision, and passes a fresh evidence package
to the Producer only for a supported story. Replay polling never starts model
requests. The application still works without Azure.

## Run locally

Use the same `.env` from [adaptation setup](adaptation.md). The required variables
are `AZURE_OPENAI_ENDPOINT`, `AZURE_OPENAI_DEPLOYMENT`, and
`AZURE_OPENAI_API_KEY`. Keep keys out of source control and chat. No additional
Azure resource is required. Configuration is loaded explicitly by the command;
the framework does not discover this application's environment file.

```sh
UV_CACHE_DIR=.uv-cache uv sync --locked
UV_CACHE_DIR=.uv-cache uv run --env-file .env --frozen python -m counterpress.workflow increase --at-ms 780000
```

Other deliberate checks (each command can make paid provider requests):

```sh
# Unsupported pressure claim: narrow to counts or reject.
UV_CACHE_DIR=.uv-cache uv run --env-file .env --frozen python -m counterpress.workflow increase --candidate pressure_effectiveness
# No increase: request evidence, reject, and skip the Producer.
UV_CACHE_DIR=.uv-cache uv run --env-file .env --frozen python -m counterpress.workflow control
```

`--db` and `COUNTERPRESS_DB_PATH` select the SQLite file. Use the same file as the
API to see the result in the replay screen. The default is
`var/counterpress.sqlite3`. At 58:00 the screen shows short **Analysis activity**
labels, and a valid explanation lasts at most sixty seconds from workflow start.
The audit remains after expiry. If corrections have extended the replay, use its
latest `--at-ms`; a historical candidate is skipped before any model request.
An incomplete comparison is also skipped.

The CLI prints a sanitized JSON audit. Exit code 0 means accepted, narrowed or
rejected; 2 means fallback, skipped or failed. A rejection is a valid review
outcome. No raw model conversation or provider error body is saved.

## Evidence and decisions

The Analyst can call only these tools. They accept no parameters and cannot
change match, cutoff, team or observation windows:

| Tool | Read-only result |
| --- | --- |
| `compare_windows` | Counts for `(48:00,53:00]` and `(53:00,58:00]`, exact event revisions, and eligible evidence identity |
| `get_data_quality` | Synthetic coverage, validated possession, cutoff, and explicit absence of tracking, measured pressure and causal evidence |
| `get_event_sequence` | Last twelve canonical events in stable occurrence order, total count and truncation flag |

The Analyst must successfully request comparison and data quality before any
decision. It may accept the count increase, narrow a pressure-effectiveness
candidate to the count increase, or reject. Code checks the decision, evidence
identity, story and reason against the calculated comparison. Equal or decreasing
counts cannot produce an increase story. The fixed pitch and coordinate rules
remain documented in [contracts](contracts.md).

Before the Producer runs, code rechecks the source journal and reconstructs a
validated evidence bundle. Only the approved story, general audience, packet with
source references, metric definition, coordinate convention and required facts
enter the fresh Producer session. Analyst conversation history is absent. The
Producer selects one of the two existing templates; code checks every fact and
renders the explanation. No model prose or tactical inference becomes a fact.

## Enforced limits and publication

| Limit | Maximum per workflow |
| --- | --- |
| Analyst provider requests | 3 |
| Producer provider requests | 1 |
| Total provider requests | 4 |
| Tool invocations | 3 |
| Shared execution deadline | 8 seconds |
| Adaptation expiry | 60 seconds from start |

The shared monotonic deadline starts before snapshot preparation. A guarded HTTP
transport counts each actual provider invocation before sending it. SDK and
transport retries are disabled, redirects are disabled, and any attempted extra
invocation is checked against the same counters. Function middleware checks the
budget before each individual tool, including multiple calls in one model
response. Tools run serially; a hard-limit failure aborts the framework loop.
Framework limits provide additional best effort protection.

One `asyncio.timeout` covers the graph. Checks run at every invocation, after
responses and before publication. Cancellation and audit persistence may finish
a few milliseconds after the deadline; late output cannot be published. Provider
response bodies are limited to 64 KiB after decoding. Exceptions become fixed
reason codes, without raw diagnostics.

No database transaction spans a provider await. Other replay reads and correction
commits can proceed. Before publishing, an atomic transaction rechecks the frozen
source journal, deadline and expiry. Changed evidence discards the result. The
append-only `workflows` table records deployment, prompt version, source version,
evidence references, counters, duration, timestamped action labels and final
status. Existing databases gain the table automatically.

Snapshot responses expose a compact workflow activity view only at or after its
availability cutoff. Earlier replay positions hide later activity. Accepted
wording must still match the current evidence version and remain unexpired.
Invalid drafts, refusals, errors, rejections, timeout and stale results leave the
deterministic factual card in place (or no card when no increase is eligible).

## Verification and limits

Offline tests exercise the actual framework, SDK and HTTP boundary with scripted
responses: accepted/narrowed/rejected decisions, fresh handoff, missing evidence,
wrong facts, oversized tool batches, exhausted request budgets, deadline
cancellation, provider failures, expiry, persistence and concurrent corrections.
Frontend tests verify activity labels and clearing stale/earlier views.

The configured `REDACTED-DEPLOYMENT` deployment completed the supported workflow in
6,929 ms with three provider requests and two tools. A preceding run timed out
at 8,014 ms and correctly retained fallback. These are individual observations,
not a latency guarantee. The successful run used a smaller Producer handoff;
network and model variability may still cause fallback.

Saved sanitized audits: [accepted](verification/workflow-live-accepted.json) and
[timeout](verification/workflow-live-timeout.json). Full verification commands and
results are in [progress](progress.md).

This workflow uses the general audience only. Stage 7 now adds separate
[validated audience views and bilingual templates](audience.md). Procedural
generation and Azure application deployment remain later work.

Implementation references: Microsoft's [function tools and best effort limits](https://learn.microsoft.com/en-us/agent-framework/agents/tools/function-tools),
[Azure OpenAI provider configuration](https://learn.microsoft.com/en-us/agent-framework/integrations/by-component/model-providers/azure-openai),
and [Agent Framework OpenAI package](https://github.com/microsoft/agent-framework/blob/main/python/packages/openai/README.md).
