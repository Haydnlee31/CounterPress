import asyncio
from pathlib import Path
from fastapi import FastAPI
from fastapi.testclient import TestClient
import pytest
from counterpress.assistant.api import install_assistant
from counterpress.personalization.store import DataStore
from counterpress.personalization.service import CareerService

@pytest.fixture(scope='module')
def career():
    store=DataStore(Path(__file__).resolve().parents[1]/'fixtures/personalization')
    yield CareerService(store)
    store.close()

@pytest.fixture
def client(monkeypatch,career):
    monkeypatch.setenv('COUNTERPRESS_ASSISTANT_MODEL','azure')
    monkeypatch.setattr('counterpress.assistant.api.load_config',lambda:object())
    app=FastAPI();install_assistant(app,lambda:career,planner=object())
    return TestClient(app)

def body(career):
    mid='wyscout-2058017';event=career.store.events(mid)[0]
    return {'question':'Summarize this play','match_id':mid,'event_id':event.event_id,'event_revision':event.revision,'cutoff':{'period':event.available_period,'elapsed_ms':event.available_ms}}

def test_summary_route_pins_event_and_passes_server_evidence(client,career,monkeypatch):
    received=[]
    async def write(config,evidence,reserve):
        assert reserve();received.append(evidence)
        return {'text':['A recorded pass.'],'mode':'azure_generated_verified','review':{'supported':True,'issues':[]}}
    monkeypatch.setattr('counterpress.assistant.highlight_summary.write_verified_summary',write)
    response=client.post('/api/fan/assistant/summary',json=body(career))
    assert response.status_code==200,response.text
    assert received[0]['context']['selected_event_id']==body(career)['event_id']
    assert response.json()['source_fingerprint']

def test_summary_route_rejects_wrong_revision_and_cross_site_before_inference(client,career,monkeypatch):
    async def never(*args):raise AssertionError('Should not call model')
    monkeypatch.setattr('counterpress.assistant.highlight_summary.write_verified_summary',never)
    request=body(career)
    assert client.post('/api/fan/assistant/summary',json={**request,'event_revision':999}).status_code==409
    assert client.post('/api/fan/assistant/summary',json=request,headers={'Origin':'https://other.example'}).status_code==403
    assert client.post('/api/fan/assistant/summary',json={**request,'cutoff':{'period':2,'elapsed_ms':2700000}}).status_code==409
