"""Four bounded Azure narrative-selection canaries; explicitly opt in with --azure."""
import argparse
import asyncio
import json
import time
from pathlib import Path
from run_footie_local import local_model_settings
from counterpress.adaptation.azure import load_config,ProviderFailure
from counterpress.assistant.contracts import AskRequest
from counterpress.assistant.narrative import AzureNarrator,build_claims,render_story
from counterpress.assistant.service import AssistantService
from counterpress.personalization.service import CareerService
from counterpress.personalization.store import DataStore


async def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--azure',action='store_true')
    args=parser.parse_args()
    if not args.azure:parser.error('--azure is required for these four billable model calls')
    local_model_settings(Path('.env'));config=load_config()
    if config is None:raise SystemExit('Azure model configuration is missing.')
    store=DataStore(Path('fixtures/personalization'));service=AssistantService(CareerService(store))
    narrator=AzureNarrator(config)
    cases=[
        {'question':'How many goals does Mateo Cross have?'},
        {'question':'Compare Mateo Cross this season and last season','preferences':{'depth':'analyst'}},
        {'question':'Who leads Redhaven in assists?'},
        {'question':'Why did the latest goal matter in this match?','match_id':'career-showcase-southbank-redhaven','cutoff':{'period':2,'elapsed_ms':1632996}},
    ]
    results=[]
    try:
        for case in cases:
            request=AskRequest(**case);plan=service.local_plan(request)
            answer=service.answer(plan,request);claims=build_claims(answer,plan,request)
            started=time.monotonic()
            row={'question':request.question,'operation':plan.operation}
            try:
                async with asyncio.timeout(6):selection,usage=await narrator.explain(request.question,claims,request.preferences.depth)
                blocks=render_story(selection,claims,request.preferences.depth)
                row.update(status='accepted',usage=usage,blocks=blocks)
            except (TimeoutError,ProviderFailure,ValueError) as exc:
                row.update(status='fallback',reason='timeout' if isinstance(exc,TimeoutError) else exc.status if isinstance(exc,ProviderFailure) else 'story_rejected')
            row['duration_ms']=round((time.monotonic()-started)*1000)
            results.append(row)
            print(f"{plan.operation}: {row['status']} ({row['duration_ms']} ms)",flush=True)
    finally:store.close()
    path=Path('docs/verification/footie-narration-azure.json')
    path.write_text(json.dumps({'attempts':len(results),'results':results},indent=2)+'\n')
    print(f"Saved sanitized results: {path}")


if __name__=='__main__':asyncio.run(main())
