# Analyst Mode

Open **Match Centre → Watch full match → Analyst Mode**, or use `#analyst`. Select a match, choose a player in the Player Analyst desk and press **Play match**. Playback speed changes the replay clock; findings retain their own source timestamps.

## Interface

Player, Match, Chance and Defensive analysts surround the pitch on desktop. Smaller screens use a compact desk selector. Team crests, score and source clock identify the game. The latest accepted contribution stays visible; earlier conversation can be expanded. Statistics dialogs provide detailed player and team views without permanently crowding the replay.

The conversation connects linked passages of play and earlier accepted findings. Evidence links let the viewer inspect the underlying actions. At full time, **Match summary** opens an automatically generated report with team coaching briefs and spatial evidence.

## Runtime

The current live conversation uses an application-managed turn scheduler in Azure Container Apps, with Azure OpenAI authoring and independent review. The general Footie assistant uses Microsoft Agent Framework. A separate native Foundry integration is documented in [analyst-foundry.md](analyst-foundry.md); it is not the current live scheduler.

See [conversation and report contracts](analyst-room.md) and [metric definitions](analyst-metrics.md). The adapter supports three full matches: one generated fixture and two licensed adapted archives. The fourth featured data fixture supplies career history and highlights but is not registered in this full-match adapter.

## Local preview

```sh
npm --prefix frontend run build
uv run --frozen python scripts/run_analyst_local.py --discussion --port 8018
```

Open `http://127.0.0.1:8018/#analyst`. Live discussion requires server-side Azure model configuration. Without `--discussion`, the preview provides metrics without pretending to run model analysis. Credentials and private activation manifests must remain outside source control.

## Operational behavior

Shared results avoid duplicate model work for identical evidence and preferences. Seeking, changing matches and source corrections protect against stale findings. Short request-rate limits, two concurrent jobs, bounded model turns and timeouts remain in force. Cumulative application spending caps default to off for the judging deployment; provider quotas and subscription limits still apply. See [operations](operations.md) for deployment checks.
