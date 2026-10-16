import asyncio
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock
import pytest
from counterpress.api.main import create_app
from counterpress.api.snapshots import SnapshotService
from counterpress.streaming.contracts import Delivery, notice
from counterpress.streaming.consumer import DeliveryProcessor
from counterpress.streaming.azure import Publisher
from test_history import updates
from test_snapshot_api import request

FIXTURES = Path(__file__).resolve().parents[1] / 'fixtures'

def setup():
    service = SnapshotService(FIXTURES)
    history = service.history('increase')
    delivery = Delivery(delivery_id='delivery-test', scenario_id='increase', match_id=history.fixture.match_id, events=updates())
    event = SimpleNamespace(body=[delivery.model_dump_json().encode()], partition_key=delivery.match_id, sequence_number=1)
    partition = SimpleNamespace(partition_id='0', update_checkpoint=AsyncMock())
    publisher = SimpleNamespace(publish=AsyncMock())
    quarantine = AsyncMock()
    return service, delivery, event, partition, publisher, quarantine

@pytest.mark.parametrize("received_key_bytes", [False, True])
def test_commit_notify_checkpoint_and_duplicate_replay(tmp_path, received_key_bytes):
    s,d,e,p,pub,q=setup()
    if received_key_bytes:
        e.partition_key = e.partition_key.encode("utf-8")
    async def check(n):
        assert len(s.history('increase').records)==93
        assert s.history('increase').changes[-1].revision==4
        p.update_checkpoint.assert_not_awaited()
        assert n.revisions[0].revision==4
    pub.publish.side_effect=check
    processor=DeliveryProcessor(s,pub,q)
    asyncio.run(processor.process(p,e))
    p.update_checkpoint.assert_awaited_once_with(e)
    p.update_checkpoint.reset_mock()
    asyncio.run(processor.process(p,e))
    assert len(s.history('increase').records)==93
    assert pub.publish.await_count==2
    q.assert_not_awaited()

def test_failure_after_commit_replays_and_republishes_without_duplicate_facts():
    s,d,e,p,pub,q=setup()
    processor=DeliveryProcessor(s,pub,q)
    pub.publish.side_effect=RuntimeError('private endpoint canary')
    with pytest.raises(RuntimeError):asyncio.run(processor.process(p,e))
    p.update_checkpoint.assert_not_awaited()
    assert len(s.history('increase').records)==93
    pub.publish.side_effect=None
    asyncio.run(processor.process(p,e))
    assert len(s.history('increase').changes)==4
    p.update_checkpoint.assert_awaited_once()

@pytest.mark.parametrize('fault',['malformed','wrong_partition','unknown_scenario','wrong_match','conflicting_revision'])
def test_invalid_messages_quarantine_before_checkpoint_without_mutating_history(fault):
    s,d,e,p,pub,q=setup()
    before=s.history('increase')
    raw=d.model_dump(mode='json')
    if fault=='wrong_partition':e.partition_key='other-match'
    if fault=='unknown_scenario':raw['scenario_id']='unknown'
    if fault=='wrong_match':
        raw['match_id']='other-match';e.partition_key='other-match'
        for item in raw['events']:item['match_id']='other-match'
    if fault=='conflicting_revision':raw['events'][0]['revision']=1
    import json
    e.body=[b'not json' if fault=='malformed' else json.dumps(raw).encode()]
    async def persisted(*args):p.update_checkpoint.assert_not_awaited()
    q.side_effect=persisted
    asyncio.run(DeliveryProcessor(s,pub,q).process(p,e))
    assert s.history('increase')==before
    q.assert_awaited_once();pub.publish.assert_not_awaited();p.update_checkpoint.assert_awaited_once()

def test_quarantine_failure_does_not_acknowledge_poison():
    s,d,e,p,pub,q=setup();e.body=[b'bad'];q.side_effect=RuntimeError('storage down')
    with pytest.raises(RuntimeError):asyncio.run(DeliveryProcessor(s,pub,q).process(p,e))
    p.update_checkpoint.assert_not_awaited()

def test_transient_error_retries_same_event_before_checkpoint(monkeypatch):
    s,d,e,p,pub,q=setup();pub.publish.side_effect=[RuntimeError('down'),None]
    monkeypatch.setattr('counterpress.streaming.consumer.asyncio.sleep',AsyncMock())
    asyncio.run(DeliveryProcessor(s,pub,q).on_event(p,e))
    assert pub.publish.await_count==2
    p.update_checkpoint.assert_awaited_once()

def test_read_only_scenario_scoped_tokens_and_sanitized_errors():
    client=SimpleNamespace(get_client_access_token=AsyncMock(return_value={'url':'wss://test.webpubsub.azure.com/client?access_token=test'}))
    app=create_app(FIXTURES,revision_publisher=Publisher(client))
    response=request(app,'/api/revisions/negotiate?scenario_id=increase')
    assert response.status_code==200
    assert response.headers['cache-control']=='no-store'
    client.get_client_access_token.assert_awaited_once_with(groups=['scenario.increase'],roles=[],minutes_to_expire=5)
    assert request(app,'/api/revisions/negotiate?scenario_id=unknown').status_code==404
    client.get_client_access_token.side_effect=RuntimeError('private endpoint canary')
    failed=request(app,'/api/revisions/negotiate?scenario_id=increase')
    assert failed.status_code==503 and 'canary' not in failed.text
    assert request(create_app(FIXTURES),'/api/revisions/negotiate?scenario_id=increase').json()=={'enabled':False}

def test_negotiation_is_bounded():
    pub=SimpleNamespace(negotiate=AsyncMock(return_value={'enabled':True,'url':'wss://test'}))
    app=create_app(FIXTURES,revision_publisher=pub)
    for _ in range(30):assert request(app,'/api/revisions/negotiate?scenario_id=increase').status_code==200
    assert request(app,'/api/revisions/negotiate?scenario_id=increase').status_code==429
    assert pub.negotiate.await_count==30

def test_stream_scenario_is_isolated_and_notice_includes_withdrawals():
    s=SnapshotService(FIXTURES)
    stream=s.history('stream-recovery');original=s.history('increase')
    revised=tuple(e.model_copy(update={'match_id':stream.fixture.match_id}) for e in updates())
    intermediate=s.ingest('stream-recovery',revised[:3])
    n=notice('stream-recovery',intermediate)
    assert n.revisions[0].operation=='withdraw'
    assert s.history('increase')==original
    assert n.match_id!=original.fixture.match_id

def test_cloud_runtime_constructs_and_closes_actual_sdk_clients_without_network(monkeypatch):
    from azure.eventhub.aio import EventHubConsumerClient
    from counterpress.streaming.azure import StreamingRuntime
    values={'COUNTERPRESS_STORAGE':'cosmos','COUNTERPRESS_EVENTHUB_NAMESPACE':'example.servicebus.windows.net',
        'COUNTERPRESS_EVENTHUB_NAME':'deliveries','COUNTERPRESS_CHECKPOINT_ENDPOINT':'https://example.blob.core.windows.net',
        'COUNTERPRESS_PUBSUB_ENDPOINT':'https://example.webpubsub.azure.com','COUNTERPRESS_STREAM_CLIENT_ID':'test-identity'}
    for k,v in values.items():monkeypatch.setenv(k,v)
    async def hold(*args,**kwargs):await asyncio.Event().wait()
    monkeypatch.setattr(EventHubConsumerClient,'receive',hold)
    async def run():
        runtime=StreamingRuntime(SnapshotService(FIXTURES))
        await runtime.start()
        assert runtime.publisher is not None and runtime.task is not None
        await runtime.close()
        assert runtime.task.done()
    asyncio.run(run())

def test_pubsub_sdk_wire_payload_is_a_json_object_not_a_double_encoded_string():
    import json
    from azure.core.credentials import AzureKeyCredential
    from azure.messaging.webpubsubservice.aio import WebPubSubServiceClient
    s=SnapshotService(FIXTURES)
    n=notice('increase',s.history('increase'))
    async def run():
        async with WebPubSubServiceClient('https://example.webpubsub.azure.com',hub='counterpress',credential=AzureKeyCredential('test')) as client:
            async def wire(request,**kwargs):
                body=json.loads(request.body)
                assert isinstance(body,dict)
                assert body['type']=='history.changed' and body['revisions'][0]['revision']==1
                return SimpleNamespace(http_response=SimpleNamespace(status_code=202))
            client._client._pipeline.run=AsyncMock(side_effect=wire)
            await Publisher(client).publish(n)
            client._client._pipeline.run.assert_awaited_once()
    asyncio.run(run())
