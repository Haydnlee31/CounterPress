"""Explicit authorized producer CLI; no public ingestion HTTP endpoint."""
import argparse
import asyncio
import os
from pathlib import Path
from uuid import uuid4
from pydantic import TypeAdapter
from counterpress.api.snapshots import SCENARIOS, SnapshotService
from counterpress.domain.models import Event
from counterpress.streaming.contracts import Delivery, MAX_DELIVERY_BYTES

async def send(delivery):
    from azure.eventhub import EventData
    from azure.eventhub.aio import EventHubProducerClient
    from azure.identity.aio import AzureCliCredential, ManagedIdentityCredential
    from counterpress.streaming.azure import required
    auth = os.environ.get('COUNTERPRESS_FEED_AUTH', 'azure-cli')
    if auth not in ('azure-cli', 'managed-identity'):
        raise ValueError('Invalid producer authentication')
    credential = (AzureCliCredential() if auth == 'azure-cli' else
        ManagedIdentityCredential(client_id=required('COUNTERPRESS_FEED_CLIENT_ID')))
    async with credential:
        async with EventHubProducerClient(fully_qualified_namespace=required('COUNTERPRESS_EVENTHUB_NAMESPACE'),
                eventhub_name=required('COUNTERPRESS_EVENTHUB_NAME'), credential=credential,
                retry_total=2, logging_enable=False) as producer:
            body = delivery.model_dump_json()
            if len(body.encode()) > MAX_DELIVERY_BYTES:
                raise ValueError('Delivery exceeds the size limit')
            batch = await producer.create_batch(partition_key=delivery.match_id)
            batch.add(EventData(body))
            await producer.send_batch(batch)

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('scenario', choices=SCENARIOS)
    parser.add_argument('updates', type=Path)
    args = parser.parse_args()
    try:
        events = TypeAdapter(tuple[Event, ...]).validate_json(args.updates.read_text())
        # Only this explicit demo alias reuses authored recovery corrections.
        if args.scenario == 'stream-recovery':
            events = tuple(e.model_copy(update={'match_id': e.match_id + '-stream'}) for e in events)
        delivery = Delivery(delivery_id='delivery-' + uuid4().hex, scenario_id=args.scenario,
            match_id=events[0].match_id, events=events)
        asyncio.run(send(delivery))
        print('Delivery accepted by Event Hubs; consumer commit and notification are asynchronous.')
    except Exception:
        parser.exit(2, 'Delivery failed; check the input, private configuration and sender role.\n')

if __name__ == '__main__':
    main()
