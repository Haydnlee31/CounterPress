"""Cards cannot silently ask about a newer delivery snapshot, even at equal clocks."""
from pathlib import Path
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from counterpress.adaptation.azure import ProviderFailure
from counterpress.assistant.api import install_assistant
from counterpress.personalization.service import CareerService
from counterpress.personalization.store import DataStore

MID='career-showcase-southbank-redhaven'


@pytest.fixture
def setup():
    store=DataStore(Path(__file__).resolve().parents[1]/'fixtures/personalization')
    events=store.original(MID).events
    sequence=max(e.delivery_sequence for e in events)
    passing=next(e for e in events if e.event_id=='e01016')
    correction=passing.model_copy(update={'revision':2,'delivery_sequence':sequence+1,
        'available_ms':1050489,'outcome':'incomplete'})
    body={'question':'What made that goal happen?', 'match_id':MID,
          'cutoff':{'period':2,'elapsed_ms':1050489},'event_id':'e01019',
          'event_revision':1,'through_sequence':sequence}
    yield store,correction,body
    store.close()


def client_for(store,researcher=None):
    app=FastAPI();install_assistant(app,lambda:CareerService(store),researcher=researcher)
    return TestClient(app)


def test_same_time_pass_correction_rejects_old_card_before_model_call(setup):
    store,correction,body=setup
    class NeverCalled:
        calls=0
        async def research(self,*args):
            self.calls+=1
            raise AssertionError('Stale snapshot must not consume inference')
    researcher=NeverCalled()
    store.ingest(MID,[correction])
    with client_for(store,researcher) as client:
        response=client.post('/api/fan/assistant/ask',json=body)
    assert response.status_code==409
    assert 'Review its update' in response.json()['detail']
    assert researcher.calls==0


def test_correction_during_investigation_cannot_return_new_facts_for_old_card(setup):
    store,correction,body=setup
    class CorrectingResearch:
        calls=0
        async def research(self,*args):
            self.calls+=1
            store.ingest(MID,[correction])
            raise ProviderFailure('limited','selection_failed')
    researcher=CorrectingResearch()
    with client_for(store,researcher) as client:
        response=client.post('/api/fan/assistant/ask',json=body)
    assert response.status_code==409 and researcher.calls==1


def test_explicit_updated_sequence_can_be_answered(setup):
    store,correction,body=setup
    store.ingest(MID,[correction])
    with client_for(store) as client:
        response=client.post('/api/fan/assistant/ask',json={**body,'through_sequence':correction.delivery_sequence})
    assert response.status_code==200
    assert response.json()['status']=='answered'


def test_later_unavailable_correction_does_not_block_historical_question(setup):
    store,correction,body=setup
    store.ingest(MID,[correction.model_copy(update={'available_ms':1050490})])
    with client_for(store) as client:
        assert client.post('/api/fan/assistant/ask',json=body).status_code==200
        assert client.post('/api/fan/assistant/ask',json={'question':'Goals?', 'through_sequence':1}).status_code==422
