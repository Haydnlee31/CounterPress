# Footie documentation

Start with the [project README](../README.md), [demo video](https://www.youtube.com/watch?v=vqpPXBcn0R0) and [judge walkthrough](demo-guide.md). No account or developer setup is required to explore the hosted app.

## Product and intelligence

| Reference | Purpose |
|---|---|
| [Analyst Mode](analyst-mode.md) | Replay, player focus, conversation and full-time report |
| [Conversation and reports](analyst-room.md) | Current scheduler, review, memory and report contracts |
| [Analyst metrics](analyst-metrics.md) | Denominators, spatial views and source coverage |
| [Highlights](highlights-workspace.md) | Saved moments, summaries, annotations and browser storage |
| [Footie assistant](grounded-assistant.md) | Grounded questions, tools and specialist coordination |
| [Fan personalization](fan-personalization.md) | Preferences, recommendations and read APIs |
| [Player analytics](player-analytics.md) | Profile statistics and visual definitions |
| [Highlight commentary](live-companion.md) | Synchronized spoken narration |

## Data and engineering

- [Data provenance](../README.md#data-and-scope), [career generation and APIs](personalization-data.md), [position calibration](position-calibration.md), and [match generation](calibrated-generator.md).
- [Foundation contracts](contracts.md), [history and corrections](history.md), and [Cosmos persistence](cosmos.md).
- [Event streaming](streaming.md), [career revision bridge](career-revision-bridge.md), and [source capabilities](intelligence-source-capabilities.md).
- [Deployment](deployment.md), [operations](operations.md), [model identity](model-identity.md), and [Foundry monitoring](footie-foundry-monitoring.md).
- [Native Foundry integration](analyst-foundry.md) describes the separate native path. The current live Analyst scheduler is documented in [conversation and reports](analyst-room.md).

## Validation and historical reference

The [verification directory](verification/) retains evaluation methods, observed test results and release evidence. Dated reports describe the revision tested, not a promise of current live behavior. The [Analyst acceptance history](verification/analyst-release-history.md) preserves failures and subsequent corrections separately from the current setup guide.

The [historical archive](archive/) preserves development evidence, the Reactor design reference and retired Studio/interface contracts. These are engineering references; Studio is not part of the current public navigation. Superseded task plans and duplicate local handoff guides have been removed. Historical material must not be used as current deployment instructions.
