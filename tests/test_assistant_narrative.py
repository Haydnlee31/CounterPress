"""Narration cannot author prose, swap a subject or outlive an evidence correction."""
import asyncio
import json
from pathlib import Path
import httpx
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import SecretStr
from counterpress.adaptation.azure import AzureConfig,ProviderFailure
from counterpress.assistant.api import install_assistant
from counterpress.assistant.contracts import AskRequest
from counterpress.assistant.narrative import AzureNarrator,build_claims,default_story,render_story
from counterpress.assistant.service import AssistantService,blank
from counterpress.personalization.service import CareerService
from counterpress.personalization.store import DataStore

ROOT=Path(__file__).resolve().parents[1]
MID='career-showcase-southbank-redhaven'

@pytest.fixture(scope='module')
def service():
    store=DataStore(ROOT/'fixtures/personalization')
    yield AssistantService(CareerService(store))
    store.close()

def claims_for(service,q,**kwargs):
    request=AskRequest(question=q,**kwargs)
    plan=service.local_plan(request);answer=service.answer(plan,request)
    return build_claims(answer,plan,request),answer

def test_rate_has_explicit_denominator_and_source_binding(service):
    claims,answer=claims_for(service,'How many goals does Mateo Cross have?')
    rate=next(c for c in claims if c['kind']=='rate')
    assert '0.54 goals per appearance: 75 in 140 appearances' in rate['text']
    assert rate['fact_indices']==[0] and len(rate['evidence_id'])==64
    assert 'probability' not in rate['text']
    story=render_story({'lead':rate['id'],'supporting':[]},claims,'casual')
    assert story==[rate] and answer['facts'][0]['value']==75

@pytest.mark.parametrize('bad',[
    {'lead':'invented','supporting':[]},
    {'lead':'c0','supporting':['c0']},
    {'lead':'c0','supporting':[],'text':'Mateo has 999 goals'},
    {'lead':'c0','supporting':['c1','c2']},
])
def test_injected_text_unknown_and_excessive_claims_rejected(service,bad):
    claims,_=claims_for(service,'How many goals does Mateo Cross have?')
    with pytest.raises(ValueError):render_story(bad,claims,'casual')

def test_season_comparison_names_both_periods_and_unequal_exposure(service):
    claims,_=claims_for(service,'Compare Mateo Cross this season and last season')
    comparison=next(c for c in claims if c['kind']=='comparison')
    assert '2025-26' in comparison['text'] and '2026-27' in comparison['text']
    assert 'recorded 7 more goals' in comparison['text'] and 'appearances respectively' in comparison['text']
    assert comparison['text'].count('Mateo Cross')==1
    assert comparison['fact_indices']==[1,0]

def test_null_and_partial_coverage_do_not_become_performance_claims(service):
    claims,_=claims_for(service,'How many saves does Rory Ellis have?')
    assert claims==[]
    request=AskRequest(question='Compare Rory Ellis and Dario Voss in goals per 90')
    plan=service.local_plan(request);answer=service.answer(plan,request)
    answer['facts'][0]['coverage']['recorded_matches']=1
    claims=build_claims(answer,plan,request)
    assert not any(c['kind']=='comparison' for c in claims)
    assert 'This covers 1 of' in claims[0]['text']

def test_exact_tie_is_not_a_winner_and_percentage_gap_has_correct_unit(service):
    request=AskRequest(question='Compare Rory Ellis and Dario Voss in goals per 90')
    plan=service.local_plan(request);answer=service.answer(plan,request)
    for f in answer['facts']:f['value']=0.5
    claims=build_claims(answer,plan,request)
    assert 'are level' in claims[-1]['text'] and 'per 90 minutes' in claims[-1]['text']
    for f in answer['facts']:f.update(metric='pass_accuracy',label='Pass completion',unit='percent')
    answer['facts'][0]['value']=80;answer['facts'][1]['value']=75
    claims=build_claims(answer,plan,request)
    assert 'by 5 percentage points' in claims[-1]['text']

def test_milestone_respects_playback_boundary_and_language(service):
    before,_=claims_for(service,'Why did the latest goal matter?',match_id=MID,cutoff={'period':2,'elapsed_ms':1632995})
    after,answer=claims_for(service,'Why did the latest goal matter?',match_id=MID,cutoff={'period':2,'elapsed_ms':1632996})
    assert not any('75th' in c['text'] for c in before)
    assert any('75th' in c['text'] for c in after)
    assert all(answer['facts'][i]['evidence']['event_digest'] for c in after for i in c['fact_indices'])
    chinese,_=claims_for(service,'Mateo Cross有多少进球',preferences={'language':'zh-Hans'})
    assert chinese==[] # Keep the existing localized answer instead of injecting English prose.

class Planner:
    def __init__(self):self.calls=0
    async def plan(self,*args):
        self.calls+=1
        return blank('stats',player_ids=['rh09']),{}

class Narrator:
    def __init__(self,failure=None):self.calls=0;self.failure=failure
    async def explain(self,q,claims,depth):
        self.calls+=1
        if self.failure:raise self.failure
        return {'lead':claims[-1]['id'],'supporting':[]},{'total_tokens':20}

def client_for(service,planner,narrator):
    app=FastAPI();install_assistant(app,lambda:service.career,planner,narrator)
    return TestClient(app)

def test_shared_hourly_budget_counts_both_stages(service):
    planner=Planner();narrator=Narrator()
    with client_for(service,planner,narrator) as client:
        for i in range(11):
            r=client.post('/api/fan/assistant/ask',json={'question':'How many goals does Mateo Cross have?'}).json()
            assert r['facts'][0]['value']==75
            assert r['narrative']['mode']==('azure_selected' if i<10 else 'calculated')
        assert planner.calls==narrator.calls==10
        assert r['fallback_reason']=='hourly_limit'

@pytest.mark.parametrize('failure',[TimeoutError(),ValueError('untrusted model details'),ProviderFailure('invalid','untrusted')])
def test_narration_failure_preserves_facts_and_safe_calculated_story(service,failure):
    with client_for(service,Planner(),Narrator(failure)) as client:
        r=client.post('/api/fan/assistant/ask',json={'question':'How many goals does Mateo Cross have?'}).json()
        assert r['facts'][0]['value']==75 and r['narrative']['mode']=='calculated'
        assert r['narrative']['blocks'] and 'untrusted' not in json.dumps(r)

def test_unsupported_does_not_call_either_model(service):
    planner=Planner();narrator=Narrator()
    with client_for(service,planner,narrator) as client:
        r=client.post('/api/fan/assistant/ask',json={'question':'Predict the next winner'}).json()
        assert r['status']=='unsupported' and not r['narrative']['blocks']
        assert planner.calls==narrator.calls==0

def test_correction_during_narration_rebuilds_story_and_evidence():
    store=DataStore(ROOT/'fixtures/personalization');service=AssistantService(CareerService(store))
    class RevisingNarrator(Narrator):
        async def explain(self,q,claims,depth):
            record=store.original(MID);goal=next(e for e in record.events if e.event_id=='e01178')
            store.ingest(MID,[goal.model_copy(update={'revision':2,'delivery_sequence':max(e.delivery_sequence for e in record.events)+1,
                'available_period':2,'available_ms':2700100,'retracted':True})])
            return {'lead':claims[-1]['id'],'supporting':[]},{}
    try:
        with client_for(service,Planner(),RevisingNarrator()) as client:
            r=client.post('/api/fan/assistant/ask',json={'question':'How many goals does Mateo Cross have?'}).json()
            assert r['facts'][0]['value']==74 and r['narrative']['fallback_reason']=='records_changed'
            assert '74 in 140' in r['narrative']['blocks'][0]['text']
            assert '75' not in ' '.join(b['text'] for b in r['narrative']['blocks'])
    finally:store.close()

def test_narrator_transport_only_accepts_ids_and_bounds_response(service):
    claims,_=claims_for(service,'How many goals does Mateo Cross have?')
    seen=[]
    def transport(request):
        payload=json.loads(request.content);seen.append(payload)
        assert payload['max_completion_tokens']==180
        schema=payload['response_format']['json_schema']['schema']
        assert schema['additionalProperties'] is False
        assert schema['properties']['lead']['enum']==[c['id'] for c in claims]
        assert 'evidence' not in payload['messages'][1]['content'] # No full ledger in model input.
        return httpx.Response(200,json={'choices':[{'finish_reason':'stop','message':{'content':'{"lead":"c0","supporting":[]}'}}]})
    config=AzureConfig(endpoint='https://example.openai.azure.com',deployment='test',api_key=SecretStr('not-a-key'))
    narrator=AzureNarrator(config,httpx.MockTransport(transport))
    selection,_=asyncio.run(narrator.explain('Question',claims,'casual'))
    assert render_story(selection,claims,'casual')[0]==claims[0] and len(seen)==1
    narrator=AzureNarrator(config,httpx.MockTransport(lambda _:httpx.Response(200,content=b'x'*32769)))
    with pytest.raises(ProviderFailure):asyncio.run(narrator.explain('Question',claims,'casual'))
