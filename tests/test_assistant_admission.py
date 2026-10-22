import asyncio
from concurrent.futures import ThreadPoolExecutor
import json

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from counterpress.adaptation.azure import ProviderFailure
from counterpress.assistant.admission import Admission, CosmosAdmissionStore, SharedResearcher, SQLiteAdmissionStore
from counterpress.assistant.api import install_assistant
from counterpress.assistant.contracts import AskRequest
from counterpress.assistant.service import AssistantService
from counterpress.history import HistoryStorageError
from counterpress.personalization.service import CareerService
from counterpress.personalization.store import DataStore
from test_assistant_research import ROOT, fake_agent
from test_cosmos_history import AtomicContainer


@pytest.fixture(params=['sqlite','cosmos'])
def admissions(request,tmp_path):
    container=AtomicContainer()
    return lambda:Admission(CosmosAdmissionStore(container) if request.param=='cosmos'
                            else SQLiteAdmissionStore(tmp_path/'admission.sqlite3'))


def test_hourly_allowance_survives_restart_and_does_not_refund(admissions):
    for i in range(10):
        admission=admissions();status,job=admission.reserve(str(i),1000+i)
        assert status=='reserved'
        admission.finish(str(i),job.owner,1000+i)
    assert admissions().reserve('eleven',1011)[0]=='hourly_limit'
    assert admissions().reserve('eleven',4599)[0]=='hourly_limit'
    assert admissions().reserve('eleven',4600)[0]=='reserved'


def test_duplicate_concurrency_expiry_and_late_owner(admissions):
    first=admissions();_,a=first.reserve('a',100)
    assert admissions().reserve('a',101)[0]=='pending'
    assert admissions().reserve('b',101)[0]=='reserved'
    assert admissions().reserve('c',101)[0]=='busy'
    _,replacement=admissions().reserve('a',120)
    assert replacement.owner!=a.owner
    first.finish('a',a.owner,121)
    assert admissions().reserve('a',121)[0]=='pending'
    admissions().finish('a',replacement.owner,122)
    assert admissions().reserve('a',123)[0]=='done'
    assert admissions().reserve('a',182)[0]=='reserved'


def test_concurrent_sqlite_instances_admit_once(tmp_path):
    def reserve(_):return Admission(SQLiteAdmissionStore(tmp_path/'same.sqlite3')).reserve('same',100)[0]
    with ThreadPoolExecutor(max_workers=8) as pool:statuses=list(pool.map(reserve,range(8)))
    assert statuses.count('reserved')==1 and statuses.count('pending')==7


def test_cosmos_conflict_rebuilds_from_winning_reservation():
    container=AtomicContainer()
    a=Admission(CosmosAdmissionStore(container));b=Admission(CosmosAdmissionStore(container))
    container.before_batch=lambda:b.reserve('same',100)
    assert a.reserve('same',100)[0]=='pending'
    container.failure=503
    with pytest.raises(HistoryStorageError):a.reserve('new',100)


@pytest.fixture
def service():
    store=DataStore(ROOT/'fixtures/personalization')
    yield AssistantService(CareerService(store))
    store.close()


def test_completed_read_reused_after_restart_without_storing_user_text(service,admissions):
    request=AskRequest(question='How many goals and assists does Mateo Cross have?')
    inner,calls=fake_agent(service.local_plan(request))
    async def run():
        a=SharedResearcher(inner,admissions(),'v1',lambda:100)
        first=await a.research(service,request,lambda:True)
        b=SharedResearcher(inner,admissions(),'v1',lambda:101)
        cached=await b.research(service,request,lambda:False)
        assert cached.cached and cached.requests==0 and cached.usage=={}
        assert cached.evidence_id==first.evidence_id and cached.selection==first.selection
        assert len(calls)==2
        state=admissions().store.transact(lambda state:state).model_dump_json()
        assert request.question not in state and 'Mateo Cross' not in state
        assert len(json.loads(state)['reservations'])==1
    asyncio.run(run())


def test_failed_attempt_suppresses_immediate_paid_retry(service,admissions):
    request=AskRequest(question='How many goals does Mateo Cross have?')
    inner,calls=fake_agent(service.local_plan(request),wrong_story=True)
    async def run():
        for reason in ('story_validation_rejected','recent_attempt_failed'):
            agent=SharedResearcher(inner,admissions(),'v1',lambda:100)
            with pytest.raises(ProviderFailure,match=reason):await agent.research(service,request,lambda:True)
        assert len(calls)==2
    asyncio.run(run())


def test_shared_admission_outage_falls_back_without_model_call(service):
    class Unavailable:
        def transact(self,build):raise HistoryStorageError('private detail')
    request=AskRequest(question='How many goals does Mateo Cross have?')
    inner,calls=fake_agent(service.local_plan(request))
    agent=SharedResearcher(inner,Admission(Unavailable()),'v1')
    app=FastAPI();install_assistant(app,lambda:service.career,researcher=agent)
    with TestClient(app) as client:answer=client.post('/api/fan/assistant/ask',json=request.model_dump(by_alias=True)).json()
    assert answer['mode']=='lookup_fallback' and answer['fallback_reason']=='admission_unavailable'
    assert answer['facts'][0]['value']==75 and not calls


def test_revision_change_cannot_reuse_old_receipt(service,admissions):
    request=AskRequest(question='How many goals does Mateo Cross have?')
    calls=[]
    class Fresh:
        async def research(self,*args):
            agent,record=fake_agent(service.local_plan(request))
            result=await agent.research(*args)
            calls.extend(record)
            return result
    async def run():
        agent=SharedResearcher(Fresh(),admissions(),'v1',lambda:100)
        before=await agent.research(service,request,lambda:True)
        mid='career-showcase-southbank-redhaven';events=service.store.original(mid).events
        goal=next(e for e in events if e.event_id=='e01178')
        service.store.ingest(mid,[goal.model_copy(update={'revision':2,'delivery_sequence':max(e.delivery_sequence for e in events)+1,
            'available_period':2,'available_ms':2700100,'retracted':True})])
        after=await agent.research(service,request,lambda:True)
        assert not after.cached and before.evidence_id!=after.evidence_id
        assert len(calls)==4
    asyncio.run(run())


def test_ephemeral_store_cannot_activate_agent():
    with pytest.raises(ValueError,match='durable'):SQLiteAdmissionStore(':memory:')


def test_runtime_agent_requires_shared_storage_and_loads_without_paid_call(monkeypatch,tmp_path):
    from counterpress.api.main import create_app
    monkeypatch.setenv('COUNTERPRESS_ASSISTANT_MODEL','azure')
    monkeypatch.setenv('COUNTERPRESS_ASSISTANT_WORKFLOW','agent')
    monkeypatch.setenv('AZURE_OPENAI_ENDPOINT','https://example.openai.azure.com')
    monkeypatch.setenv('AZURE_OPENAI_DEPLOYMENT','test')
    monkeypatch.setenv('AZURE_OPENAI_API_KEY','test-only')
    with pytest.raises(ValueError,match='durable'):create_app()
    app=create_app(db_path=tmp_path/'runtime.sqlite3')
    with TestClient(app) as client:
        config=client.get('/api/fan/assistant/config').json()
    assert config['workflow']=='agent' and config['model_requests_per_hour']==20
    assert config['natural_language'] is True


def test_api_cache_reuses_claims_but_never_charges_provider_again(service,admissions):
    request=AskRequest(question='How many goals does Mateo Cross have?')
    inner,calls=fake_agent(service.local_plan(request))
    answers=[]
    for _ in range(2):
        app=FastAPI()
        install_assistant(app,lambda:service.career,researcher=SharedResearcher(inner,admissions(),'v1',lambda:100))
        with TestClient(app) as client:
            response=client.post('/api/fan/assistant/ask',json=request.model_dump(by_alias=True))
        assert response.status_code==200
        answers.append(response.json())
    assert len(calls)==2
    assert all(a['mode']=='azure_agent' for a in answers)
    assert answers[0]['facts']==answers[1]['facts'] and answers[0]['narrative']==answers[1]['narrative']


def test_preferences_and_release_version_have_separate_receipts(service,admissions):
    request=AskRequest(question='How many goals does Mateo Cross have?')
    calls=[]
    class Fresh:
        async def research(self,s,r,reserve):
            agent,record=fake_agent(s.local_plan(r))
            result=await agent.research(s,r,reserve);calls.extend(record)
            return result
    async def run():
        for version,body in [('v1',request),('v2',request),('v2',request.model_copy(update={
            'preferences':request.preferences.model_copy(update={'depth':'analyst'})}))]:
            result=await SharedResearcher(Fresh(),admissions(),version,lambda:100).research(service,body,lambda:True)
            assert not result.cached
        assert len(calls)==6
    asyncio.run(run())
