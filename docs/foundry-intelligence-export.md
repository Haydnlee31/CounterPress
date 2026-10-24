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
