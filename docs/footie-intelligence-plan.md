# Football intelligence design

This reference describes the design principles shared by Footie's grounded assistant, personalized insights and Analyst Mode. Current runtime details are in [conversation and reports](analyst-room.md); evaluation evidence is in the [intelligence verification report](verification/footie-intelligence.md).

## Explain, show the evidence, offer a next step

A useful answer connects a football question to a supported explanation, then offers the relevant replay, player record or comparison. Casual and detailed presentations can differ in depth and emphasis while preserving the same facts.

| Question | Evidence | Useful next step |
|---|---|---|
| What made that goal happen? | Linked actions and participants before the finish | Replay the buildup |
| How is my player doing? | Current involvement and a comparable historical baseline | Open the player profile or cited moments |
| What changed in the game? | Comparable completed windows and supported differences | Inspect a representative passage |

## Computation and interpretation

Python reducers own totals, eligibility, denominators and temporal selection. Models interpret bounded evidence; they do not replace the statistical engine. Missing coverage stays unavailable. Source corrections can update or withdraw findings rather than silently preserving old claims.

The general assistant uses read-only tools for match and career questions. The live Analyst scheduler selects specialist turns, supplies accepted peer context and checks each draft before publication. The full-time report considers match-wide evidence with a larger analysis context. These paths share evidence principles but have distinct runtime contracts.

## Reliability boundaries

- Separate factual checks from usefulness checks: an accurate count can still be repetitive or unhelpful.
- Preserve source time and revision when presenting asynchronous output.
- Deduplicate identical work and reject stale results after source or viewing-context changes.
- State unavailable tracking information rather than derive defender ability from illustrative replay positions.
- Keep model output, rejected drafts and diagnostics separate from authoritative records.

See [source capability definitions](intelligence-source-capabilities.md), [career corrections](career-revision-bridge.md), [Foundry monitoring](footie-foundry-monitoring.md) and [evaluation export](foundry-intelligence-export.md) for the supporting contracts.
