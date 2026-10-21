"""Durable delivery -> independent reader -> corrected fan and assistant facts."""
import asyncio
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from counterpress.personalization.store import DataStore
from counterpress.personalization.service import CareerService
from counterpress.personalization.api import install_personalization
from counterpress.personalization.journal import SQLiteCareerJournal, CosmosCareerJournal
from counterpress.history import HistoryStorageError
from counterpress.streaming.contracts import CareerDelivery
from counterpress.streaming.consumer import DeliveryProcessor
from counterpress.streaming.azure import Publisher
from counterpress.fan.api import install_fan
from counterpress.assistant.api import install_assistant
from counterpress.api.main import create_app
from test_cosmos_history import AtomicContainer

ROOT=Path(__file__).resolve().parents[1]/'fixtures'
MID='career-showcase-southbank-redhaven'


def correction(store, revision=2):
    events=store.original(MID).events
    goal=next(e for e in events if e.event_id=='e01178')
    return goal.model_copy(update={'revision':revision,'delivery_sequence':max(e.delivery_sequence for e in events)+revision-1,
        'available_period':2,'available_ms':2700000+(revision-1)*100,'retracted':revision%2==0})


@pytest.fixture(params=['sqlite','cosmos'])
def pair(request,tmp_path):
    if request.param=='sqlite':
        factory=lambda:SQLiteCareerJournal(tmp_path/'journal.sqlite3')
    else:
        container=AtomicContainer()
        factory=lambda:CosmosCareerJournal(container)
    a=DataStore(ROOT/'personalization',journal=factory())
    b=DataStore(ROOT/'personalization',journal=factory())
    yield a,b,factory
    a.close();b.close()


def test_restart_duplicate_reordering_and_causal_views(pair):
    a,b,factory=pair
    assert a.ingest(MID,[correction(a)])['generation']==1
    assert a.ingest(MID,[correction(a)])['accepted']==0
    with b.snapshot():
        assert CareerService(b).profile('rh09')['totals']['goals']==74
        assert CareerService(b).live(MID,2,2700099)['milestones']
        assert not CareerService(b).live(MID,2,2700100)['milestones']
    c=DataStore(ROOT/'personalization',journal=factory())
    try:
        with c.snapshot():assert CareerService(c).profile('rh09')['totals']['goals']==74
        # Later revision arriving first doesn't prevent the intermediate version.
        c.ingest(MID,[correction(c,4),correction(c,3)])
        with b.snapshot():
            assert CareerService(b).live(MID,2,2700200)['milestones'][0]['event_revision']==3
            assert not CareerService(b).live(MID,2,2700300)['milestones']
        assert b.revision_state()['generation']==2
    finally:c.close()


def test_invalid_batch_cannot_partially_commit(pair):
    a,b,_=pair
    good=correction(a)
    invalid=good.model_copy(update={'event_id':'bad-actor','delivery_sequence':good.delivery_sequence+1,'player_id':'unknown'})
    with pytest.raises(ValueError):a.ingest(MID,[good,invalid])
    assert b.revision_state()['generation']==0
    assert b.journal.read(b.dataset).actions==()
    assert a.db.execute('SELECT count(*) FROM career_revisions').fetchone()[0]==0


def test_cosmos_concurrent_writers_rebuild_and_keep_both_commits():
    container=AtomicContainer();a=DataStore(ROOT/'personalization',journal=CosmosCareerJournal(container));b=DataStore(ROOT/'personalization',journal=CosmosCareerJournal(container))
    try:
        container.before_batch=lambda:b.ingest(MID,[correction(b,3)])
        a.ingest(MID,[correction(a,2)])
        frame=a.journal.read(a.dataset)
        assert frame.generation==2 and {e.revision for e in frame.actions}=={2,3}
        with a.snapshot():assert CareerService(a).profile('rh09')['totals']['goals']==75
        assert container.batches==3
        assert {p for p,_ in container.items}=={'career-'+a.dataset}
    finally:a.close();b.close()


def test_failure_does_not_serve_stale_success_or_expose_sdk_details():
    container=AtomicContainer();journal=CosmosCareerJournal(container)
    app=FastAPI();service=install_personalization(app,ROOT,journal)
    install_fan(app,service,None);install_assistant(app,service)
    with TestClient(app) as client:
        assert client.get('/api/data/players/rh09').status_code==200
        container.failure=503
        for url in ('/api/data/players/rh09','/api/data/revisions'):
            response=client.get(url)
            assert response.status_code==503
            assert 'canary' not in response.text
        assert client.post('/api/fan/players/rh09',json={'as_of':'2026-10-20T00:00:00Z'}).status_code==503
        response=client.post('/api/fan/assistant/ask',json={'question':'How many goals does Mateo Cross have?','as_of':'2026-10-20T00:00:00Z'})
        assert response.status_code==503 and 'canary' not in response.text


def test_api_and_assistant_refresh_from_another_writer(pair):
    writer,_,factory=pair
    app=FastAPI();service=install_personalization(app,ROOT,factory())
    install_assistant(app,service)
    with TestClient(app) as client:
        payload={'question':'How many goals does Mateo Cross have?','as_of':'2026-10-20T00:00:00Z'}
        assert client.post('/api/fan/assistant/ask',json=payload).json()['facts'][0]['value']==75
        writer.ingest(MID,[correction(writer)])
        assert client.get('/api/data/players/rh09').json()['totals']['goals']==74
        assert client.post('/api/fan/assistant/ask',json=payload).json()['facts'][0]['value']==74
        assert client.get(f'/api/data/matches/{MID}/replay').status_code==409
        revision=client.get('/api/data/revisions')
        assert revision.json()['generation']==1 and revision.headers['cache-control']=='no-store'
        writer.ingest(MID,[correction(writer,3)])
        assert client.post('/api/fan/assistant/ask',json=payload).json()['facts'][0]['value']==75


def processor_setup(store):
    d=CareerDelivery(dataset=store.dataset,delivery_id='career-test',match_id=MID,events=(correction(store),))
    event=SimpleNamespace(body=[d.model_dump_json().encode()],partition_key=MID,sequence_number=1)
    partition=SimpleNamespace(partition_id='0',update_checkpoint=AsyncMock())
    publisher=SimpleNamespace(publish=AsyncMock());quarantine=AsyncMock()
    processor=DeliveryProcessor(None,publisher,quarantine,career_service=lambda:CareerService(store))
    return processor,event,partition,publisher,quarantine


def test_commit_notify_checkpoint_and_failed_publish_replay(pair):
    a,b,_=pair;processor,event,partition,publisher,q=processor_setup(a)
    async def failure(notice):
        assert notice.type=='career.changed' and notice.generation==1
        with b.snapshot():assert CareerService(b).profile('rh09')['totals']['goals']==74
        partition.update_checkpoint.assert_not_awaited()
        raise RuntimeError('publish failed')
    publisher.publish.side_effect=failure
    with pytest.raises(RuntimeError):asyncio.run(processor.process(partition,event))
    partition.update_checkpoint.assert_not_awaited();q.assert_not_awaited()
    publisher.publish.side_effect=None
    asyncio.run(processor.process(partition,event))
    partition.update_checkpoint.assert_awaited_once()
    assert a.journal.read(a.dataset).generation==1


@pytest.mark.parametrize('fault',['dataset','partition','actor','identity'])
def test_invalid_routing_and_event_quarantined_before_checkpoint(pair,fault):
    import json
    a,_,_=pair;processor,event,partition,publisher,q=processor_setup(a)
    payload=json.loads(b''.join(event.body))
    if fault=='dataset':payload['dataset']='0'*64
    if fault=='partition':event.partition_key='other'
    if fault=='actor':payload['events'][0]['player_id']='unknown'
    if fault=='identity':payload['events'][0]['occurrence_order']+=1
    event.body=[json.dumps(payload).encode()]
    async def rejected(*args):partition.update_checkpoint.assert_not_awaited()
    q.side_effect=rejected
    asyncio.run(processor.process(partition,event))
    q.assert_awaited_once();partition.update_checkpoint.assert_awaited_once();publisher.publish.assert_not_awaited()
    assert a.revision_state()['generation']==0


def test_transient_storage_failure_is_not_quarantined_or_checkpointed():
    container=AtomicContainer();store=DataStore(ROOT/'personalization',journal=CosmosCareerJournal(container))
    try:
        processor,event,partition,pub,q=processor_setup(store);container.failure=503
        with pytest.raises(HistoryStorageError):asyncio.run(processor.process(partition,event))
        q.assert_not_awaited();partition.update_checkpoint.assert_not_awaited();pub.publish.assert_not_awaited()
    finally:store.close()


def test_reader_tokens_are_dataset_scoped_and_cannot_send(pair):
    store,_,factory=pair;client=SimpleNamespace(get_client_access_token=AsyncMock(return_value={'url':'wss://example.webpubsub.azure.com/test'}))
    publisher=Publisher(client)
    app=create_app(ROOT,career_journal=factory(),revision_publisher=publisher)
    with TestClient(app) as api:
        result=api.get('/api/data/revisions/negotiate')
        assert result.status_code==200 and result.headers['cache-control']=='no-store'
    client.get_client_access_token.assert_awaited_once_with(groups=['career.'+store.dataset],roles=[],minutes_to_expire=5)

def test_sqlite_two_concurrent_writers_serialize_without_lost_updates(tmp_path):
    from concurrent.futures import ThreadPoolExecutor
    a=DataStore(ROOT/'personalization',journal=SQLiteCareerJournal(tmp_path/'shared.sqlite3'))
    b=DataStore(ROOT/'personalization',journal=SQLiteCareerJournal(tmp_path/'shared.sqlite3'))
    try:
        first,second=correction(a),correction(b,3)
        with ThreadPoolExecutor(max_workers=2) as pool:
            results=list(pool.map(lambda pair:pair[0].ingest(MID,[pair[1]]),[(a,first),(b,second)]))
        assert sum(r['accepted'] for r in results)==2
        frame=a.journal.read(a.dataset)
        assert frame.generation==2 and len(frame.actions)==2
        with a.snapshot():assert CareerService(a).profile('rh09')['totals']['goals']==75
    finally:a.close();b.close()


def test_cosmos_failed_atomic_write_does_not_mutate_local_view():
    from azure.cosmos.exceptions import CosmosHttpResponseError
    container=AtomicContainer();store=DataStore(ROOT/'personalization',journal=CosmosCareerJournal(container))
    try:
        def fail():raise CosmosHttpResponseError(status_code=503,message='private endpoint canary')
        container.before_batch=fail
        with pytest.raises(HistoryStorageError,match='could not be committed'):store.ingest(MID,[correction(store)])
        assert store.db.execute('SELECT COUNT(*) FROM career_revisions').fetchone()[0]==0
        assert not container.items
        assert store.ingest(MID,[correction(store)])['accepted']==1
    finally:store.close()


def test_local_only_revisions_are_not_silently_discarded_when_enabling_journal(tmp_path):
    store=DataStore(ROOT/'personalization',tmp_path/'index.sqlite3')
    store.ingest(MID,[correction(store)]);store.close()
    shared=DataStore(ROOT/'personalization',tmp_path/'index.sqlite3',journal=SQLiteCareerJournal(tmp_path/'journal.sqlite3'))
    try:
        with pytest.raises(HistoryStorageError,match='differ'):shared.revision_state()
    finally:shared.close()


def test_correction_during_model_narrative_rechecks_shared_history(pair):
    from counterpress.assistant.service import AssistantService
    from counterpress.assistant.contracts import AskRequest
    writer,_,factory=pair
    app=FastAPI();service=install_personalization(app,ROOT,factory())
    class Planner:
        async def plan(self,question,context):
            return AssistantService(service()).local_plan(AskRequest(question=question,as_of='2026-10-20T00:00:00Z')),{}
    class Narrator:
        async def explain(self,*args):
            writer.ingest(MID,[correction(writer)])
            raise ValueError('Rejected narrative')
    install_assistant(app,service,planner=Planner(),narrator=Narrator())
    with TestClient(app) as client:
        response=client.post('/api/fan/assistant/ask',json={'question':'How many goals does Mateo Cross have?','as_of':'2026-10-20T00:00:00Z'})
        result=response.json()
        assert response.status_code==200
        assert result['facts'][0]['value']==74
        assert result['narrative']['fallback_reason']=='records_changed'
        assert '75' not in str(result['narrative']['blocks'])


def test_journal_capacity_rejects_before_committing(pair,monkeypatch):
    from counterpress.personalization import journal
    store,_,_=pair
    monkeypatch.setattr(journal,'MAX_JOURNAL_BYTES',2000)
    with pytest.raises(ValueError,match='full'):store.ingest(MID,[correction(store)])
    assert store.revision_state()['generation']==0
    assert store.db.execute('SELECT COUNT(*) FROM career_revisions').fetchone()[0]==0
