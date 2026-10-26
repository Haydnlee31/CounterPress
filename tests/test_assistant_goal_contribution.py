"""Relational goal questions resolve the contributor separately from the scorer."""
import asyncio
import json
from pathlib import Path

import httpx2
import pytest

from counterpress.assistant.contracts import AskRequest
from counterpress.assistant.multiagent import MultiAgentResearch
from counterpress.assistant.narrative import build_claims, render_story
from counterpress.assistant.planner import query_schema
from counterpress.assistant.service import AssistantService, blank
from counterpress.personalization.service import CareerService
from counterpress.personalization.store import DataStore
from test_assistant_research import CONFIG


@pytest.fixture(scope='module')
def service():
    store=DataStore(Path(__file__).resolve().parents[1]/'fixtures/personalization')
    yield AssistantService(CareerService(store))
    store.close()


def request(question,**changes):
    return AskRequest.model_validate(dict(question=question,player_id='rh04',
        match_id='career-showcase-southbank-redhaven',event_id='e01019',event_revision=1,
        cutoff={'period':2,'elapsed_ms':1050489},through_sequence=1448,
        as_of='2026-10-20T00:00:00Z',preferences={'depth':'analyst','favorite_player_ids':['rh13']})|changes)


@pytest.mark.parametrize('question',[
    'How did Luca Bennett contribute to Mateo Cross\'s equalizer?',
    'How did Luca Bennett contribute to Mateo Cross’s equaliser?',
    'What role did Luca Bennett play in Mateo Cross’s winner?',
    'What was Luca Bennett’s role in Mateo Cross’s goal?',
    'Explain Luca Bennett’s contribution to Mateo Cross’s finish.',
    'Describe the involvement of Luca Bennett in Mateo Cross’s goal.',
    'How did Luca Bennett help create Mateo Cross’s equalizer?',
])
def test_named_contributor_is_answered_with_authored_sequence_facts(service,question):
    body=request(question);plan=service.local_plan(body)
    assert plan.operation=='match' and plan.analysis=='buildup' and plan.player_ids==[]
    service.validate(plan,body)
    schema=query_schema(service.context(body))['properties']
    assert schema['analysis']['enum']==[None,'buildup']
    assert schema['player_ids']['maxItems']==0
    answer=service.answer(plan,body)
    assert answer['status']=='answered'
    facts={(f['subject_id'],f['metric']):f['value'] for f in answer['facts']}
    assert facts['rh04','buildup_completed_passes']==1
    assert facts['rh04','buildup_receptions']==1
    assert facts['redhaven','completed_passes']==4
    assert facts['redhaven','participant_count']==4
    assert facts['redhaven','observed_duration_seconds']==15.71
    assert answer['text'][0]=='Luca Bennett contributed 1 completed pass, 1 received pass in the buildup.'
    assert 'winner' not in ' '.join(answer['text']).lower()  # User wording is not evidence of score impact.
    claims=build_claims(answer,plan,body)
    assert claims[0]['required'] is True
    with pytest.raises(ValueError,match='required'):
        render_story({'lead':claims[1]['id'],'supporting':[]},claims,'analyst')


@pytest.mark.parametrize('question',[
    'How did Lionel Messi contribute to Mateo Cross’s equalizer?',
    'How did Luca Bennett contribute to Lionel Messi’s equaliser?',
    'How did Luca Bennett contribute to Unknown Mateo Cross’s goal?',
    'How did Luca Bennett contribute to Lionel Cross’s goal?',
    'How did Unknown Luca Bennett contribute to Mateo Cross’s goal?',
    'How did Mateo Cross contribute to Luca Bennett’s equalizer?',
    'How did Leon Finch contribute to Mateo Cross’s winner?',
])
def test_unknown_absent_or_wrong_scorer_never_gets_replaced(service,question):
    body=request(question);plan=service.local_plan(body)
    answer=service.answer(plan,body)
    assert answer['status']=='clarify' and not answer['facts']
    forced=blank('match',analysis='buildup',match_id=body.match_id)
    try:
        service.validate(forced,body)
    except ValueError:
        return
    assert service.answer(forced,body)['status']=='clarify'


@pytest.mark.parametrize('question',[
    'How many career assists did Luca Bennett contribute to Mateo Cross’s goals?',
    'How did Luca Bennett contribute to Mateo Cross’s goal this season?',
    'Compare Luca Bennett and Mateo Cross’s career assists.',
])
def test_history_totals_are_not_silently_replaced_with_selected_buildup(service,question):
    body=request(question)
    assert service.local_plan(body).analysis is None
    assert query_schema(service.context(body))['properties']['analysis']['enum']==[None]


@pytest.mark.parametrize('question',[
    'How did Luca Bennett contribute to Redhaven’s equalizer?',
    'Explain the buildup to Redhaven’s goal.',
    'Explain the buildup to this player’s goal.',
])
def test_known_club_and_generic_possessives_keep_existing_scope(service,question):
    body=request(question);plan=service.local_plan(body)
    assert service.answer(plan,body)['status']=='answered'


@pytest.mark.parametrize('question',[
    'How did Luca Bennett contribute to Mateo Cross’s goal with his tracking speed?',
    'What role did Luca Bennett play in Mateo Cross’s goal according to the coach’s intentions?',
])
def test_unobservable_requested_causality_remains_unsupported(service,question):
    body=request(question);plan=service.local_plan(body)
    assert plan.operation=='unsupported'
    assert not service.answer(plan,body)['facts']


def test_mocked_model_receives_locked_schema_and_cannot_omit_contributor(service):
    body=request('How did Luca Bennett contribute to Mateo Cross’s equalizer?')
    calls=[]
    def respond(req):
        payload=json.loads(req.content);kind=payload['response_format']['json_schema']['name'];calls.append(kind)
        prompt=json.loads(payload['messages'][-1]['content'])
        if kind=='footie_query':
            schema=payload['response_format']['json_schema']['schema']['properties']
            assert schema['player_ids']['maxItems']==0
            assert schema['analysis']['enum']==[None,'buildup']
            result=service.local_plan(body).model_dump()
        elif kind=='footie_followup':result={'player_id':None}
        else:result={'bundle_id':prompt['bundles'][0]['bundle_id']}
        return httpx2.Response(200,json={'id':'local-only','object':'chat.completion','created':1,'model':'test',
            'choices':[{'index':0,'finish_reason':'stop','message':{'role':'assistant','content':json.dumps(result)}}],
            'usage':{'prompt_tokens':1,'completion_tokens':1,'total_tokens':2}})
    result=asyncio.run(MultiAgentResearch(CONFIG,lambda:httpx2.MockTransport(respond)).research(service,body,lambda:True))
    assert result.plan.analysis=='buildup' and result.plan.player_ids==[]
    assert calls[0]=='footie_query' and len(calls)<=4
    assert result.tools>=1
    wrong=result.plan.model_copy(update={'player_ids':['rh04']})
    with pytest.raises(ValueError,match='Unexpected player subset'):service.validate(wrong,body)


def test_contributor_and_unknown_regain_origin_both_remain_required(service):
    body=request('How did Luca Bennett contribute to Mateo Cross’s goal after the team won the ball?')
    plan=service.local_plan(body);answer=service.answer(plan,body)
    assert answer['status']=='answered'
    claims=build_claims(answer,plan,body)
    required=[c for c in claims if c.get('required')]
    assert len(required)==2
    assert any('does not establish' in c['text'] for c in required)
    assert any('Luca Bennett contributed' in c['text'] for c in required)
    for omitted in required:
        other=next(c for c in claims if c['id']!=omitted['id'])
        with pytest.raises(ValueError,match='required'):
            render_story({'lead':other['id'],'supporting':[]},claims,'analyst')


def test_chinese_answer_keeps_named_contribution_without_model_sentence_selection(service):
    body=request('How did Luca Bennett contribute to Mateo Cross’s equalizer?',
                 preferences={'language':'zh-Hans','favorite_player_ids':['rh13']})
    plan=service.local_plan(body);answer=service.answer(plan,body)
    assert answer['status']=='answered'
    assert answer['text'][0]=='Luca Bennett在进攻过程中贡献了1次成功传球、1次接球。'
    assert build_claims(answer,plan,body)==[]  # Chinese uses the complete calculated answer.
