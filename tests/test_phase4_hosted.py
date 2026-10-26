"""Hosted harness contract using real local APIs/journal; no Azure or models."""
from contextlib import ExitStack
from datetime import datetime, timedelta, timezone
import importlib.util
import json
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient
import pytest

from counterpress.fan.api import install_fan
from counterpress.personalization.api import install_personalization
from counterpress.personalization.journal import SQLiteCareerJournal
from counterpress.personalization.store import DataStore
from counterpress.streaming.contracts import CareerDelivery

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('phase4_hosted_check',ROOT/'scripts/check_phase4_hosted.py')
harness=importlib.util.module_from_spec(spec)
spec.loader.exec_module(harness)


def proof():
    return {'isolated':True,'inference':False,'production_unchanged':True,'image_digest':'sha256:'+'a'*64,
            'dataset':harness.EXPECTED['dataset'],'origin_sha256':harness.sha256(b'https://isolated.example.test').hexdigest(),'checked_at':datetime.now(timezone.utc).isoformat(),
            'isolation_checks':{key:True for key in harness.PROOF_CHECKS}}


class LocalReader:
    def __init__(self,client,origin):self.client=client;self.calls=[];self.origin=origin
    def get(self,path,params=None):
        self.calls.append(('GET',path))
        result=self.client.get(path,params=params)
        assert result.status_code==200,result.status_code
        return result.json()
    def post(self,path,body):
        self.calls.append(('POST',path))
        assert path.startswith('/api/fan/') and '/assistant/' not in path
        result=self.client.post(path,json=body)
        assert result.status_code==200,result.status_code
        return result.json()


@pytest.fixture
def setup(tmp_path,monkeypatch):
    monkeypatch.setenv('COUNTERPRESS_PROFILE_DB_PATH',':memory:')
    with ExitStack() as stack:
        def app(name,isolated):
            path=tmp_path/(name+'.sqlite3')
            journal=SQLiteCareerJournal(path);stack.callback(journal.close)
            writer=DataStore(ROOT/'fixtures/personalization',journal=journal);stack.callback(writer.close)
            api=FastAPI();get_career=install_personalization(api,ROOT/'fixtures',journal)
            stack.callback(lambda:get_career().store.close());install_fan(api,get_career)
            telemetry={'schema':'phase4_counters_v1','processed':0,
                       **{k:0 for k in harness.FAILURES},'pending':False,'observed_backlog':0}
            if isolated:
                api.get('/api/phase4/config')(lambda:harness.CONFIG.copy())
                api.get('/api/phase4/telemetry')(lambda:telemetry.copy())
            reader=LocalReader(stack.enter_context(TestClient(api)),f'https://{name}.example.test')
            return reader,writer,telemetry
        test,writer,telemetry=app('isolated',True)
        production,prod_writer,_=app('production',False)
        yield test,production,writer,prod_writer,telemetry


def test_complete_hosted_protocol_preserves_production_and_original_cards(setup):
    test,production,writer,prod_writer,telemetry=setup
    authorization=proof()
    state=harness.baseline(test,production,authorization)
    prod_before=prod_writer.revision_state()
    delivered={}
    for step in harness.STEPS:
        payload=harness.prepare(test,production,state,authorization,step)
        delivery=CareerDelivery.model_validate_json(json.dumps(payload))
        delivered[step]=payload
        if step=='duplicate':assert payload==delivered['retraction']
        writer.ingest(delivery.match_id,delivery.events)
        telemetry['processed']+=1
        state,result=harness.check_step(test,production,state,authorization,step,attempts=1)
        assert result['generation']==harness.GENERATIONS[step]
        assert result['original_cards_preserved'] and result['production_unchanged']
        assert result['processed_delta']==1
    assert state['generation']==4 and state['processed']==5
    assert prod_writer.revision_state()==prod_before
    assert all('/assistant/' not in path for _,path in test.calls+production.calls)
    assert not any(word in json.dumps(state) for word in ('https://','wss://','access_token','client_id'))


def test_prepare_refuses_production_change_and_never_sends(setup):
    test,production,writer,prod_writer,telemetry=setup
    authorization=proof();state=harness.baseline(test,production,authorization)
    event=next(e for e in prod_writer.original(harness.EXPECTED['match_id']).events if e.event_id=='e01019')
    prod_writer.ingest(event.match_id,[event.model_copy(update={'revision':2,
        'delivery_sequence':state['sequence']+1,'available_ms':1051000,'retracted':True})])
    with pytest.raises(harness.VerificationError,match='production_state_changed'):
        harness.prepare(test,production,state,authorization,'correction')
    assert writer.revision_state()['generation']==0 and telemetry['processed']==0


def test_duplicate_requires_observed_processing_not_only_unchanged_generation(setup):
    test,production,writer,_,telemetry=setup
    authorization=proof();state=harness.baseline(test,production,authorization)
    for step in ('correction','retraction'):
        payload=harness.payload_for(state,step);delivery=CareerDelivery.model_validate_json(json.dumps(payload))
        writer.ingest(delivery.match_id,delivery.events);telemetry['processed']+=1
        state,_=harness.check_step(test,production,state,authorization,step,attempts=1)
    with pytest.raises(harness.VerificationError,match='delivery_not_confirmed'):
        harness.check_step(test,production,state,authorization,'duplicate',attempts=1)


def test_readers_fail_closed_on_unexpected_generation(setup):
    test,production,writer,_,telemetry=setup
    authorization=proof();state=harness.baseline(test,production,authorization)
    with pytest.raises(harness.VerificationError,match='step_out_of_order'):
        harness.prepare(test,production,state,authorization,'restoration')
    payload=harness.payload_for(state,'correction');delivery=CareerDelivery.model_validate_json(json.dumps(payload))
    writer.ingest(delivery.match_id,delivery.events)
    telemetry['processed']+=1;telemetry['publish_failures']=1
    with pytest.raises(harness.VerificationError,match='test_consumer_failure'):
        harness.check_step(test,production,state,authorization,'correction',attempts=1)


@pytest.mark.parametrize('change',['expired','missing','prod','inference','dataset'])
def test_isolation_proof_cannot_be_skipped_or_stale(change):
    value=proof()
    if change=='expired':value['checked_at']=(datetime.now(timezone.utc)-timedelta(hours=3)).isoformat()
    elif change=='missing':value['isolation_checks'].pop('journal')
    elif change=='prod':value['production_unchanged']=False
    elif change=='inference':value['inference']=True
    else:value['dataset']='0'*64
    with pytest.raises(harness.VerificationError):harness.proof_check(value)


@pytest.mark.parametrize('url',['http://example.com','https://user:secret@example.com','https://example.com/?key=private','https://example.com/path'])
def test_reader_rejects_unsafe_or_non_origin_urls(url):
    with pytest.raises(harness.VerificationError,match='invalid_reader_origin'):harness.Reader(url)


def test_only_valid_scoped_hint_can_trigger_confirmation():
    message={'type':'career.changed','schema_version':1,'dataset':harness.EXPECTED['dataset'],
             'generation':2,'match_id':harness.EXPECTED['match_id']}
    assert harness.valid_hint(json.dumps(message),2)
    for change in ({'dataset':'wrong'},{'generation':True},{'generation':3},{'type':'other'},{'match_id':'other'}):
        assert not harness.valid_hint(json.dumps({**message,**change}),2)
    assert not harness.valid_hint('not-json',2)
    assert not harness.valid_hint('[]',2)
    assert not harness.valid_hint(json.dumps({**message,'schema_version':True}),2)
    assert not harness.valid_hint('a'*4097,2)


def test_private_files_do_not_replace_prior_results(tmp_path):
    path=tmp_path/'private.json'
    harness.private_write(path,{'status':'passed'})
    assert path.stat().st_mode & 0o777 == 0o600
    with pytest.raises(FileExistsError):harness.private_write(path,{'changed':True})
    harness.private_write(path,{'status':'next'},replace=True)
    assert json.loads(path.read_text())=={'status':'next'}


def test_socket_watcher_records_only_valid_hint_and_reconnects(monkeypatch,capsys):
    import asyncio
    from types import SimpleNamespace
    import aiohttp
    calls=[]
    class FakeReader:
        def get(self,path):
            calls.append(path)
            if path.endswith('/negotiate'):
                return {'enabled':True,'url':'wss://private.webpubsub.azure.com/client?access_token=never-record-me'}
            return {'dataset':harness.EXPECTED['dataset'],'enabled':True,'generation':2,'matches':{}}
    class Socket:
        closed=False
        messages=[SimpleNamespace(type=aiohttp.WSMsgType.TEXT,data='[]'),
                  SimpleNamespace(type=aiohttp.WSMsgType.TEXT,data=json.dumps({
                      'type':'career.changed','schema_version':1,'dataset':harness.EXPECTED['dataset'],
                      'generation':2,'match_id':harness.EXPECTED['match_id']}))]
        async def __aenter__(self):return self
        async def __aexit__(self,*_):self.closed=True
        async def receive(self):return self.messages.pop(0)
    class Session:
        def __init__(self,**_):pass
        async def __aenter__(self):return self
        async def __aexit__(self,*_):pass
        def ws_connect(self,url,**_):
            assert url.startswith('wss://')
            return Socket()
    monkeypatch.setattr(aiohttp,'ClientSession',Session)
    report=asyncio.run(harness.watch(FakeReader(),2,seconds=1))
    assert report['reconnected'] and report['authoritative_generation']==2
    assert calls.count('/api/data/revisions/negotiate')==2
    assert 'never-record-me' not in json.dumps(report)+capsys.readouterr().out


def test_http_transport_error_does_not_echo_endpoint_or_secret():
    import httpx
    reader=harness.Reader('https://example.test')
    reader.client.close()
    def fail(_):raise httpx.ConnectError('https://private.invalid?key=never-print-this')
    reader.client=httpx.Client(transport=httpx.MockTransport(fail),base_url='https://example.test')
    try:
        with pytest.raises(harness.VerificationError) as error:reader.get('/api/data/revisions')
        assert str(error.value)=='reader_transport_failed'
    finally:reader.close()


def test_valid_isolation_proof_cannot_authorize_another_origin():
    from types import SimpleNamespace
    with pytest.raises(harness.VerificationError,match='isolated_origin_mismatch'):
        harness.bound_proof(SimpleNamespace(origin='https://different.example.test'),proof())


class ProductionModeReader:
    """Independent minimal public read responses, with no ingestion bridge."""
    def __init__(self, enabled=False):self.enabled=enabled
    def get(self,path,params=None):
        if path=='/api/data/revisions':
            return {'dataset':harness.EXPECTED['dataset'],'enabled':self.enabled,
                    'generation':0,'matches':{}}
        assert path=='/api/data/matches'
        return {'items':[{'match_id':'public-match','period_lengths_ms':[2700000,2700000]}],'total':1}
    def post(self,path,body):
        if path=='/api/fan/home':return {'highlights':[],'highlight_total':0}
        assert path=='/api/fan/matches/public-match'
        return {'evidence':{'event_digest':'a'*64}}


def test_disabled_production_is_accepted_and_unchanged():
    reader=ProductionModeReader()
    snapshot=harness.production_snapshot(reader)
    assert snapshot['revision']['enabled'] is False
    state={'production_hash':harness.hashed(snapshot)}
    assert harness.unchanged_production(reader,state)==state['production_hash']
    with pytest.raises(harness.VerificationError,match='revision_dataset_or_storage_invalid'):
        harness.revision(reader)


def test_production_mode_change_changes_fingerprint_and_blocks_progress():
    reader=ProductionModeReader()
    original=harness.hashed(harness.production_snapshot(reader))
    reader.enabled=True
    assert harness.hashed(harness.production_snapshot(reader))!=original
    with pytest.raises(harness.VerificationError,match='production_state_changed'):
        harness.unchanged_production(reader,{'production_hash':original})


@pytest.mark.parametrize('enabled',[None,0,1,'false','true'])
def test_production_requires_an_explicit_boolean_mode(enabled):
    with pytest.raises(harness.VerificationError,match='revision_dataset_or_storage_invalid'):
        harness.production_snapshot(ProductionModeReader(enabled))
