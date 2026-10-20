from pathlib import Path
import pytest
from pydantic import ValidationError
from fastapi import FastAPI
from fastapi.testclient import TestClient
from counterpress.assistant.api import install_assistant
from counterpress.assistant.contracts import AskRequest
from counterpress.assistant.service import AssistantService
from counterpress.assistant.narrative import build_claims
from counterpress.personalization.store import DataStore
from counterpress.personalization.service import CareerService
from counterpress.gi.synthetic import read_synthetic

ROOT=Path(__file__).resolve().parents[1]
MID='career-showcase-southbank-redhaven'

@pytest.fixture(scope='module')
def service():
    store=DataStore(ROOT/'fixtures/personalization')
    yield AssistantService(CareerService(store))
    store.close()

def ask(service,event,**changes):
    values={'question':'What happened in this moment?','match_id':event.match_id,
            'event_id':event.event_id,'event_revision':event.revision,
            'cutoff':{'period':event.available_period,'elapsed_ms':event.available_ms},**changes}
    request=AskRequest(**values);plan=service.local_plan(request)
    return service.answer(plan,request),request,plan

def test_unresolved_goal_does_not_reveal_outcome_or_milestone(service):
    goal=next(e for e in service.store.original(MID).events if e.event_id=='e01178')
    before,_,_=ask(service,goal,cutoff={'period':2,'elapsed_ms':goal.available_ms-1})
    assert before['status']=='clarify' and not before['facts']
    assert 'unfolding' in before['text'][0] and '75' not in str(before)
    after,_,_=ask(service,goal)
    assert after['facts'][-1]['value']==75

def test_selected_earlier_goal_never_turns_into_latest_goal(service):
    goals=[e for e in service.store.original(MID).events if e.goal_for]
    first,_,_=ask(service,goals[0],cutoff={'period':2,'elapsed_ms':2700000})
    assert all(f['scope']['cutoff']=={'period':goals[0].available_period,'elapsed_ms':goals[0].available_ms} for f in first['facts'])
    assert not any(f['value']==75 and f['metric']=='career_goals' for f in first['facts'])
    assert all(r['event_id']!=goals[-1].event_id for f in first['facts'] for r in f['evidence']['events'])

def test_pass_explains_its_actor_recipient_and_geometry_without_career_claims(service):
    event=next(e for e in service.store.original(MID).events if e.kind=='pass' and e.outcome=='completed' and e.start and e.end)
    answer,request,plan=ask(service,event)
    assert answer['title']=='About this moment'
    assert service.store.players[event.player_id].name in answer['text'][0]
    assert service.store.players[event.recipient_id].name in answer['text'][0]
    assert [f['metric'] for f in answer['facts']]==['selected_action','pass_distance_m']
    assert all(f['evidence']['event_id']==event.event_id for f in answer['facts'])
    assert len(build_claims(answer,plan,request))==2 and not answer['actions']

def test_stale_revision_and_wrong_match_do_not_silently_substitute_event(service):
    event=service.store.original(MID).events[0]
    answer,_,_=ask(service,event,event_revision=99)
    assert answer['status']=='clarify' and not answer['facts']
    answer,_,_=ask(service,event,event_id='missing-source-event')
    assert answer['status']=='clarify' and not answer['facts']
    with pytest.raises(ValidationError):AskRequest(question='What happened?',event_id=event.event_id)

def test_retracted_event_does_not_survive_as_selected_moment():
    store=DataStore(ROOT/'fixtures/personalization');service=AssistantService(CareerService(store))
    try:
        record=store.original(MID);goal=next(e for e in record.events if e.event_id=='e01178')
        store.ingest(MID,[goal.model_copy(update={'revision':2,'delivery_sequence':max(e.delivery_sequence for e in record.events)+1,
            'available_period':2,'available_ms':2700100,'retracted':True})])
        answer,_,_=ask(service,goal,cutoff={'period':2,'elapsed_ms':2700100})
        assert answer['status']=='clarify' and not answer['facts']
    finally:store.close()

def test_match_centre_preserves_native_availability_not_animation_time(service):
    mid='synthetic-32fe41c5d304ce68d7d9'
    gi=read_synthetic(ROOT/'fixtures/gi',mid)
    originals={e.event_id:e for e in service.store.original(mid).events}
    for event in gi.events:
        source=originals[event.event_id]
        assert (event.available_period,event.available_ms,event.revision)==(source.available_period,source.available_ms,source.revision)

def test_legacy_highlight_resolver_uses_canonical_availability_without_outcome(service):
    app=FastAPI();install_assistant(app,lambda:service.career)
    mid='synthetic-32fe41c5d304ce68d7d9'
    with TestClient(app) as client:
        params={'match_id':mid,'event_id':'a00500','revision':1,'resolved':True}
        response=client.get('/api/fan/assistant/moment',params=params)
        assert response.status_code==200
        assert response.json()['cutoff']=={'period':1,'elapsed_ms':2094886}
        assert 'goal' not in response.text and 'score' not in response.text
        params['resolved']=False
        assert client.get('/api/fan/assistant/moment',params=params).json()['cutoff']=={'period':1,'elapsed_ms':2094785}
        params['event_id']='does-not-exist'
        assert client.get('/api/fan/assistant/moment',params=params).status_code==404
