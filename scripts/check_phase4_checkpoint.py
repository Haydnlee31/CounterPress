#!/usr/bin/env python3
"""One read-only durable checkpoint check inside the isolated Phase4 Container App.

No receive loop, lease claim, checkpoint update, event send, reset or inference.
The four-field output contains no resource names, endpoints or credentials.
Exit 0: caught up; 1: lagging; 2: configuration/read failure.
"""
import asyncio
from contextlib import AsyncExitStack
import json
import logging
import os
import re

EMPTY = {'checkpoint_sequence':-1,'last_enqueued_sequence':-1,'partition_count':0,'caught_up':False}


def summarize(partition_ids, properties, checkpoints):
    # The reviewed test hub has exactly one partition. Do not turn aggregates
    # across unexpected partitions into a misleading caught-up certificate.
    if len(partition_ids)!=1 or len(properties)!=1:
        raise ValueError('Unexpected partition count')
    partition = partition_ids[0]
    if properties[0].get('id') != partition:
        raise ValueError('Partition response mismatch')
    last = properties[0].get('last_enqueued_sequence_number')
    if type(last) is not int or last < -1:
        raise ValueError('Invalid last sequence')
    rows = list(checkpoints)
    if any(row.get('partition_id')!=partition for row in rows) or len(rows)>1:
        raise ValueError('Checkpoint identity mismatch')
    checkpoint = rows[0].get('sequence_number') if rows else -1
    if type(checkpoint) is not int or not -1<=checkpoint<=last:
        raise ValueError('Invalid checkpoint sequence')
    return {'checkpoint_sequence':checkpoint,'last_enqueued_sequence':last,
            'partition_count':1,'caught_up':checkpoint==last}


async def inspect_once():
    # This must run before importing/constructing any credential or SDK client.
    from counterpress.api.phase4 import validate_environment
    validate_environment()
    from counterpress.streaming.azure import endpoint, required
    namespace = required('COUNTERPRESS_EVENTHUB_NAMESPACE')
    if not re.fullmatch(r'[a-zA-Z0-9-]+\.servicebus\.windows\.net',namespace):
        raise ValueError('Invalid isolated namespace')
    client_id = required('COUNTERPRESS_STREAM_CLIENT_ID')
    if not re.fullmatch(r'[a-fA-F0-9-]{36}',client_id) or any(
        os.environ.get(key)!=client_id for key in ('COUNTERPRESS_COSMOS_CLIENT_ID','COUNTERPRESS_FEED_CLIENT_ID')):
        raise ValueError('Isolated identity mismatch')
    blob = endpoint('COUNTERPRESS_CHECKPOINT_ENDPOINT','.blob.core.windows.net')
    from azure.identity.aio import ManagedIdentityCredential
    from azure.eventhub.aio import EventHubConsumerClient
    from azure.eventhub.extensions.checkpointstoreblobaio import BlobCheckpointStore
    # Suppress SDK exception/log destinations. Errors produce the fixed numeric
    # unavailable result in main, never a raw URL, token, identity or traceback.
    logging.getLogger('azure').handlers=[logging.NullHandler()]
    logging.getLogger('azure').propagate=False
    async with AsyncExitStack() as stack:
        credential = await stack.enter_async_context(ManagedIdentityCredential(
            client_id=client_id,connection_timeout=5,read_timeout=5,retry_total=0))
        checkpoint_store = BlobCheckpointStore(blob_account_url=blob,
            container_name='eventhub-checkpoints-phase4',credential=credential,
            retry_total=0,connection_timeout=5,read_timeout=5,logging_enable=False)
        stack.push_async_callback(checkpoint_store.close)
        client = await stack.enter_async_context(EventHubConsumerClient(
            fully_qualified_namespace=namespace,eventhub_name='deliveries-phase4',
            consumer_group='$Default',credential=credential,retry_total=0,
            auth_timeout=5,connection_timeout=5,logging_enable=False))
        # asyncio bounds management operations even when an SDK retry setting
        # does not cover a particular transport. No streaming receive is started.
        async with asyncio.timeout(20):
            ids = await client.get_partition_ids()
            if len(ids)!=1:raise ValueError('Unexpected partition count')
            properties = [await client.get_partition_properties(ids[0])]
            checkpoints = await checkpoint_store.list_checkpoints(namespace,'deliveries-phase4','$Default',timeout=5)
            return summarize(ids,properties,checkpoints)


def main():
    try:
        # Outer bound includes credential/client cleanup as well as reads.
        async def bounded():
            async with asyncio.timeout(30):return await inspect_once()
        result=asyncio.run(bounded())
    except Exception:
        print(json.dumps(EMPTY),flush=True)
        return 2
    print(json.dumps(result),flush=True)
    return 0 if result['caught_up'] else 1


if __name__=='__main__':raise SystemExit(main())
