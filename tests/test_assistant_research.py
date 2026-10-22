"""Real Agent Framework loop with a fake Azure transport; no paid calls."""
import asyncio
import json
from pathlib import Path

import httpx2
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import SecretStr, ValidationError

from counterpress.adaptation.azure import AzureConfig, ProviderFailure
from counterpress.assistant.api import install_assistant
from counterpress.assistant.contracts import AskRequest, Plan
from counterpress.assistant.research import ResearchAgent
from counterpress.assistant.service import AssistantService, blank
from counterpress.personalization.service import CareerService
from counterpress.personalization.store import DataStore

ROOT=Path(__file__).resolve().parents[1]
CONFIG=AzureConfig(endpoint='https://example.openai.azure.com',deployment='test',api_key=SecretStr('fake'))

@pytest.fixture(scope='module')
def service():
    store=DataStore(ROOT/'fixtures/personalization')
    yield AssistantService(CareerService(store))
    store.close()


def fake_agent(plan, *, repeated=False, wrong_story=False, mutation=None):
    calls=[]
    def transport(request):
        body=json.loads(request.content);calls.append(body)
        if len(calls)==1 or repeated:
            message={'role':'assistant','content':None,'tool_calls':[{'id':'read1','type':'function',
                'function':{'name':'read_football_records','arguments':plan.model_dump_json()}}]}
            finish='tool_calls'
        else:
            tool_message=next(m for m in body['messages'] if m['role']=='tool')
            evidence=json.loads(tool_message['content'])
            claims=evidence['sentences']
            if mutation:mutation()
            message={'role':'assistant','content':json.dumps({'lead':'invented' if wrong_story else claims[0]['id'] if claims else '', 'supporting':[]})}
            finish='stop'
        return httpx2.Response(200,json={'id':'test','object':'chat.completion','created':1,'model':'test',
            'choices':[{'index':0,'finish_reason':finish,'message':message}],
            'usage':{'prompt_tokens':10,'completion_tokens':20,'total_tokens':30}})
    return ResearchAgent(CONFIG,lambda:httpx2.MockTransport(transport)),calls


def test_real_framework_tool_cycle_returns_grounded_compound_answer(service):
    request=AskRequest(question='How many goals and assists does Mateo Cross have?')
    agent,calls=fake_agent(service.local_plan(request));reservations=[]
    def reserve():reservations.append(1);return True
    result=asyncio.run(agent.research(service,request,reserve))
    assert len(calls)==len(reservations)==result.requests==2
    assert result.tools==1 and result.usage['total_tokens']==60
    assert set([result.plan.metric,*result.plan.additional_metrics])=={'goals','assists'}
    assert result.evidence_id and result.selection.lead=='c0'
    assert len(calls[0]['tools'])==1
    assert calls[0]['tool_choice']['function']['name']=='read_football_records'
    assert 'response_format' not in calls[0]
    assert calls[1]['tool_choice']=='none'
    assert calls[1]['response_format']['json_schema']['schema']['properties']['lead']['enum'][0]=='c0'
    assert 'api-key' not in json.dumps(calls)


@pytest.mark.parametrize('failure',['subject','metric','scope','repeat','story','allowance'])
def test_invalid_agent_read_or_narrative_fails_closed(service,failure):
    request=AskRequest(question='How many goals and assists does Mateo Cross have?')
    plan=service.local_plan(request)
    if failure=='subject':plan=plan.model_copy(update={'player_ids':['rh08']})
    if failure=='metric':plan=plan.model_copy(update={'additional_metrics':[]})
    if failure=='scope':plan=plan.model_copy(update={'season':'2026-27'})
    agent,calls=fake_agent(plan,repeated=failure=='repeat',wrong_story=failure=='story')
    with pytest.raises(ProviderFailure):
        asyncio.run(agent.research(service,request,lambda:failure!='allowance'))
    assert len(calls)<=2
    if failure=='allowance':assert not calls


def test_api_agent_mode_keeps_existing_response_and_safe_fallback(service):
    request=AskRequest(question='How many goals and assists does Mateo Cross have?')
    for wrong in (False,True):
        agent,_=fake_agent(service.local_plan(request),wrong_story=wrong)
        app=FastAPI();install_assistant(app,lambda:service.career,researcher=agent)
        with TestClient(app) as client:
            assert client.get('/api/fan/assistant/config').json()['workflow']=='agent'
            response=client.post('/api/fan/assistant/ask',json=request.model_dump(by_alias=True))
        assert response.status_code==200
        answer=response.json()
        assert answer['mode']==('lookup_fallback' if wrong else 'azure_agent')
        assert next(f for f in answer['facts'] if f['metric']=='goals')['value']==75
        assert answer['visual']['kind']=='groups'
        assert answer['narrative']['mode']==('calculated' if wrong else 'agent_selected')


def test_compound_contract_is_bounded_and_preserves_missingness(service):
    with pytest.raises(ValidationError):Plan.model_validate({**blank('stats').model_dump(),'additional_metrics':['goals']})
    with pytest.raises(ValidationError):Plan.model_validate({**blank('stats').model_dump(),'additional_metrics':['assists','shots','saves']})
    request=AskRequest(question='Show Rory Ellis goals and saves')
    answer=service.answer(service.local_plan(request),request)
    assert next(f for f in answer['facts'] if f['metric']=='saves')['value'] is None
    assert len(answer['visual']['groups'])==2


def test_all_metrics_survive_followup_and_share_a_scope(service):
    first=service.local_plan(AskRequest(question='Compare Mateo Cross and Rory Ellis goals and assists'))
    request=AskRequest(question='And last season?',previous_plan=first)
    plan=service.local_plan(request);answer=service.answer(plan,request)
    assert {f['metric'] for f in answer['facts']}=={'goals','assists'}
    assert {f['scope']['season'] for f in answer['facts']}=={'2025-26'}
    assert {f['subject_id'] for f in answer['facts']}=={'rh09','eb09'}


def test_revision_during_model_selection_discards_old_claims():
    store=DataStore(ROOT/'fixtures/personalization');service=AssistantService(CareerService(store))
    try:
        request=AskRequest(question='How many goals and assists does Mateo Cross have?')
        def mutate():
            mid='career-showcase-southbank-redhaven';events=store.original(mid).events
            goal=next(e for e in events if e.event_id=='e01178')
            store.ingest(mid,[goal.model_copy(update={'revision':2,'delivery_sequence':max(e.delivery_sequence for e in events)+1,
                'available_period':2,'available_ms':2700100,'retracted':True})])
        agent,_=fake_agent(service.local_plan(request),mutation=mutate)
        app=FastAPI();install_assistant(app,lambda:service.career,researcher=agent)
        with TestClient(app) as client:answer=client.post('/api/fan/assistant/ask',json=request.model_dump(by_alias=True)).json()
        assert next(f for f in answer['facts'] if f['metric']=='goals')['value']==74
        assert answer['narrative']['fallback_reason']=='records_changed'
        assert answer['narrative']['mode']=='calculated'
        assert not any('75 goals' in b['text'] for b in answer['narrative']['blocks'])
    finally:store.close()


def test_provider_schema_constrains_metrics_and_requires_all_tool_fields(service):
    request=AskRequest(question='Show Enzo Clarke recent assists')
    agent,calls=fake_agent(service.local_plan(request))
    asyncio.run(agent.research(service,request,lambda:True))
    function=calls[0]['tools'][0]['function'];schema=function['parameters']
    assert function['strict'] is True
    assert set(schema['required'])==set(schema['properties'])
    assert 'per90' not in schema['properties']['additional_metrics']['items']['enum']
    assert 'assists' in schema['properties']['metric']['enum']


def test_successful_answer_does_not_hide_incorrect_agent_execution(service):
    # These are the concrete routing failures captured in the first live sample.
    for plan,question in [
        (blank('compare',player_ids=['eb09','sb09'],per90=True,additional_metrics=['per90']),
         'Compare Rory Ellis and Dario Voss in goals per 90'),
        (blank('seasons',player_ids=['rh09'],season='2025-26'), 'And last season?')]:
        request=AskRequest(question=question,previous_plan=blank('stats',player_ids=['rh09']))
        agent,calls=fake_agent(plan)
        with pytest.raises(ProviderFailure):asyncio.run(agent.research(service,request,lambda:True))
        assert len(calls)<=2


def test_rate_query_schema_does_not_invite_unrequested_denominators(service):
    from counterpress.assistant.planner import query_schema
    request=AskRequest(question='Compare Rory Ellis and Dario Voss in goals per 90')
    schema=query_schema(service.context(request))
    assert schema['properties']['metric']['enum']==['goals']
    assert schema['properties']['additional_metrics']['maxItems']==0
    # If a provider still violates the constraint, fail before a paid story turn.
    bad=service.local_plan(request).model_copy(update={'additional_metrics':['minutes']})
    agent,calls=fake_agent(bad)
    with pytest.raises(ProviderFailure,match='query_scope_rejected'):
        asyncio.run(agent.research(service,request,lambda:True))
    assert len(calls)==1


@pytest.mark.parametrize('depth,limit',[('casual',1),('analyst',2)])
def test_story_schema_enforces_audience_sentence_limit(service,depth,limit):
    request=AskRequest(question='Show Enzo Clarke recent assists',preferences={'depth':depth})
    agent,calls=fake_agent(service.local_plan(request))
    asyncio.run(agent.research(service,request,lambda:True))
    schema=calls[1]['response_format']['json_schema']['schema']
    assert schema['properties']['supporting']['maxItems']==limit


def test_general_comparison_cannot_invent_extra_metrics_but_followups_keep_them(service):
    from counterpress.assistant.planner import query_schema
    request=AskRequest(question='Compare Mateo Cross this season and last season')
    assert query_schema(service.context(request))['properties']['additional_metrics']['maxItems']==0
    bad=service.local_plan(request).model_copy(update={'additional_metrics':['assists','shots_on_target']})
    with pytest.raises(ValueError,match='explicit request'):service.validate(bad,request)
    previous=blank('compare',player_ids=['rh09','eb09'],additional_metrics=['assists'])
    follow=AskRequest(question='And last season?',previous_plan=previous)
    schema=query_schema(service.context(follow))
    assert set(schema['properties']['metric']['enum'])=={'goals','assists'}
    assert schema['properties']['additional_metrics']['maxItems']==1
    assert service.answer(service.local_plan(follow),follow)['visual']['kind']=='groups'


def test_malformed_tool_plan_stops_before_second_request(service):
    request=AskRequest(question='What happened in this match?',match_id='career-showcase-southbank-redhaven',
                       cutoff={'period':2,'elapsed_ms':2700000})
    bad=blank('match',match_id=request.match_id,additional_metrics=['assists'])
    agent,calls=fake_agent(bad)
    with pytest.raises(ProviderFailure,match='query_schema_rejected'):
        asyncio.run(agent.research(service,request,lambda:True))
    assert len(calls)==1


def test_compound_comparison_claims_bind_correct_global_fact_indices(service):
    from counterpress.assistant.narrative import build_claims
    request=AskRequest(question='Compare Rory Ellis and Dario Voss goals and assists last season')
    plan=service.local_plan(request);answer=service.answer(plan,request)
    claims=build_claims(answer,plan,request)
    comparisons=[c for c in claims if c['kind']=='comparison']
    assert len(comparisons)==2
    assert 'by 1 assist.' in comparisons[1]['text']
    assert {answer['facts'][i]['metric'] for i in comparisons[0]['fact_indices']}=={'goals'}
    assert {answer['facts'][i]['metric'] for i in comparisons[1]['fact_indices']}=={'assists'}
    assert all('2025-26' in c['text'] for c in comparisons)


@pytest.mark.parametrize('question', ['And last season?', 'What about this season?', 'How about 2025-26?', 'This season?', '那上赛季？'])
@pytest.mark.parametrize('operation', ['stats', 'compare', 'recent', 'club_leaders'])
def test_period_only_followup_preserves_operation_in_schema_and_read_boundary(service, question, operation):
    from counterpress.assistant.planner import query_schema
    previous=blank(operation, player_ids=['rh09','eb09'] if operation=='compare' else [] if operation=='club_leaders' else ['rh09'],
                   club_id='redhaven' if operation=='club_leaders' else None, metric='assists')
    request=AskRequest(question=question,previous_plan=previous)
    schema=query_schema(service.context(request))
    assert schema['properties']['operation']['enum']==[operation,'clarify','unsupported']
    assert schema['properties']['metric']['enum']==['assists']
    assert service.local_plan(request).operation==operation
    wrong=previous.model_copy(update={'operation':'seasons','season':'2025-26','comparison_season':'2026-27'})
    with pytest.raises(ValueError,match='period-only'):service.validate(wrong,request)


def test_period_followup_rejection_stops_before_second_model_request(service):
    previous=blank('stats',player_ids=['rh09'])
    request=AskRequest(question='And last season?',previous_plan=previous)
    wrong=previous.model_copy(update={'operation':'seasons','season':'2025-26','comparison_season':'2026-27'})
    agent,calls=fake_agent(wrong)
    with pytest.raises(ProviderFailure):asyncio.run(agent.research(service,request,lambda:True))
    assert len(calls)==1


def test_explicit_comparison_is_not_constrained_to_previous_operation(service):
    from counterpress.assistant.planner import query_schema
    request=AskRequest(question='Compare Mateo Cross this season and last season',previous_plan=blank('stats',player_ids=['rh09']))
    assert 'seasons' in query_schema(service.context(request))['properties']['operation']['enum']
    service.validate(service.local_plan(request),request)
