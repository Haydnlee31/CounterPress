"""Server-selected hub/container isolation. No Azure requests or real tokens."""
import asyncio
import base64
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock
from urllib.parse import parse_qs, unquote, urlparse
from pathlib import Path

import pytest

from counterpress.streaming.azure import StreamingRuntime, blob_container, pubsub_hub
from counterpress.streaming.contracts import CareerRevisionNotice


def configured(monkeypatch):
    values={'COUNTERPRESS_STORAGE':'cosmos','COUNTERPRESS_EVENTHUB_NAMESPACE':'example.servicebus.windows.net',
            'COUNTERPRESS_EVENTHUB_NAME':'deliveries','COUNTERPRESS_CHECKPOINT_ENDPOINT':'https://example.blob.core.windows.net',
            'COUNTERPRESS_PUBSUB_ENDPOINT':'https://example.webpubsub.azure.com','COUNTERPRESS_STREAM_CLIENT_ID':'fake-identity',
            'COUNTERPRESS_TELEMETRY':'off'}
    for name,value in values.items():monkeypatch.setenv(name,value)
    for name in ('COUNTERPRESS_PUBSUB_HUB','COUNTERPRESS_CHECKPOINT_CONTAINER','COUNTERPRESS_QUARANTINE_CONTAINER'):
        monkeypatch.delenv(name,raising=False)


@pytest.mark.parametrize('value',['counterpress','counterpress_phase4','A','A'+'0'*127])
def test_valid_server_hub_subset(monkeypatch,value):
    monkeypatch.setenv('COUNTERPRESS_PUBSUB_HUB',value)
    assert pubsub_hub()==value


@pytest.mark.parametrize('value',['','1hub','_hub','bad-hub','other/hub','hub?x=y',' space','space ', 'équipe','a'*129,'hub\n'])
def test_invalid_hub_never_echoes_config_or_falls_back(monkeypatch,value):
    monkeypatch.setenv('COUNTERPRESS_PUBSUB_HUB',value)
    with pytest.raises(ValueError) as error:pubsub_hub()
    assert str(error.value)=='Invalid streaming hub name'


@pytest.mark.parametrize('value',['abc','eventhub-checkpoints-phase4','rejected-deliveries-phase4','a'*63])
def test_valid_blob_container_override(monkeypatch,value):
    monkeypatch.setenv('COUNTERPRESS_CHECKPOINT_CONTAINER',value)
    assert blob_container('COUNTERPRESS_CHECKPOINT_CONTAINER','eventhub-checkpoints')==value


@pytest.mark.parametrize('value',['','ab','Uppercase','bad--name','-start','end-','path/name','a'*64,'name\n'])
def test_invalid_blob_container_does_not_fall_back(monkeypatch,value):
    monkeypatch.setenv('COUNTERPRESS_QUARANTINE_CONTAINER',value)
    with pytest.raises(ValueError,match='^Invalid streaming container name$'):
        blob_container('COUNTERPRESS_QUARANTINE_CONTAINER','rejected-deliveries')


class Resource:
    def __init__(self):self.close=AsyncMock()
    async def __aenter__(self):return self
    async def __aexit__(self,*args):await self.close()
    async def receive(self,**kwargs):await asyncio.Event().wait()


@pytest.mark.parametrize('isolated',[False,True])
def test_runtime_binds_publish_and_receive_only_tokens_to_one_server_hub(monkeypatch,isolated):
    from azure.core.credentials import AzureKeyCredential
    from azure.messaging.webpubsubservice.aio import WebPubSubServiceClient
    configured(monkeypatch)
    hub='counterpress_phase4' if isolated else 'counterpress'
    checkpoint='eventhub-checkpoints-phase4' if isolated else 'eventhub-checkpoints'
    quarantine='rejected-deliveries-phase4' if isolated else 'rejected-deliveries'
    if isolated:
        monkeypatch.setenv('COUNTERPRESS_PUBSUB_HUB',hub)
        monkeypatch.setenv('COUNTERPRESS_CHECKPOINT_CONTAINER',checkpoint)
        monkeypatch.setenv('COUNTERPRESS_QUARANTINE_CONTAINER',quarantine)
    seen={};credential=Resource();consumer=Resource();checkpoints=Resource();rejected=Resource()
    def pubsub(endpoint,**kwargs):
        seen['pubsub']=kwargs
        # The real SDK serializes URLs and locally signed test-only reader JWTs.
        # It never receives a real secret or network-capable credential here.
        client=WebPubSubServiceClient(endpoint,hub=kwargs['hub'],credential=AzureKeyCredential('test-only-'+'0'*32))
        async def wire(request,**options):
            seen['publish_url']=request.url
            seen['publish_body']=json.loads(request.body)
            return SimpleNamespace(http_response=SimpleNamespace(status_code=202))
        client._client._pipeline.run=AsyncMock(side_effect=wire)
        return client
    def checkpoint_store(**kwargs):seen['checkpoint']=kwargs;return checkpoints
    def quarantine_store(*args,**kwargs):seen['quarantine']=kwargs;return rejected
    def receiver(**kwargs):seen['receiver']=kwargs;return consumer
    monkeypatch.setattr('azure.identity.aio.ManagedIdentityCredential',lambda **kwargs:credential)
    monkeypatch.setattr('azure.messaging.webpubsubservice.aio.WebPubSubServiceClient',pubsub)
    monkeypatch.setattr('azure.eventhub.extensions.checkpointstoreblobaio.BlobCheckpointStore',checkpoint_store)
    monkeypatch.setattr('azure.storage.blob.aio.ContainerClient',quarantine_store)
    monkeypatch.setattr('azure.eventhub.aio.EventHubConsumerClient',receiver)
    async def run():
        runtime=StreamingRuntime(None)
        try:
            await runtime.start()
            monkeypatch.setenv('COUNTERPRESS_PUBSUB_HUB','later_change')
            dataset='a'*64
            await runtime.publisher.publish(CareerRevisionNotice(dataset=dataset,generation=2,match_id='match'))
            token=await runtime.publisher.negotiate_career(dataset)
            scenario_token=await runtime.publisher.negotiate('increase')
            assert seen['pubsub']['hub']==hub
            assert seen['checkpoint']['container_name']==checkpoint
            assert seen['quarantine']['container_name']==quarantine
            assert seen['receiver']['checkpoint_store'] is checkpoints
            assert seen['receiver']['consumer_group']=='$Default'
            assert f'/api/hubs/{hub}/groups/career.{dataset}/' in unquote(urlparse(seen['publish_url']).path)
            assert seen['publish_body']=={'type':'career.changed','schema_version':1,'dataset':dataset,'generation':2,'match_id':'match'}
            for result,group in ((token,'career.'+dataset),(scenario_token,'scenario.increase')):
                url=urlparse(result['url'])
                assert url.path=='/client/hubs/'+hub
                encoded=parse_qs(url.query)['access_token'][0].split('.')[1]
                payload=json.loads(base64.urlsafe_b64decode(encoded+'='*(-len(encoded)%4)))
                assert payload['webpubsub.group']==[group]
                assert not payload.get('role')
                assert payload['exp']-payload['iat']==300
                assert payload['aud'].endswith('/client/hubs/'+hub)
        finally:await runtime.close()
        assert runtime.task.done()
        credential.close.assert_awaited_once();checkpoints.close.assert_awaited_once()
    asyncio.run(run())


@pytest.mark.parametrize('setting,value',[
    ('COUNTERPRESS_PUBSUB_HUB','/production'),
    ('COUNTERPRESS_CHECKPOINT_CONTAINER','bad--container'),
    ('COUNTERPRESS_QUARANTINE_CONTAINER','Uppercase'),
])
def test_bad_isolation_config_fails_before_credential_or_clients(monkeypatch,setting,value):
    configured(monkeypatch);monkeypatch.setenv(setting,value)
    def forbidden(**kwargs):raise AssertionError('No credential should be created')
    monkeypatch.setattr('azure.identity.aio.ManagedIdentityCredential',forbidden)
    with pytest.raises(ValueError,match='Invalid streaming'):
        asyncio.run(StreamingRuntime(None).start())


def test_browser_query_cannot_select_production_hub_or_another_dataset(monkeypatch,tmp_path):
    from azure.core.credentials import AzureKeyCredential
    from azure.messaging.webpubsubservice.aio import WebPubSubServiceClient
    from counterpress.api.main import create_app
    from counterpress.personalization.journal import SQLiteCareerJournal
    from counterpress.streaming.azure import Publisher
    from test_snapshot_api import request
    monkeypatch.setenv('COUNTERPRESS_PUBSUB_HUB','counterpress_phase4')
    client=WebPubSubServiceClient('https://example.webpubsub.azure.com',hub=pubsub_hub(),credential=AzureKeyCredential('test-only-'+'0'*32))
    app=create_app(Path(__file__).resolve().parents[1]/'fixtures',
                   career_journal=SQLiteCareerJournal(tmp_path/'career.sqlite3'),revision_publisher=Publisher(client))
    try:
        result=request(app,'/api/data/revisions/negotiate?hub=counterpress&dataset='+'b'*64)
        assert result.status_code==200
        url=urlparse(result.json()['url'])
        assert url.path=='/client/hubs/counterpress_phase4'
        encoded=parse_qs(url.query)['access_token'][0].split('.')[1]
        payload=json.loads(base64.urlsafe_b64decode(encoded+'='*(-len(encoded)%4)))
        assert payload['webpubsub.group']==['career.'+app.state.career_service().store.dataset]
        scenario=request(app,'/api/revisions/negotiate?scenario_id=increase&hub=counterpress')
        assert scenario.status_code==200
        assert urlparse(scenario.json()['url']).path=='/client/hubs/counterpress_phase4'
    finally:
        asyncio.run(client.close())
        app.state.career_service().store.close()
