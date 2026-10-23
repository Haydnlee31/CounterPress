"""Offline real-framework multiagent tests; all facts use the real career store."""
import asyncio
import json

import httpx2
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from counterpress.adaptation.azure import ProviderFailure
from counterpress.assistant.api import install_assistant
from counterpress.assistant.contracts import AskRequest
from counterpress.assistant.multiagent import MultiAgentResearch,Route,Task,read_bundle,specialist_request,validate_route
from counterpress.assistant.service import AssistantService,blank
from counterpress.personalization.service import CareerService
from counterpress.personalization.store import DataStore
from test_assistant_research import CONFIG,ROOT

@pytest.fixture(scope='module')
def service():
    store=DataStore(ROOT/'fixtures/personalization')
    yield AssistantService(CareerService(store))
    store.close()


def fake_multi(service,request,*,fail_role=None,wrong_selection=False,mutation=None,incomplete_selection=False,clarify_role=None):
    calls=[]
    def respond(req):
        payload=json.loads(req.content);calls.append(payload)
        name=payload['response_format']['json_schema']['name']
        data=json.loads(payload['messages'][-1]['content'])
        if name=='footie_route':
            separator='; then ' if '; then ' in request.question else ' and '
            split=request.question.index(separator)
            result={'tasks':[{'role':'match','question':request.question[:split],'scope':'selected'},
                {'role':'career','question':request.question[split+len(separator):],'scope':'pre_match'}]}
        elif name=='footie_query':
            role='match' if 'match specialist' in payload['messages'][0]['content'] else 'career'
            if role==fail_role:return httpx2.Response(503)
            # Provider sees the normalized question and pinned context, not the
            # original task offsets (which remain in the orchestration receipt).
            body=request.model_copy(update={'question':data['question'],'as_of':data['context']['as_of'],
                'match_id':data['context']['selected']['match_id']})
            if role=='career' and request.playback:
                body=body.model_copy(update={'playback':None,'event_id':None,'event_revision':None})
            result=service.local_plan(body).model_dump()
            if role==clarify_role:result=blank('clarify').model_dump()
        else:
            if mutation:mutation()
            result={'bundle_id':'invented' if wrong_selection else data['bundles'][0]['bundle_id']}
            if incomplete_selection:result={'lead':data['sentences'][0]['id'],'supporting':[]}
        return httpx2.Response(200,json={'id':'test','object':'chat.completion','created':1,'model':'test',
            'choices':[{'index':0,'finish_reason':'stop','message':{'role':'assistant','content':json.dumps(result)}}],
            'usage':{'prompt_tokens':10,'completion_tokens':5,'total_tokens':15}})
    return MultiAgentResearch(CONFIG,lambda:httpx2.MockTransport(respond)),calls


def compound_request():
    return AskRequest(question='Explain this moment and compare Mateo Cross goals this season',
        match_id='career-showcase-southbank-redhaven',cutoff={'period':2,'elapsed_ms':2700000})


def test_single_specialist_fast_path_preserves_existing_facts(service):
    request=AskRequest(question='Compare Rory Ellis and Dario Voss goals and assists last season')
    agent,calls=fake_multi(service,request)
    result=asyncio.run(agent.research(service,request,lambda:True))
    assert result.requests==2 and result.tools==1 and not result.partial_failures
    assert [t.role for t in result.tasks]==['career']
    assert result.plans[0].operation=='compare'
    assert result.usage['total_tokens']==30
    assert [p['response_format']['json_schema']['name'] for p in calls]==['footie_query','footie_story']


def test_compound_delegation_reads_both_parts_in_one_scope(service):
    request=compound_request();agent,calls=fake_multi(service,request)
    result=asyncio.run(agent.research(service,request,lambda:True))
    assert result.requests==4 and result.tools==2 and not result.partial_failures
    assert {t.role for t in result.tasks}=={'match','career'}
    assert {p.operation for p in result.plans}=={'match','seasons'}
    with service.store.snapshot():answer,claims=read_bundle(service,request,result.tasks,result.plans)
    career=[f for f in answer['facts'] if f.get('subject_id')=='rh09' and f['scope']['window']!='match_at_cutoff']
    assert career and all(f['scope']['as_of']<=service.store.row(request.match_id)['kickoff'] for f in career)
    assert len({c['id'] for c in claims})==len(claims)
    assert all(0<=i<len(answer['facts']) for c in claims for i in c['fact_indices'])
    assert 'before this match' in answer['text'][-1]


def test_partial_specialist_failure_keeps_available_evidence(service):
    request=compound_request();agent,_=fake_multi(service,request,fail_role='career')
    app=FastAPI();install_assistant(app,lambda:service.career,researcher=agent)
    with TestClient(app) as client:response=client.post('/api/fan/assistant/ask',json=request.model_dump(by_alias=True))
    assert response.status_code==200
    body=response.json()
    assert body['mode']=='azure_agent' and body['research']['partial']
    assert body['research']['unavailable']==['career']
    assert any('could not be checked' in t for t in body['text'])
    assert body['narrative']['blocks']==[]


def test_bad_synthesis_uses_calculated_story_without_throwing_away_data(service):
    request=AskRequest(question='How many goals does Mateo Cross have?')
    agent,_=fake_multi(service,request,wrong_selection=True)
    app=FastAPI();install_assistant(app,lambda:service.career,researcher=agent)
    with TestClient(app) as client:answer=client.post('/api/fan/assistant/ask',json=request.model_dump(by_alias=True)).json()
    assert answer['narrative']['mode']=='calculated'
    assert answer['facts'][0]['value']==75
    assert answer['research']['unavailable']==['orchestrator']


def test_scope_cannot_silently_include_current_match(service):
    request=compound_request().model_copy(update={'question':'Explain this moment and goals this season including this goal'})
    task=Task(role='career',start=24,end=len(request.question),scope='pre_match')
    with pytest.raises(ValueError,match='including'):specialist_request(service,request,task)
    with pytest.raises(ValueError,match='explicitly'):specialist_request(service,request,task.model_copy(update={'scope':'selected'}))


@pytest.mark.parametrize('tasks',[
    [Task(role='career',start=10,end=15)],
    [Task(role='match',start=0,end=10),Task(role='career',start=9,end=20)],
    [Task(role='career',start=0,end=500)],
])
def test_route_rejects_omitted_overlapping_and_out_of_range_text(tasks):
    with pytest.raises(ValueError):validate_route(Route(tasks=tasks),'Explain this moment and goals this season')


def test_budget_denial_never_sends_provider_request(service):
    request=AskRequest(question='How many goals does Mateo Cross have?')
    agent,calls=fake_multi(service,request)
    with pytest.raises(ProviderFailure):asyncio.run(agent.research(service,request,lambda:False))
    assert not calls


def test_multiagent_cached_bundle_is_typed_and_reused_without_calls(service,tmp_path):
    from counterpress.assistant.admission import Admission,SQLiteAdmissionStore,SharedResearcher
    request=compound_request();inner,calls=fake_multi(service,request)
    store=SQLiteAdmissionStore(tmp_path/'multi.sqlite3')
    async def run():
        first=await SharedResearcher(inner,Admission(store,lease_seconds=28),'multi',lambda:100).research(service,request,lambda:True)
        cached=await SharedResearcher(inner,Admission(store,lease_seconds=28),'multi',lambda:101).research(service,request,lambda:False)
        assert cached.cached and cached.requests==0
        assert cached.tasks==first.tasks and cached.plans==first.plans and cached.selection==first.selection
        assert len(calls)==4
        state=store.transact(lambda s:s)
        assert state.weighted==((100,4),)
        saved=state.model_dump_json()
        assert request.question not in saved and 'Explain this moment' not in saved
    asyncio.run(run())


def test_changed_revision_during_synthesis_discards_old_multiplan_claims():
    store=DataStore(ROOT/'fixtures/personalization');service=AssistantService(CareerService(store))
    try:
        request=compound_request()
        def mutate():
            mid=request.match_id;events=store.original(mid).events
            goal=next(e for e in events if e.event_id=='e01178')
            store.ingest(mid,[goal.model_copy(update={'revision':2,'delivery_sequence':max(e.delivery_sequence for e in events)+1,
                'available_period':2,'available_ms':2699999,'retracted':True})])
        agent,_=fake_multi(service,request,mutation=mutate)
        app=FastAPI();install_assistant(app,lambda:service.career,researcher=agent)
        with TestClient(app) as client:response=client.post('/api/fan/assistant/ask',json=request.model_dump(by_alias=True))
        assert response.status_code==200
        answer=response.json()
        assert answer['narrative']['fallback_reason']=='records_changed'
        assert answer['narrative']['mode']=='calculated'
        with store.snapshot():
            tasks=(Task(role='match',start=0,end=19),Task(role='career',start=24,end=len(request.question),scope='pre_match'))
            plans=tuple(service.local_plan(specialist_request(service,request,t)) for t in tasks)
            fresh,_=read_bundle(service,request,tasks,plans)
        assert answer['facts']==fresh['facts']
    finally:store.close()


def test_exact_substring_delegation_handles_unicode_and_rejects_rewrites():
    from counterpress.assistant.multiagent import Delegation,exact_tasks
    question='解释这一刻，并且比较本赛季助攻。'
    route=Delegation(tasks=[{'role':'match','question':'解释这一刻','scope':'selected'},
                           {'role':'career','question':'比较本赛季助攻','scope':'pre_match'}])
    tasks=exact_tasks(route,question)
    assert [question[t.start:t.end] for t in tasks]==['解释这一刻','比较本赛季助攻']
    bad=Delegation(tasks=[{'role':'career','question':'invented question','scope':'selected'}])
    with pytest.raises(ValueError,match='uniquely'):exact_tasks(bad,question)


def test_compound_response_clears_single_plan_followup_instead_of_dropping_half(service):
    from counterpress.assistant.contracts import Plan
    request=compound_request();agent,_=fake_multi(service,request)
    app=FastAPI();install_assistant(app,lambda:service.career,researcher=agent)
    with TestClient(app) as client:answer=client.post('/api/fan/assistant/ask',json=request.model_dump(by_alias=True)).json()
    previous=Plan.model_validate(answer['plan'])
    assert previous.operation=='clarify' and not previous.player_ids
    followup=AskRequest(question='And last season?',previous_plan=previous)
    assert service.local_plan(followup).operation=='clarify'
    with pytest.raises(ValueError,match='Unresolved subject'):
        service.validate(blank('stats',player_ids=['rh09'],season='2025-26'),followup)


def test_compound_story_must_cover_each_specialist_and_show_scope(service):
    request=compound_request();agent,calls=fake_multi(service,request,incomplete_selection=True)
    result=asyncio.run(agent.research(service,request,lambda:True))
    assert result.partial_failures==('orchestrator:selection_failed',)
    with service.store.snapshot():answer,claims=read_bundle(service,request,result.tasks,result.plans)
    picked=[c for c in claims if c['id'] in [result.selection.lead,*result.selection.supporting]]
    assert {c['source_role'] for c in picked}=={'match','career'}
    assert all(c['text'].startswith('Before this match kicked off:') for c in picked if c['source_role']=='career')
    labels=[g['label'] for g in answer['visual']['groups']]
    assert len(labels)==len(set(labels))
    schema=calls[-1]['response_format']['json_schema']['schema']
    assert set(schema['properties'])=={'bundle_id'}
    assert len(schema['properties']['bundle_id']['enum'])<=24


def test_clarifying_specialist_is_reported_as_visible_partial_answer(service):
    request=compound_request();agent,_=fake_multi(service,request,clarify_role='career')
    app=FastAPI();install_assistant(app,lambda:service.career,researcher=agent)
    with TestClient(app) as client:answer=client.post('/api/fan/assistant/ask',json=request.model_dump(by_alias=True)).json()
    assert answer['research']=={'partial':True,'unavailable':['career']}
    assert answer['narrative']['blocks']==[]
    assert answer['narrative']['fallback_reason']=='partial_research'
    assert answer['plan']['operation']=='clarify'


def test_goalkeeper_fraction_maps_to_percentage_without_changing_counts(service):
    from counterpress.assistant.service import requested_metrics
    question='What fraction of shots faced has Leon Finch saved?'
    request=AskRequest(question=question)
    assert requested_metrics(question)=={'save_pct'}
    plan=service.local_plan(request)
    assert plan.metric=='save_pct' and not plan.additional_metrics
    service.validate(plan,request)
    assert requested_metrics('Show Leon Finch shots and saves')=={'shots','saves'}
    assert service.local_plan(AskRequest(question='Predict what fraction of shots faced Leon Finch will save')).operation=='unsupported'


@pytest.mark.parametrize('question,changes',[
    ('How many total goals does Mateo Cross have?',{'per90':True}),
    ('How many total goals does Mateo Cross have?',{'operation':'recent'}),
    ('How many goals does Redhaven have?',{'operation':'club_leaders'}),
    ('Who leads Redhaven in goals?',{'operation':'stats'}),
])
def test_explicit_operation_count_and_ranking_cannot_be_reinterpreted(service,question,changes):
    request=AskRequest(question=question)
    plan=service.local_plan(request)
    service.validate(plan,request)
    with pytest.raises(ValueError):service.validate(plan.model_copy(update=changes),request)


@pytest.mark.parametrize('question',[
    'Is Mateo Cross better than Rory Ellis?',
    'Is Mateo Cross naturally superior to Rory Ellis?',
])
def test_vague_player_superiority_cannot_default_to_goal_comparison(service,question):
    request=AskRequest(question=question)
    with pytest.raises(ValueError,match='operation'):
        service.validate(blank('compare',player_ids=['rh09','eb09']),request)


@pytest.mark.parametrize('metric',['passes','shots'])
def test_match_count_queries_cannot_return_goals_instead(service,metric):
    request=AskRequest(question=f'How many {metric} in this match?',match_id='career-showcase-southbank-redhaven',cutoff={'period':2,'elapsed_ms':2700000})
    with pytest.raises(ValueError):service.answer(service.local_plan(request),request)
    with pytest.raises(ValueError):service.answer(blank('match',match_id=request.match_id,metric=metric),request)
    app=FastAPI();install_assistant(app,lambda:service.career)
    with TestClient(app) as client:answer=client.post('/api/fan/assistant/ask',json=request.model_dump(by_alias=True)).json()
    assert answer['status']=='clarify' and not answer['facts']


def test_compound_visual_omits_action_indicator_and_keeps_missing_values(service):
    mid='career-showcase-southbank-redhaven'
    event=next(e for e in service.store.original(mid).events if e.kind=='pass')
    question='Explain this moment and show Rory Ellis saves this season'
    request=AskRequest(question=question,match_id=mid,event_id=event.event_id,event_revision=event.revision,
        cutoff={'period':event.available_period,'elapsed_ms':event.available_ms})
    tasks=(Task(role='match',start=0,end=19),Task(role='career',start=24,end=len(question),scope='pre_match'))
    plans=tuple(service.local_plan(specialist_request(service,request,t)) for t in tasks)
    with service.store.snapshot():answer,_=read_bundle(service,request,tasks,plans)
    action=next(f for f in answer['facts'] if f['metric']=='selected_action')
    groups=answer['visual']['groups']
    assert not any(g['label']=='This match · '+action['label'] for g in groups)
    saves=next(g for g in groups if g['label']=='Before kickoff · Saves')
    assert saves['items'][0]['value'] is None


def test_cached_incomplete_story_is_revalidated_without_losing_evidence(service):
    from dataclasses import replace
    from counterpress.assistant.narrative import StoryPlan
    request=compound_request();agent,_=fake_multi(service,request)
    result=asyncio.run(agent.research(service,request,lambda:True))
    cached=replace(result,cached=True,requests=0,selection=StoryPlan(lead=result.selection.lead,supporting=[]))
    class Cached:
        max_requests=4
        deadline_seconds=24
        async def research(self,*args):return cached
    app=FastAPI();install_assistant(app,lambda:service.career,researcher=Cached())
    with TestClient(app) as client:response=client.post('/api/fan/assistant/ask',json=request.model_dump(by_alias=True))
    assert response.status_code==200
    answer=response.json()
    assert answer['narrative']['mode']=='calculated'
    assert answer['narrative']['fallback_reason']=='stale_selection'
    assert {c['source_role'] for c in answer['narrative']['blocks']}=={'match','career'}
    assert answer['facts']


def test_every_advertised_story_bundle_is_valid_and_bounded(service):
    from counterpress.assistant.multiagent import story_candidates,validate_bundle_story
    for depth in ('casual','analyst'):
        request=compound_request()
        request=request.model_copy(update={'preferences':request.preferences.model_copy(update={'depth':depth})})
        tasks=(Task(role='match',start=0,end=19),Task(role='career',start=24,end=len(request.question),scope='pre_match'))
        plans=tuple(service.local_plan(specialist_request(service,request,t)) for t in tasks)
        with service.store.snapshot():_,claims=read_bundle(service,request,tasks,plans)
        candidates=story_candidates(claims,depth)
        assert 1<=len(candidates)<=24
        for selection in candidates.values():
            selected=validate_bundle_story(selection,claims,depth)
            assert {c['source_role'] for c in selected}=={'match','career'}
            assert len(selected)<= (2 if depth=='casual' else 3)
            assert len({c['id'] for c in selected})==len(selected)
        assert candidates==story_candidates(claims,depth)


def test_club_total_provider_schema_cannot_expand_to_squad(service):
    from counterpress.assistant.planner import query_schema
    request=AskRequest(question='How many goals does Redhaven have?',as_of='2026-10-20T00:00:00Z')
    schema=query_schema(service.context(request))
    assert schema['properties']['operation']['enum']==['stats','clarify','unsupported']
    assert schema['properties']['player_ids']['maxItems']==0
    assert schema['properties']['club_id']['enum']==[None,'redhaven']
    assert schema['properties']['additional_metrics']['maxItems']==0
    assert schema['properties']['per90']['enum']==[False]
    for bad in ([f'rh{i:02}' for i in range(1,12)],['rh09']):
        with pytest.raises(ValueError):
            plan=blank('stats',club_id='redhaven',player_ids=bad)
            # At most four members is in the model contract; subject binding is
            # checked again even if a provider ignores the restricted schema.
            service.validate(type(plan).model_validate(plan.model_dump()),request)


def test_malformed_query_diagnostics_are_bounded_and_do_not_stringify_errors(service):
    events=[]
    class Broken(MultiAgentResearch):
        async def complete(self,budget,role,prompt,data,schema,name):
            budget.request(role)
            return {**blank('stats',club_id='redhaven').model_dump(),'player_ids':['rh01']*11}
    agent=Broken(CONFIG,observer=lambda event,value:events.append((event,value)))
    with pytest.raises(ProviderFailure,match='all_specialists_failed'):
        asyncio.run(agent.research(service,AskRequest(question='How many goals does Redhaven have?'),lambda:True))
    proposal=next(value for event,value in events if event=='query_proposal')
    assert len(proposal['plan']['player_ids'])==11
    failure=next(value for event,value in events if event=='planning_failure')
    assert failure=={'role':'career','type':'schema','codes':['too_long']}
    assert 'example.openai' not in json.dumps(failure)


@pytest.mark.parametrize('question,operation',[
    ('Which Redhaven player has the highest total for key passes?','club_leaders'),
    ('Who in the Redhaven squad has the greatest number of key passes?','club_leaders'),
    ('Which Redhaven footballer has the largest key pass total?','club_leaders'),
    ('How many total key passes does Redhaven have?','stats'),
    ('Show Redhaven key passes','stats'),
    ('Which Redhaven player has the fewest key passes?','clarify'),
])
def test_ranking_binds_player_superlative_without_rewriting_club_totals(service,question,operation):
    from counterpress.assistant.planner import query_schema
    request=AskRequest(question=question)
    plan=service.local_plan(request)
    assert plan.operation==operation
    assert query_schema(service.context(request))['properties']['operation']['enum'][0]==operation
    if operation!='clarify':
        service.validate(plan,request)
        wrong=plan.model_copy(update={'operation':'stats' if operation=='club_leaders' else 'club_leaders'})
        with pytest.raises(ValueError,match='operation'):service.validate(wrong,request)


@pytest.mark.parametrize('question',[
    'What percentage of the shots on target Leon Finch has faced did he save?',
    'What proportion of shots Leon Finch faced has he stopped?',
    'What fraction of shots faced has Leon Finch saved?',
])
def test_shots_faced_percentage_is_one_keeper_ratio(service,question):
    from counterpress.assistant.service import requested_metrics
    request=AskRequest(question=question)
    assert requested_metrics(question)=={'save_pct'}
    plan=service.local_plan(request)
    assert plan.metric=='save_pct' and not plan.additional_metrics
    service.validate(plan,request)
    with pytest.raises(ValueError,match='Metric'):
        service.validate(plan.model_copy(update={'metric':'shots_on_target','additional_metrics':['saves']}),request)


def test_keeper_counts_remain_counts_and_unknown_ratios_clarify(service):
    from counterpress.assistant.service import requested_metrics
    request=AskRequest(question='Show Leon Finch shots on target and saves')
    assert requested_metrics(request.question)=={'shots_on_target','saves'}
    plan=service.local_plan(request)
    assert {plan.metric,*plan.additional_metrics}=={'shots_on_target','saves'}
    service.validate(plan,request)
    for question in ('What percentage of Leon Finch shots were excellent saves?',
        'What percentage of shots on target and saves does Leon Finch have?'):
        body=AskRequest(question=question)
        assert service.local_plan(body).operation=='clarify'
        with pytest.raises(ValueError,match='operation'):
            service.validate(blank('stats',player_ids=['rh01'],metric='saves'),body)


@pytest.mark.parametrize('qualifier',['before this match','prior to the selected match','ahead of this match','before kickoff'])
def test_explicit_pre_match_comparison_binds_cutoff_and_removes_match_scope(service,qualifier):
    question=f'Compare Mateo Cross and Dario Voss on goals per 90 {qualifier}'
    request=compound_request().model_copy(update={'question':question})
    task=Task(role='career',start=0,end=len(question),scope='pre_match')
    body=specialist_request(service,request,task)
    assert body.question=='Compare Mateo Cross and Dario Voss on goals per 90'
    assert body.match_id is None and body.playback is None
    assert body.as_of==service.store.row(request.match_id)['kickoff']
    plan=service.local_plan(body)
    assert plan.operation=='compare' and plan.per90 and set(plan.player_ids)=={'rh09','sb09'}
    service.validate(plan,body)
    with service.store.snapshot():answer,claims=read_bundle(service,request,(task,),(plan,))
    assert claims and all(c['text'].startswith('Before this match kicked off: ') for c in claims)
    assert all(f['scope']['as_of']<=body.as_of for f in answer['facts'])


def test_explicit_pre_match_only_question_uses_career_fast_path(service):
    request=compound_request().model_copy(update={'question':'Compare Mateo Cross and Dario Voss on goals per 90 before this match'})
    agent,calls=fake_multi(service,request)
    result=asyncio.run(agent.research(service,request,lambda:True))
    assert result.requests==2 and not result.partial_failures
    assert result.tasks[0].role=='career' and result.tasks[0].scope=='pre_match'
    assert result.plans[0].operation=='compare' and result.plans[0].match_id is None


def test_in_match_rate_cannot_become_pre_match_comparison(service):
    request=compound_request().model_copy(update={'question':'Compare Mateo Cross and Dario Voss goals per 90 in this match'})
    assert service.operation_constraint(request)=='clarify'
    with pytest.raises(ValueError):service.validate(service.local_plan(request),request)
    task=Task(role='career',start=0,end=len(request.question),scope='selected')
    with pytest.raises(ValueError,match='explicitly'):specialist_request(service,request,task)
    with pytest.raises(ValueError,match='Current-match'):
        specialist_request(service,request,task.model_copy(update={'scope':'pre_match'}))


def test_explicit_pre_match_compound_comparison_preserves_both_specialists(service):
    request=compound_request().model_copy(update={'question':
        'How did the latest goal change this match?; then compare Mateo Cross and Dario Voss on goals per 90 before this match.'})
    agent,calls=fake_multi(service,request)
    result=asyncio.run(agent.research(service,request,lambda:True))
    assert result.requests==4 and not result.partial_failures
    assert {p.operation for p in result.plans}=={'match','compare'}
    career=next(p for t,p in zip(result.tasks,result.plans) if t.role=='career')
    assert career.match_id is None and career.per90
    assert set(career.player_ids)=={'rh09','sb09'}
