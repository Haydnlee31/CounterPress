"""Server-only Entra clients. No shared access keys or connection strings."""
import asyncio
from contextlib import AsyncExitStack
import logging
import os
import re
from urllib.parse import urlparse
from counterpress.streaming.consumer import DeliveryProcessor
from counterpress.streaming.telemetry import StreamTelemetry

log = logging.getLogger(__name__)

def required(name: str) -> str:
    value = os.environ.get(name, '')
    if not value:
        raise ValueError('Streaming configuration is incomplete')
    return value

def endpoint(name: str, suffix: str) -> str:
    value = required(name)
    p = urlparse(value)
    if (p.scheme != 'https' or not p.hostname or not p.hostname.endswith(suffix)
        or p.username or p.password or p.query or p.fragment or p.path not in ('', '/') or p.port):
        raise ValueError('Invalid streaming endpoint')
    return value.rstrip('/')

class Publisher:
    def __init__(self, client):
        self.client = client

    async def publish(self, notice):
        await self.client.send_to_group('scenario.' + notice.scenario_id,
            notice.model_dump(mode='json'), content_type='application/json')

    async def negotiate(self, scenario):
        token = await self.client.get_client_access_token(groups=['scenario.' + scenario],
            roles=[], minutes_to_expire=5)
        return {'enabled': True, 'url': token['url']}

class StreamingRuntime:
    def __init__(self, service):
        self.service = service
        self.stack = AsyncExitStack()
        self.task = None
        self.publisher = None
        self.telemetry = StreamTelemetry()
        self.telemetry_task = None
        self.metric_sender = None

    async def start(self):
        if os.environ.get("COUNTERPRESS_STORAGE") != "cosmos":
            raise ValueError("Azure streaming requires shared Cosmos history")
        from azure.identity.aio import ManagedIdentityCredential
        from azure.eventhub.aio import EventHubConsumerClient
        from azure.eventhub.extensions.checkpointstoreblobaio import BlobCheckpointStore
        from azure.storage.blob.aio import ContainerClient
        from azure.messaging.webpubsubservice.aio import WebPubSubServiceClient
        ns = required('COUNTERPRESS_EVENTHUB_NAMESPACE')
        if not re.fullmatch(r'[a-zA-Z0-9-]+\.servicebus\.windows\.net', ns):
            raise ValueError('Invalid Event Hubs namespace')
        blob = endpoint('COUNTERPRESS_CHECKPOINT_ENDPOINT', '.blob.core.windows.net')
        pubsub = endpoint('COUNTERPRESS_PUBSUB_ENDPOINT', '.webpubsub.azure.com')
        credential = await self.stack.enter_async_context(ManagedIdentityCredential(
            client_id=required('COUNTERPRESS_STREAM_CLIENT_ID')))
        client = await self.stack.enter_async_context(WebPubSubServiceClient(pubsub,
            hub='counterpress', credential=credential, retry_total=2, logging_enable=False))
        self.publisher = Publisher(client)
        quarantine = await self.stack.enter_async_context(ContainerClient(blob,
            container_name='rejected-deliveries', credential=credential, retry_total=2))
        async def reject(partition, sequence, body, digest):
            from azure.core.exceptions import ResourceExistsError
            try:
                await quarantine.upload_blob(f'{ns}/{required("COUNTERPRESS_EVENTHUB_NAME")}/{partition}/{sequence}',
                    body or b'oversized delivery omitted', overwrite=False,
                    metadata={'sha256': digest, 'reason': 'invalid_delivery'})
            except ResourceExistsError:
                pass  # Stable offset identity, already durably quarantined.
        processor = DeliveryProcessor(self.service, self.publisher, reject, self.telemetry)
        self.checkpoints = BlobCheckpointStore(blob_account_url=blob,
            container_name='eventhub-checkpoints', credential=credential)
        self.consumer = await self.stack.enter_async_context(EventHubConsumerClient(
            fully_qualified_namespace=ns, eventhub_name=required('COUNTERPRESS_EVENTHUB_NAME'),
            consumer_group='$Default', credential=credential, checkpoint_store=self.checkpoints,
            logging_enable=False, retry_total=3, prefetch=32))
        async def run():
            while True:
                try:
                    await self.consumer.receive(on_event=processor.on_event, starting_position='-1',
                        track_last_enqueued_event_properties=True)
                except asyncio.CancelledError:
                    raise
                except Exception:
                    self.telemetry.increment('consumer_failures')
                    log.warning('stream_consumer_retry')
                    await asyncio.sleep(5)
        self.task = asyncio.create_task(run())
        if self.telemetry.enabled:
            from aiohttp import ClientSession, ClientTimeout
            from counterpress.streaming.monitor import MonitorPublisher
            session = await self.stack.enter_async_context(ClientSession(timeout=ClientTimeout(total=5)))
            self.metric_sender = MonitorPublisher(credential, session).send
            self.telemetry_task = asyncio.create_task(self.telemetry.run(self.metric_sender))

    async def close(self):
        if self.task:
            self.task.cancel()
            try:
                await self.task
            except asyncio.CancelledError:
                pass
        if self.telemetry_task:
            self.telemetry_task.cancel()
            try:
                await self.telemetry_task
            except asyncio.CancelledError:
                pass
            await self.telemetry.flush(self.metric_sender)
        if hasattr(self, 'checkpoints'):
            await self.checkpoints.close()
        await self.stack.aclose()
