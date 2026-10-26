# Curated intelligence evaluation in Foundry

The exporter creates reviewable **local files only** from the independently
authored synthetic intelligence corpus and its scored evaluation report. It does
not upload, request credentials, run a judge model or read production conversations.
Production traces remain metadata-only.

## Export a preserved report

```sh
.venv/bin/python scripts/export_intelligence_foundry.py \
  --report var/footie-intelligence-unsupported-regression.json \
  --corpus fixtures/assistant/intelligence_questions.json \
  --output-dir var/foundry-intelligence-regression-example
```

The existing example contains eight unsupported-intent **local regressions**.
It demonstrates export and review, not supported-task accuracy or model quality.
For the fresh corpus, explicitly use
`--corpus fixtures/assistant/intelligence_fresh_questions.json` with its matching
report after the run completes. Export single-agent and multiagent reports into
separate new directories; compare matched case IDs and retain their original run
labels and different workflow budgets.

The exporter rejects mismatched corpus hashes/questions, duplicate cases,
changed-during-run sources, noncurated input paths, likely credentials/private
service endpoints and existing output directories. It preserves failed cases.
Missing rendered responses are explicitly excluded from content evaluation while
retaining their original deterministic scores. It never manufactures an answer
from expected facts to fill a missing response.

## Files

| File | Purpose |
| --- | --- |
| `evaluation.jsonl` | Precomputed response dataset with string `query`, `response`, `context`, `ground_truth`, plus `case_id`. |
| `execution-summaries.jsonl` | Observed roles, validated plans, call counts, token usage and completion state, where recorded. |
| `manifest.json` | Report/corpus/source/artifact hashes, original labels and scores, omitted rows and limitations. |

Evidence repeated across facts is deduplicated by fingerprint in the context.
The ground truth is a JSON serialization of independently authored expected
assertions, not a reference answer written by Footie. Use it for exact local
checks and custom evaluation, not automatic textual-similarity scoring.

The execution summary is **not** a native Foundry tool conversation. The current
benchmark records selected plans and outcomes but not a complete chronological
SDK transcript with corresponding call IDs/tool results. Inventing those messages
would misrepresent the actual bounded workflow. Consequently this export does not
claim to support tool-call accuracy, tool sequencing or instruction-adherence
metrics that require richer message capture.

## Review and run in Foundry

Microsoft documents a Dataset evaluation target for scoring preexisting outputs,
with JSONL input and column mapping. The current schema supports separate `query`
and `response` strings with supporting `context`. AI-assisted evaluation requires
an appropriate model connection and consumes model resources.

After the core release gate and remaining-budget review:

1. Inspect the exported JSONL and manifest locally, including failures and exclusions.
2. In the existing Foundry project, open **Evaluation → Create**.
3. Choose **Dataset**, then **Individual turns**, and upload `evaluation.jsonl`.
4. Map `query`, `response` and `context` to the identically named columns.
5. Select grounding and relevance evaluators that accept these columns. Review
   the chosen judge model and sample size before starting the paid run.
6. Retain `case_id` for comparison with the deterministic scores in the manifest.
   Use the original label plus source hash in the run name. A repeated or tuned
   corpus is regression evidence, regardless of what the portal score calls it.

Do not select a hosted-agent target: Footie still runs in Container Apps, and its
external-agent registration is monitoring metadata. Do not export production
trace contents just to satisfy a content evaluator. Judge-model scores supplement
exact calculations and human football review; they cannot establish the truth of
unsupported tactical causality.

Official sources checked 23 October 2026:

- [Foundry evaluation dataset schema](https://learn.microsoft.com/en-us/azure/foundry/observability/how-to/evaluation-dataset-schema)
- [Run evaluations in the Foundry portal](https://learn.microsoft.com/en-us/azure/foundry/how-to/evaluate-generative-ai-app)
- [Agent evaluator input formats](https://learn.microsoft.com/en-us/azure/foundry-classic/how-to/develop/agent-evaluate-sdk)

## Verification

```sh
.venv/bin/python -m pytest -q tests/test_foundry_intelligence_export.py
```

Seventeen independent tests cover provenance, failure preservation, hashes,
missing response handling, content filtering, allowlisted fields, curated-path
restriction and preservation of existing exports. No cloud API is exercised.
Pattern-based secret checks are deliberately conservative and not a guarantee;
local human review remains necessary before uploading any artifact.

## Publish deterministic contracts without a judge model

`scripts/publish_intelligence_foundry.py` publishes **precomputed synthetic
outputs** to the existing CounterPress Foundry project. Footie continues running
in Container Apps. This path uses the project client's OpenAI Evals API with
`type="custom"`, `include_sample_schema=false`, inline JSONL items and two
`type="python"` testing criteria. It creates no hosted agent, model deployment,
endpoint evaluator, or judge-model request.

The Microsoft [Foundry Evals REST reference](https://learn.microsoft.com/en-us/rest/api/microsoft-foundry/azureopenai/evals#openaievalgraderpython)
documents Python criteria with `source` and `pass_threshold`.
The [evaluation creation reference](https://ai.azure.com/api-reference/evals/create-eval/)
also supports this criterion on the project evaluation surface. The script uses
`AIProjectClient.get_openai_client()` with the optional `foundry-admin`
dependencies; its wire payload is tested using the actual Projects/OpenAI SDKs
and an in-memory HTTP transport. No model name is needed for this direct Python
grader path. This differs from a registered catalog code evaluator, whose
orchestration schema currently asks for a deployment name.

Two metrics have deliberately narrow meanings:

- **local_contract_pass** imports the original deterministic pass and its boolean
  checks. Failed cases remain failed; this is not a fresh AI quality judgment.
- **recorded_fact_assertions** independently recomputes the exported status,
  numeric or presence-only anchors, null metrics, required subjects and available
  event/availability boundaries against the authored expectations. It does not
  re-evaluate every local check: analysis routing, replay links, historical
  denominator semantics and usefulness may require information beyond the export.

Neither metric is called groundedness, instruction adherence, native tool-call
accuracy, or football causality. An empty recorded response stays empty and stays
in the local-score denominator; the fact-assertion metric assigns it zero.

### Review first

The command defaults to a local dry run. It validates the reviewed manifest SHA,
recreates the export from its bound original report and curated corpus, and
compares every artifact byte. It refuses more than 64 scored rows, datasets over
8 MB, unreviewed corpus paths, changed artifacts and mismatched source claims.
It does not alter the exporter, expected answers or preserved reports.

```sh
.venv/bin/python scripts/publish_intelligence_foundry.py \
  --export-dir var/foundry-warm-release-full \
  --report var/footie-intelligence-warm-release-full.json \
  --manifest-sha256 <reviewed-manifest-sha256> \
  --source-status historical \
  --release-label warm-release-20261024
```

The 24 October warm-release export contains 40/40 original regression passes.
Six recorded backend source hashes differ from the later `b0ef550` runtime.
It is historical evidence, not a certificate for the current release. A repeat
on the same 40-case corpus remains **regression** evidence. The later 48-case
`intelligence_questions.json` suite is a different corpus: publish its full
denominator and failures separately, without claiming a matched improvement
over the earlier 40-case run. Each preserved run gets a new export directory. `--source-status current` requires every recorded
source hash to match the current checkout. Compare matched case IDs, identical
corpus/grader hashes and original workflow budgets. Do not compare a small
success-only subset against the historical full denominator.

### Controlled publication

The operator supplies a mode-0600 private JSON configuration derived from the
existing project's ARM metadata. It contains only `project_endpoint`,
`endpoint_sha256`, `project_resource_sha256`, `project_name`, `account_name`, and
`resource_group`. Its canonical sorted compact JSON SHA256 must be reviewed
separately and supplied with `--project-binding-sha256`. The fixed resource names,
endpoint path/host and endpoint hash are checked before authentication. The
endpoint and resource identity are never printed.

After reviewing the exact dry-run plan, repeat its arguments with:

```sh
  --apply \
  --project-config <private-project-config.json> \
  --project-binding-sha256 <reviewed-project-binding-sha256> \
  --poll-seconds 30
```

The submitting identity needs the existing project's evaluation permissions;
see Microsoft's [evaluation permissions guide](https://learn.microsoft.com/en-us/azure/foundry/observability/how-to/evaluation-permissions).
No production transcript or telemetry-message capture is enabled. The script
uses Azure CLI identity, disables SDK request retries and rejects verbose SDK
logging. It may incur evaluation-service execution/storage usage even though it
makes no target or judge inference calls.

Private receipts live in `var/foundry-publication-receipts/` (directory 0700,
files 0600). A publication key binds project, reviewed manifest and grader.
Receipts are written **before** each cloud mutation. A lost mutation response
blocks further submission and requires an operator to reconcile the existing
remote object; do not delete the receipt or blindly rerun under another identity.
A known pending run can be resumed with the same command: only bounded reads are
retried, and no second run is submitted. Completed receipts return their prior
verification result. No automatic delete or reset operation exists.

The final check reads every remote row, matches its exact submitted case data,
compares both scores against local execution of the same grader programs, and
rejects errors or unexpected model usage. Preserve failure receipts and compare
runs using the Foundry evaluation view and original case IDs. The publication
job's duration/tokens are not the original application's latency/token measures.

```sh
.venv/bin/python -m pytest -q \
  tests/test_foundry_intelligence_export.py \
  tests/test_foundry_intelligence_publication.py
```

The publication suite includes failed-anchor controls, future evidence,
unknown subjects, missing responses, source drift, artifact tampering, private
project binding, the 64-row cap, idempotent receipts, uncertain-mutation recovery,
remote score substitution and actual SDK request serialization. The SDK wire
test requires the optional `foundry-admin` dependencies; all other controls run
without them. Tests do not contact Azure.
