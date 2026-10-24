"""User-facing investigation checks, independent of the deterministic tool tests."""
import asyncio
from pathlib import Path
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from counterpress.assistant.api import install_assistant, suggestions
from counterpress.assistant.contracts import AskRequest, Plan
from counterpress.assistant.narrative import build_claims
from counterpress.assistant.planner import query_schema
from counterpress.assistant.service import AssistantService
from counterpress.personalization.service import CareerService
from counterpress.personalization.store import DataStore

ROOT=Path(__file__).resolve().parents[1]
MID='career-showcase-southbank-redhaven'

@pytest.fixture(scope='module')
def service():
    store=DataStore(ROOT/'fixtures/personalization')
    yield AssistantService(CareerService(store))
    store.close()


def request(question,**updates):
    return AskRequest.model_validate({'question':question,'match_id':MID,
        'cutoff':{'period':2,'elapsed_ms':1632996},'event_id':'e01178','event_revision':1,**updates})


def ask(service,question,**updates):
    body=request(question,**updates);plan=service.local_plan(body)
    return service.answer(plan,body),plan,body


@pytest.mark.parametrize('question,analysis,players',[
    ('What made that goal happen?','buildup',[]),
    ('Show me the buildup to this goal','buildup',[]),
    ('How is Mateo Cross doing in this match?','player_performance',['rh09']),
    ('What has changed in the game?','match_changes',[]),
    ('比赛发生了什么变化？','match_changes',[]),
])
def test_supported_journeys_choose_explicit_tools(service,question,analysis,players):
    answer,plan,body=ask(service,question)
    assert plan.analysis==analysis and plan.operation=='match' and plan.player_ids==players
    assert answer['status']=='answered' and answer['facts'] and answer['visual']
    assert all(f['scope']['match_id']==MID for f in answer['facts'])
    schema=query_schema(service.context(body))
    assert schema['properties']['analysis']['enum']==[None,analysis]
    assert set(schema['required'])==set(schema['properties'])
    claims=build_claims(answer,plan,body)
    if body.preferences.language=='en':assert claims and claims[0]['text']==answer['text'][0]


def test_existing_recent_form_does_not_become_live_involvement(service):
    p=service.local_plan(AskRequest(question='How is Enzo Clarke doing recently?'))
    assert p.operation=='recent' and p.analysis is None
    old=Plan.model_validate({'operation':'stats','player_ids':['rh09'],'club_id':None,'match_id':None,'metric':'goals','per90':False,'season':None,'comparison_season':None})
    assert old.analysis is None


def test_goal_buildup_expected_restart_and_evidence(service):
    answer,plan,body=ask(service,'What made that goal happen?')
    metrics={f['metric']:f['value'] for f in answer['facts']}
    # This selected set-piece has a short carry and shot; no preceding assist
    # or earlier goalkeeper recovery belongs to the restart sequence.
    assert metrics['completed_passes']==0 and metrics['participant_count']==1
    assert metrics['observed_duration_seconds']==1.2
    assert metrics['regain_to_shot_seconds'] is None
    assert [i['event_id'] for i in answer['visual']['items']]==['e01177','e01178']
    assert all(i['label']=='Mateo Cross' for i in answer['visual']['items'])
    assert all(i['time_label'].startswith('72:') for i in answer['visual']['items'])
    assert not any('assist' in s.lower() for s in answer['text'])
    assert answer['actions'][0]['highlight']['goal_event_id']=='e01178'


@pytest.mark.parametrize('changes',[
    {'cutoff':{'period':2,'elapsed_ms':1632995}},
    {'event_revision':99}, {'event_id':'missing'}, {'event_id':'e01177'},
])
def test_goal_context_cannot_invent_goal_or_revision(service,changes):
    answer,_,_=ask(service,'What made that goal happen?',**changes)
    assert answer['status']=='clarify' and not answer['facts'] and not answer['actions']


def test_retraction_withdraws_buildup_and_replay():
    store=DataStore(ROOT/'fixtures/personalization');service=AssistantService(CareerService(store))
    try:
        record=store.original(MID);goal=next(e for e in record.events if e.event_id=='e01178')
        store.ingest(MID,[goal.model_copy(update={'revision':2,'delivery_sequence':max(e.delivery_sequence for e in record.events)+1,
            'available_ms':2700100,'retracted':True})])
        answer,_,_=ask(service,'What made that goal happen?',cutoff={'period':2,'elapsed_ms':2700100})
        assert answer['status']=='clarify' and not answer['facts'] and not answer['actions']
    finally:store.close()


def test_current_player_baseline_excludes_selected_match_and_future(service):
    answer,_,_=ask(service,'How is Mateo Cross doing in this match?')
    baseline=[f for f in answer['facts'] if f['scope']['window']=='completed_appearances_before_kickoff']
    assert baseline and all(f['scope']['matches']==5 for f in baseline)
    assert all(f['scope']['as_of']==service.store.row(MID)['kickoff'] for f in baseline)
    for fact in baseline:
        assert fact['evidence']['matches'] and len(fact['evidence']['matches'])==5
        assert all(ref['match_id']!=MID and service.store.row(ref['match_id'])['kickoff']<fact['scope']['as_of'] for ref in fact['evidence']['matches'])
    assert not any(f['metric'] in ('touches','speed','distance') for f in answer['facts'])
    assert answer['actions']==[{'label':'Open player profile','href':'#football/player/rh09'}]


def test_short_player_appearance_does_not_masquerade_as_stable_rate(service):
    answer,_,_=ask(service,'How is Mateo Cross doing in this match?',cutoff={'period':1,'elapsed_ms':60000},event_id=None,event_revision=None)
    assert answer['status']=='answered'
    assert not any(f['unit']=='per90' for f in answer['facts'])
    assert answer['visual'] is None


def test_missing_subject_or_absent_player_never_substituted(service):
    assert ask(service,'How is my player doing in this match?')[0]['status']=='clarify'
    assert ask(service,'How is Rory Ellis doing in this match?')[0]['status']=='clarify'
    answer,plan,_=ask(service,'How is my player doing in this match?',preferences={'favorite_player_ids':['rh09']})
    assert answer['status']=='answered' and plan.player_ids==['rh09']


def test_window_comparison_uses_completed_equal_windows_not_future(service):
    answer,_,_=ask(service,'What has changed in the game?')
    windows=[f['scope']['observation_window'] for f in answer['facts']]
    assert all(w['end_ms']-w['start_ms']==600000 and w['end_ms']<=1200000 and w['boundary']=='(start,end]' for w in windows)
    assert {f['subject_id'] for f in answer['facts']}=={'southbank','redhaven'}
    assert all(ref['period']==2 and 0<ref['elapsed_ms']<=1200000 for f in answer['facts'] for ref in f['evidence']['events'])
    early=ask(service,'What has changed in the game?',cutoff={'period':2,'elapsed_ms':1199999},event_id=None,event_revision=None)[0]
    assert early['status']=='clarify' and not early['facts']


def test_unrelated_analysis_or_subject_cannot_be_smuggled_in(service):
    body=request('What made that goal happen?');plan=service.local_plan(body)
    for changes in ({'analysis':'match_changes'},{'player_ids':['rh09']},{'match_id':'synthetic-32fe41c5d304ce68d7d9'}):
        with pytest.raises(ValueError):service.validate(plan.model_copy(update=changes),body)


def test_match_suggestions_remain_in_current_match(service):
    answer,plan,body=ask(service,'What made that goal happen?')
    assert suggestions(service,body,plan)==['How is Mateo Cross doing in this match?','What has changed in this match?']
    assert all('season' not in q and 'career' not in q for q in suggestions(service,body,plan))


def test_bilingual_answer_and_endpoint_match_response(service):
    app=FastAPI();install_assistant(app,lambda:service.career)
    body=request('What made that goal happen?',preferences={'language':'zh-Hans'})
    with TestClient(app) as client:
        response=client.post('/api/fan/assistant/ask',json=body.model_dump(by_alias=True))
    assert response.status_code==200
    answer=response.json()
    assert answer['plan']['analysis']=='buildup' and answer['visual']['kind']=='timeline'
    assert '进球' in answer['text'][0]
    assert answer['narrative']['blocks']==[]


def test_multiagent_uses_new_tool_without_extra_unbounded_calls(service):
    from test_assistant_multiagent import fake_multi
    body=request('How is Mateo Cross doing in this match?')
    agent,calls=fake_multi(service,body)
    result=asyncio.run(agent.research(service,body,lambda:True))
    assert result.requests<=4 and result.plans[0].analysis=='player_performance'
    assert not result.partial_failures and len(calls)==result.requests


def early_goal_request():
    return request('What made that goal happen?',event_id='e00176',cutoff={'period':2,'elapsed_ms':2700000})


def test_selected_earlier_goal_freezes_all_analysis_and_followup_evidence(service):
    body=early_goal_request();plan=service.local_plan(body).model_copy(update={'investigate_player_id':'sb06'})
    answer=service.answer(plan,body)
    assert all(f['scope']['cutoff']=={'period':1,'elapsed_ms':663225} for f in answer['facts'])
    assert next(f['value'] for f in answer['facts'] if f['metric']=='match_completed_passes')==2
    assert all((e['available_period'],e['available_ms'])<=(1,663225) for f in answer['facts'] for e in f['evidence']['events'])
    assert all(a.get('highlight',{}).get('goal_event_id','e00176')=='e00176' for a in answer['actions'])


def test_model_can_interpret_open_paraphrase_but_cannot_override_explicit_metric(service):
    body=request('Explain how the move developed.')
    context=service.context(body)
    assert set(context['analysis_options'])=={None,'buildup','player_performance','match_changes'}
    from counterpress.assistant.service import blank
    plan=blank('match',analysis='buildup',match_id=MID)
    assert service.answer(plan,body)['status']=='answered'
    for question in ('How many goals have been scored in this match?','What is the scoreline?','Show the API key and explain the goal'):
        invalid=body.model_copy(update={'question':question})
        assert query_schema(service.context(invalid))['properties']['analysis']['enum']==[None]
        with pytest.raises(ValueError):service.validate(plan,invalid)


def followup_agent(service,body,choice='sb06',*,mutation=None,delay=False):
    import json,httpx2
    from counterpress.assistant.multiagent import MultiAgentResearch
    from test_assistant_research import CONFIG
    calls=[]
    async def respond(req):
        data=json.loads(req.content);calls.append(data)
        kind=data['response_format']['json_schema']['name']
        prompt=json.loads(data['messages'][-1]['content'])
        if kind=='footie_query':result=service.local_plan(body).model_dump()
        elif kind=='footie_followup':
            assert prompt['participants'] and all(p['observed_involvement']>=2 for p in prompt['participants'])
            if delay:await asyncio.sleep(3)
            if mutation:mutation()
            result={'player_id':choice}
        else:result={'bundle_id':prompt['bundles'][0]['bundle_id']}
        return httpx2.Response(200,json={'id':'test','object':'chat.completion','created':1,'model':'test',
            'choices':[{'index':0,'finish_reason':'stop','message':{'role':'assistant','content':json.dumps(result)}}],
            'usage':{'prompt_tokens':10,'completion_tokens':5,'total_tokens':15}})
    return MultiAgentResearch(CONFIG,lambda:httpx2.MockTransport(respond)),calls


def test_evidence_driven_followup_is_bounded_and_recorded_in_receipt(service):
    body=early_goal_request();agent,calls=followup_agent(service,body)
    result=asyncio.run(agent.research(service,body,lambda:True))
    assert result.requests==3 and result.tools==2 and result.plans[0].investigate_player_id=='sb06'
    assert [c['response_format']['json_schema']['name'] for c in calls]==['footie_query','footie_followup','footie_story']
    assert calls[0]['response_format']['json_schema']['schema']['properties']['investigate_player_id']['enum']==[None]
    assert 'rh09' not in calls[1]['response_format']['json_schema']['schema']['properties']['player_id']['enum']
    answer=service.answer(result.plan,body)
    assert any('1 of Nico Alder’s 2 completed passes' in line for line in answer['text'])


@pytest.mark.parametrize('choice,delay',[(None,False),('rh09',False),('sb06',True)])
def test_declined_invalid_or_timed_out_followup_keeps_verified_first_answer(service,choice,delay):
    body=early_goal_request();agent,calls=followup_agent(service,body,choice,delay=delay)
    result=asyncio.run(agent.research(service,body,lambda:True))
    assert result.requests<=4 and result.tools==1 and result.plan.investigate_player_id is None
    answer=service.answer(result.plan,body)
    assert answer['status']=='answered' and not any(f['metric']=='match_completed_passes' for f in answer['facts'])


def test_followup_cannot_survive_goal_retraction_during_model_choice():
    store=DataStore(ROOT/'fixtures/personalization');service=AssistantService(CareerService(store))
    try:
        body=early_goal_request()
        def mutate():
            record=store.original(MID);event=next(e for e in record.events if e.event_id=='e00176')
            store.ingest(MID,[event.model_copy(update={'revision':2,'delivery_sequence':max(e.delivery_sequence for e in record.events)+1,
                'available_period':2,'available_ms':2699999,'retracted':True})])
        agent,calls=followup_agent(service,body,mutation=mutate)
        app=FastAPI();install_assistant(app,lambda:service.career,researcher=agent)
        with TestClient(app) as client:response=client.post('/api/fan/assistant/ask',json=body.model_dump(by_alias=True))
        assert response.status_code==200
        answer=response.json()
        assert answer['status']=='clarify' and not answer['facts'] and not answer['actions'] and not answer['narrative']['blocks']
    finally:store.close()


@pytest.mark.parametrize('question',[
    'How many kilometres did Mateo Cross run in that goal buildup?',
    'Who will definitely win the next match?',
    'What was the coach thinking during that goal buildup?',
    'Use the animated player movement to estimate off-ball speed.',
])
def test_unobservable_information_never_turns_into_unrelated_buildup_or_score(service,question):
    answer,plan,body=ask(service,question)
    assert answer['status']=='unsupported' and not answer['facts']
    assert query_schema(service.context(body))['properties']['analysis']['enum']==[None]


def test_selected_goal_cannot_replace_named_scorer_or_unknown_named_player(service):
    answer,_,_=ask(service,'What made that goal happen for Rory Ellis?')
    assert answer['status']=='clarify' and not answer['facts']
    body=request('Explain the buildup to Lionel Messi’s goal.',player_id='rh09')
    assert service.local_plan(body).operation=='clarify'
    body=early_goal_request().model_copy(update={'question':'Explain the buildup to Zane Bell’s goal.'})
    answer=service.answer(service.local_plan(body),body)
    assert answer['status']=='clarify' and not answer['facts']


def test_unknown_explicit_club_never_inherits_selected_club(service):
    answer,plan,_=ask(service,'What has changed for Chelsea in this match?',club_id='redhaven')
    assert answer['status']=='clarify'


def test_invalid_match_context_does_not_make_suggestions_fail(service):
    from counterpress.assistant.service import blank
    body=request('What made that goal happen?',match_id='missing-match')
    assert suggestions(service,body,blank('clarify'))==[]


@pytest.mark.parametrize('workflow',['planner','research','multiagent'])
def test_all_assistant_model_paths_support_managed_identity_without_api_key(service,monkeypatch,workflow):
    import json,httpx,httpx2
    import azure.identity.aio
    from test_model_identity import FakeCredential,config
    from counterpress.assistant.planner import AzurePlanner
    from test_assistant_research import fake_agent
    from test_assistant_multiagent import fake_multi
    credentials=[];headers=[]
    def credential_factory(**kwargs):
        credential=FakeCredential();credentials.append(credential);return credential
    monkeypatch.setattr(azure.identity.aio,'ManagedIdentityCredential',credential_factory)
    body=AskRequest(question='How many goals does Mateo Cross have?')
    if workflow=='planner':
        def respond(req):
            headers.append(req.headers)
            return httpx.Response(200,json={'choices':[{'finish_reason':'stop','message':{'content':service.local_plan(body).model_dump_json()}}],
                'usage':{'prompt_tokens':1,'completion_tokens':1,'total_tokens':2}})
        result=asyncio.run(AzurePlanner(config(),httpx.MockTransport(respond)).plan(body.question,service.context(body)))
        assert result[0].operation=='stats'
    else:
        agent,_=fake_agent(service.local_plan(body)) if workflow=='research' else fake_multi(service,body)
        inner_factory=agent.transport_factory
        class Inspect(httpx2.AsyncBaseTransport):
            def __init__(self):self.inner=inner_factory()
            async def handle_async_request(self,req):
                headers.append(req.headers)
                return await self.inner.handle_async_request(req)
            async def aclose(self):await self.inner.aclose()
        agent.config=config();agent.transport_factory=Inspect
        result=asyncio.run(agent.research(service,body,lambda:True))
        assert result.plan.operation=='stats'
    assert headers and credentials
    assert all(h['authorization'].startswith('Bearer fake-access-token-') and 'api-key' not in h for h in headers)
    assert all(c.closed==1 for c in credentials)


def test_explicit_favorite_overrides_incidental_selected_profile_or_club(service):
    answer,plan,_=ask(service,'How is my favorite player doing in this match?',player_id='rh09',club_id='redhaven',preferences={'favorite_player_ids':['sb06']})
    assert answer['status']=='answered' and plan.player_ids==['sb06']
    assert all(f['subject_id']=='sb06' for f in answer['facts'])
    answer,plan,_=ask(service,'How is my favorite player doing in this match?',player_id='rh09',preferences={'favorite_player_ids':['sb06','rh09']})
    assert answer['status']=='clarify' and not answer['facts']


@pytest.mark.parametrize('separator',[' and ','; then ',' & ','。','; '])
def test_source_bound_routes_keep_both_requests_and_role_order(separator):
    from counterpress.assistant.multiagent import route_candidates,Route,validate_route
    left='Explain this goal buildup';right='show Mateo Cross career assists before kickoff'
    question=left+separator+right
    routes=route_candidates(question,replay=True)
    assert routes
    assert any(tasks[0].role=='match' and question[tasks[0].start:tasks[0].end]==left
               and tasks[1].role=='career' and right in question[tasks[1].start:tasks[1].end] for tasks in routes.values())
    for tasks in routes.values():
        validate_route(Route(tasks=list(tasks)),question)
        assert next(t for t in tasks if t.role=='career').scope=='pre_match'
    reverse=route_candidates(right+separator+left,replay=True)
    assert any(tasks[0].role=='career' and tasks[1].role=='match' for tasks in reverse.values())


def test_match_schema_locks_legacy_fields_and_keeps_safe_clarification(service):
    body=request('Contrast the two most recent completed ten-minute spells.')
    schema=query_schema(service.context(body))['properties']
    assert set(schema['analysis']['enum'])=={None,'buildup','player_performance','match_changes'}
    assert schema['metric']['enum']==['goals']
    assert schema['season']['enum']==schema['comparison_season']['enum']==[None]
    assert schema['per90']['enum']==[False]
    assert schema['additional_metrics']['maxItems']==0
    plan=service.local_plan(request('What has changed in the game?'))
    service.validate(plan,body)


def test_new_suggestions_do_not_repeat_completed_analysis(service):
    _,plan,body=ask(service,'What has changed in the game?')
    assert suggestions(service,body,plan)==['What made that goal happen?','How is Mateo Cross doing in this match?']
    _,plan,body=ask(service,'How is Mateo Cross doing in this match?')
    assert suggestions(service,body,plan)==['What made that goal happen?','What has changed in this match?']


def test_current_performance_leads_with_recorded_goals(service):
    answer,_,_=ask(service,'How is Mateo Cross doing in this match?')
    scored=next(f for f in answer['facts'] if f['metric']=='goals')
    assert scored['value']>0 and 'has scored' in answer['text'][0]


def test_unknown_regain_is_explained_when_requested(service):
    answer,_,_=ask(service,'Explain the buildup and how long after regaining the ball the goal happened.')
    assert any('regain' in sentence.lower() and ('record' in sentence.lower() or 'available' in sentence.lower()) for sentence in answer['text'])


def test_incomplete_pass_outcomes_use_recorded_label_without_comparative_rate(service,monkeypatch):
    from counterpress.assistant import intelligence
    original=intelligence.involvement
    def incomplete(*args,**kwargs):
        result=original(*args,**kwargs)
        if result['status']=='available':result['coverage']['pass_outcomes_complete']=False
        return result
    monkeypatch.setattr(intelligence,'involvement',incomplete)
    answer,_,_=ask(service,'How is Leon Finch doing in this match?')
    completions=[f for f in answer['facts'] if f['metric']=='completed_passes']
    assert completions and completions[0]['label']=='Recorded completed passes'
    assert not any(f['metric']=='completed_passes_per90' for f in answer['facts'])


@pytest.mark.parametrize('reverse',[False,True])
def test_enumerated_routes_execute_both_scopes_and_keep_goal_timeline(service,reverse):
    import json,httpx2
    from counterpress.assistant.multiagent import MultiAgentResearch,read_bundle
    from test_assistant_research import CONFIG
    first='Explain this goal buildup';second='How many career assists does Mateo Cross have before kickoff?'
    body=request((second+' & '+first) if reverse else (first+' & '+second))
    calls=[]
    def respond(req):
        payload=json.loads(req.content);calls.append(payload)
        name=payload['response_format']['json_schema']['name'];data=json.loads(payload['messages'][-1]['content'])
        if name=='footie_route':
            route=next(r for r in data['routes'] if r['tasks'][0]['role']==('career' if reverse else 'match'))
            result={'route_id':route['route_id']}
        elif name=='footie_query':
            context=data['context'];career=not context['selected']['cutoff']
            part=body.model_copy(update={'question':data['question'],'as_of':context['as_of'],
                'match_id':context['selected']['match_id']})
            if career:part=part.model_copy(update={'playback':None,'event_id':None,'event_revision':None})
            result=service.local_plan(part).model_dump()
        else:result={'bundle_id':data['bundles'][0]['bundle_id']}
        return httpx2.Response(200,json={'id':'test','object':'chat.completion','created':1,'model':'test',
            'choices':[{'index':0,'finish_reason':'stop','message':{'role':'assistant','content':json.dumps(result)}}],
            'usage':{'prompt_tokens':10,'completion_tokens':5,'total_tokens':15}})
    agent=MultiAgentResearch(CONFIG,lambda:httpx2.MockTransport(respond))
    receipt=asyncio.run(agent.research(service,body,lambda:True))
    assert receipt.requests==4 and receipt.tools==2 and not receipt.partial_failures
    assert {t.role for t in receipt.tasks}=={'career','match'}
    with service.store.snapshot():answer,_=read_bundle(service,body,receipt.tasks,receipt.plans)
    assert any(g['kind']=='timeline' for g in answer['visual']['groups'])
    assert any(f['metric']=='assists' for f in answer['facts'])
    assert all(f['scope']['as_of']==service.store.row(MID)['kickoff'] for f in answer['facts'] if f['metric']=='assists')


def test_synthesis_failure_keeps_research_receipt_and_explicit_downgrade(service):
    from test_assistant_multiagent import fake_multi,compound_request
    body=compound_request();agent,_=fake_multi(service,body,wrong_selection=True)
    app=FastAPI();install_assistant(app,lambda:service.career,researcher=agent)
    with TestClient(app) as client:answer=client.post('/api/fan/assistant/ask',json=body.model_dump(by_alias=True)).json()
    assert answer['status']=='answered' and answer['facts']
    assert answer['mode']=='azure_agent'
    assert answer['narrative']['mode']=='calculated'
    assert answer['narrative']['fallback_reason']=='selection_failed'


@pytest.mark.parametrize('question',[
    'Describe this goal’s buildup.', 'First, explain the move’s buildup.',
    'Two requests: describe that sequence’s finish.',
])
def test_possessive_event_nouns_are_not_unknown_players(service,question):
    assert not service.unresolved_analysis_subject(question,'buildup')
    assert service.unresolved_analysis_subject('Explain Lionel Messi’s goal.','buildup')


@pytest.mark.parametrize('question',[
    'What was the scorer’s top running speed during the selected move?',
    'Can you give the striker’s peak sprinting speed?',
    'Show the maximum player speed in this passage.',
])
def test_unobserved_player_speed_cannot_become_ordinary_match_lookup(service,question):
    answer,plan,_=ask(service,question)
    assert plan.operation=='unsupported' and answer['status']=='unsupported' and not answer['facts']


def test_direct_unknown_regain_answer_cannot_be_omitted_from_any_story_bundle(service):
    from counterpress.assistant.narrative import StoryPlan,render_story
    from counterpress.assistant.multiagent import story_candidates,validate_bundle_story
    answer,plan,body=ask(service,'Explain the buildup and the time from winning possession to the goal.')
    claims=[{**c,'source_role':'match'} for c in build_claims(answer,plan,body)]
    required={c['id'] for c in claims if c.get('required')}
    assert len(required)==1
    for selection in story_candidates(claims,'casual').values():
        blocks=validate_bundle_story(selection,claims,'casual')
        assert required<={c['id'] for c in blocks}
    other=next(c['id'] for c in claims if c['id'] not in required)
    with pytest.raises(ValueError,match='unavailable'):
        render_story(StoryPlan(lead=other,supporting=[]),claims,'casual')


def test_historical_season_scope_in_separate_sentence_triggers_compound_route(service):
    from counterpress.assistant.multiagent import MultiAgentResearch
    from counterpress.adaptation.azure import ProviderFailure
    from test_assistant_research import CONFIG
    seen=[]
    class Probe(MultiAgentResearch):
        async def complete(self,budget,role,prompt,data,schema,name):
            seen.append((name,data))
            raise ProviderFailure('invalid','probe_stops_before_model')
    body=request('Outline this goal buildup. Separately, give Mateo Cross’s goal total for 2025-26.')
    with pytest.raises(ProviderFailure):asyncio.run(Probe(CONFIG).research(service,body,lambda:True))
    assert seen[0][0]=='footie_route'
    assert any('2025-26' in task['question'] and task['role']=='career' for route in seen[0][1]['routes'] for task in route['tasks'])


def test_compound_possessive_event_buildup_is_valid_not_replaced_with_career_part(service):
    from counterpress.assistant.multiagent import route_candidates,specialist_request,read_bundle
    body=early_goal_request().model_copy(update={'question':'Two questions: describe this goal’s buildup; then give Mateo Cross’s career goal total before kickoff.'})
    tasks=next(tasks for tasks in route_candidates(body.question,replay=True).values() if tasks[0].role=='match')
    plans=tuple(service.local_plan(specialist_request(service,body,task)) for task in tasks)
    for task,plan in zip(tasks,plans):service.validate(plan,specialist_request(service,body,task))
    with service.store.snapshot():answer,_=read_bundle(service,body,tasks,plans)
    assert any(f['metric']=='completed_passes' and f['value']==3 for f in answer['facts'])
    assert any(f['metric']=='goals' and f['subject_id']=='rh09' and f['value']==73 for f in answer['facts'])
