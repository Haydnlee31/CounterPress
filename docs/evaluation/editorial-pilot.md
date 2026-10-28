# Editorial workflow pilot

This development pilot compares deterministic templates, one Microsoft Agent
Framework editor, and the existing Analyst → Producer workflow on identical frozen
histories. It is a decision aid before hosted AI activation, not a claim that more
agents improve the product. Human usefulness ratings are still required.

## Frozen protocol

`fixtures/evaluation/editorial_cases.json` contains 15 cases: eight positive cases
covering four story families in English and Simplified Chinese, plus no-change,
incomplete, wrong-player, recovery-control-with-another-story, withdrawal,
restoration with reversed duplicate delivery, and historical-after-correction cases.
The expected counts/fractions are written separately from the renderer, using the
existing independently reviewed fixture controls. Negative recovery eligibility
does not imply no eligible progression story.

`editorial_lock.json` hashes the case manifest, fixture inputs, backend source and
Python dependency lock. Drift fails the runner. Freeze/version the suite before
observing model results; do not tune on these cases and call them held-out. All
these fixtures are previously used development data. The first live run uses two
repetitions with rotated variant order. Each variant receives a fresh in-memory
SQLite history. No production Cosmos or Event Hubs history is mutated.

## What the alternatives can do

| Variant | Model work | Shared constraints |
| --- | --- | --- |
| Template | None; display all ranked factual stories with the requested depth. | Same evidence, preference ranking, renderer and qualifications. |
| Single editor | One structured Agent Framework call receives frozen facts, limits and approved wording; may accept, narrow or reject and select brief/detailed wording. | Same eight-second service deadline, final atomic freshness check, exact citations and sixty-second presentation expiry. |
| Analyst/Producer | Analyst reads two evidence tools and decides which eligible stories survive; Producer receives a fresh reviewed package and chooses approved wording. | Existing maximum four provider requests and three tool calls; typically three requests and two tools. |

Neither model variant can create facts, introduce a new claim, invent a tactical
cause, reorder stories against the source ranking, change language or remove
qualifications. Rejection, timeout, malformed output, changed evidence or expiry
retains the complete factual recap. A fallback is scored as a supported displayed
presentation, **not** as a successful AI adaptation.

The single editor is an opt-in evaluation service. There is no new HTTP endpoint,
no anonymous paid trigger and no automatic activation on polling. The Cosmos
serialization/restart test uses the existing transactional service double, not a
new live Cosmos integration claim.

## Run and inspect

The observed results below belong to the archived source commit `ce4cf9e` and
unchanged `editorial_lock.json`. After the access-controls increment, the current
CLI uses `editorial_controls_lock.json` with suite name
`editorial-controls-regression-v2`. It reruns the same cases against current code;
it does not reproduce or extend the original paid pilot. No new paid run has been
performed. To reproduce the original protocol, use its recorded source commit in
an isolated checkout.

Offline, without loading any cloud configuration:

```sh
uv run --frozen python -m counterpress.evaluation.editorial \
  --output var/editorial-offline.json
```

Explicit paid local pilot using the existing private `.env`:

```sh
UV_CACHE_DIR=.uv-cache uv run --env-file .env --frozen \
  python -m counterpress.evaluation.editorial --live --repetitions 2 \
  --output var/editorial-live.json
```

The CLI prints numeric/status summaries only. Output files also retain validated,
application-rendered presentations for review. No endpoint, deployment name,
credentials, raw transcript, provider diagnostics or free-form provider prose is
included. A nonzero exit means the evaluation did not complete or a structural
check failed; a successful exit does not mean every AI attempt succeeded.

Microsoft Agent Framework's pinned `LocalEvaluator` runs deterministic checks for
supported presentations and zero dispatched calls on ineligible cases. This uses
no paid model judge or Foundry evaluation service. The evaluation API is marked
experimental in the pinned package; dependencies remain locked. The framework
supports local checks and repetitions, but the football-specific checks are ours:
[Microsoft evaluation documentation](https://learn.microsoft.com/en-us/agent-framework/agents/evaluation).

## Measurements and limits

- Record end-to-end local duration including history preparation and rendering;
  record workflow duration separately. This is not browser/network latency.
- Report P50, maximum, fallback counts, accepted/narrowed counts, calls, tools and
  observed token usage. Empirical P95 is omitted below 20 eligible samples per
  variant; a small pilot percentile is not a production SLO or reliability claim.
- A request with no usage receipt, including cancellation, has unknown usage.
  Never price it as zero. Cost per accepted output includes failed attempts and
  stays unknown when any usage receipt is missing.
- Before transport dispatch, cap the run at 96 requests, each at 65,536 request
  bytes and 650 output tokens, with a US$1 conservative admission estimate. Reserve
  UTF-8 request bytes plus 4,096 token overhead at the configured estimate rates;
  never refund that reservation after a failure. No implicit retries or redirects.
- The estimate uses US$0.44/million input and US$1.76/million output tokens, above
  the existing GlobalStandard GPT-4.1 mini retail rates of US$0.40/US$1.60 observed
  on 17 October 2026. Cached-input discounts are omitted. It is not an invoice,
  guaranteed billing cap, durable quota, or replacement for current cost review.
  Source: [Azure retail pricing API](https://prices.azure.com/api/retail/prices?%24filter=contains%28meterName%2C%20%274.1%27%29%20and%20armRegionName%20eq%20%27eastus%27).

The approved project envelope remains US$75 total. Azure Cost Management's
preflight query reported approximately US$0.16 month-to-date for the subscription;
this can lag usage, includes more than model calls, and is not remaining credit.
No service or spending-limit configuration changed.

## Decision rule

Require all published output to retain exact supported facts, citations, language,
order and qualifications. Ineligible cases must dispatch zero calls. Evaluate AI
success separately from safe fallback. Prefer templates unless a blinded human
review demonstrates a useful gain from editorial selection/wording. Prefer one
editor over two roles if usefulness is comparable and calls/latency are lower.
Do not treat a more complex agent graph or a shorter string as a usefulness win.

Prepare anonymous side-by-side outputs for at least five fans and two producer
reviewers. Hide variant names, cost and latency while scoring clarity, relevance,
completeness and usefulness (1–5), collect reasons, and rotate display order.
Reveal the labels only after scoring. Report the actual sample and disagreement;
do not claim a statistically significant result from this small formative study.
Generate printable anonymous comparison sheets after the pilot:

```sh
python3 scripts/editorial_review.py var/editorial-live.json --language en
python3 scripts/editorial_review.py var/editorial-live.json --language zh-Hans
```

Share the generated HTML sheet, keeping the separate `-key.json` from reviewers
until scoring is complete. The sheets contain the first repetition's eligible
presentations in rotated A/B/C order and blank rating fields. They do not invent
ratings. Generated sheets and raw human responses stay under ignored `var/`.
The [fan task kit](fan-usability.md) tests the live interface separately.

The [access-controls increment](../archive/editorial-access.md) implements explicit
authenticated triggering, shared deduplication, durable quotas, revision-bound
caching and stale-work cancellation. Real Entra/Cosmos integration checks and
human review remain activation gates; this local benchmark does not satisfy them.

## Observed pilot — 17 October 2026, Singapore time

The protocol/code were frozen at commit `ce4cf9e` before the paid run. Two repetitions
produced 90 rows: 30 per variant, including 22 model-eligible rows per variant.
All 90 displayed presentations passed both deterministic checks. Ineligible cases
made no paid requests. No prompt tuning or rerun was performed after inspecting
these results. Full sanitized data: [editorial-pilot.json](../verification/editorial-pilot.json).

| Variant | Valid AI adaptations / eligible attempts | Eligible fallbacks | Median local time | Empirical P95 | Dispatched requests |
| --- | --- | --- | --- | --- | --- |
| Template | Not applicable; 30/30 supported baseline displays | 0 | 27 ms | 98 ms | 0 |
| Single editor | 21/22 (18 accepted, 3 narrowed) | 1 timeout | 4,610 ms | 6,248 ms | 22 |
| Analyst/Producer | 13/22 | 6 timeouts, 3 invalid responses | 7,323 ms | 8,153 ms | 61 |

The single editor changed the displayed recap in 14 cases; the two-role graph in
8. This measures selection/wording differences, not usefulness. Safe fallback
explains why every displayed result can pass while AI acceptance differs. Deadline
cancellation and final audit/rendering overhead can finish slightly after eight
seconds; late model wording is not published.

Of 83 dispatched calls, six had no usable token receipt. Known receipts estimated
US$0.10281172 at the conservative uncached rates; **total actual inference cost and
cost per accepted adaptation remain unknown** because the missing receipts may
still be billed. The admission reservation was US$0.54624944 of the US$1 allowance.
The reservation is not observed spend. No new Azure service was created.

Decision: retain templates as the immediate fan-facing default. Use the single
editor as the candidate for a bounded, authenticated editorial integration. The
current two-role graph does not justify its extra calls and fallbacks in this pilot;
do not add more agents. Before activating AI, collect the blinded human scores and
verify the explicit trigger, durable quota, cache and stale-work gates above in
the real deployment.
Human participants will be arranged later; all forms and rating fields remain blank.

The public app remains on the previously verified Matchday image; this benchmark
ran locally against Azure OpenAI and did not publish anything to the cloud app.
Deploy the expanded audit schema before writing single-editor attempts to shared
Cosmos histories; the old hosted image understands only the two-role prompt version.
