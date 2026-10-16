"""Explicit live check inside the configured app. Uses only the isolated stream demo."""
import argparse
import asyncio
import os
from pathlib import Path
import json
from uuid import uuid4
from pydantic import TypeAdapter
from counterpress.domain.models import Event
from counterpress.api.snapshots import SnapshotService
from counterpress.storage import configured_store
from counterpress.streaming.contracts import Delivery, RevisionNotice
from counterpress.streaming.send import send

async def verify(exercise=False):
    from azure.identity.aio import ManagedIdentityCredential
    from azure.messaging.webpubsubservice.aio import WebPubSubServiceClient
    from azure.eventhub.extensions.checkpointstoreblobaio import BlobCheckpointStore
    import aiohttp
    service=SnapshotService(Path(os.environ['COUNTERPRESS_FIXTURE_DIR']),configured_store(':memory:'))
    history=await asyncio.to_thread(service.history,'stream-recovery')
    if exercise:
        records=TypeAdapter(tuple[Event,...]).validate_json((Path(os.environ['COUNTERPRESS_FIXTURE_DIR'])/'faults/recovery_corrections.json').read_text())
        records=tuple(e.model_copy(update={'match_id':history.fixture.match_id}) for e in records)
        async with ManagedIdentityCredential(client_id=os.environ['COUNTERPRESS_STREAM_CLIENT_ID']) as credential:
            checkpoints=BlobCheckpointStore(blob_account_url=os.environ['COUNTERPRESS_CHECKPOINT_ENDPOINT'],container_name='eventhub-checkpoints',credential=credential)
            ns,hub=os.environ['COUNTERPRESS_EVENTHUB_NAMESPACE'],os.environ['COUNTERPRESS_EVENTHUB_NAME']
            prior=await checkpoints.list_checkpoints(ns,hub,'$Default')
            previous=max((int(p['sequence_number']) for p in prior),default=-1)
            async with WebPubSubServiceClient(os.environ['COUNTERPRESS_PUBSUB_ENDPOINT'],hub='counterpress',credential=credential) as pubsub:
                token=await pubsub.get_client_access_token(groups=['scenario.stream-recovery'],roles=[],minutes_to_expire=5)
                async with aiohttp.ClientSession() as session:
                    async with session.ws_connect(token['url']) as socket:
                        for _ in range(2):
                            delivery=Delivery(delivery_id='check-'+uuid4().hex,scenario_id='stream-recovery',match_id=history.fixture.match_id,events=records)
                            await send(delivery)
                            message=await asyncio.wait_for(socket.receive(), timeout=120)
                            assert message.type==aiohttp.WSMsgType.TEXT
                            n=RevisionNotice.model_validate_json(message.data)
                            assert n.scenario_id=='stream-recovery' and n.history_version==93
                            assert n.revisions[0].revision==4 and n.revisions[0].operation=='create'
                for _ in range(30):
                    current=await checkpoints.list_checkpoints(ns,hub,'$Default')
                    if max((int(p['sequence_number']) for p in current),default=-1)>=previous+2:break
                    await asyncio.sleep(1)
                else:raise AssertionError('checkpoint did not advance')
            await checkpoints.close()
        print('PASS: Event Hubs -> Cosmos -> Web PubSub, duplicate replay, durable Blob checkpoint',flush=True)
    for at,count,revision in [(780000,4,1),(785000,3,2),(790000,None,3),(795000,2,4)]:
        s=await asyncio.to_thread(service.snapshot,'stream-recovery',at)
        assert s.lifecycle.revision==revision
        assert (s.insight.facts.current_count if s.insight else None)==count
    assert len(service.history('stream-recovery').records)==93
    assert service.evidence('stream-recovery',1,795000).packet.current.value==4
    assert service.snapshot('increase',780000).insight.facts.current_count==4
    print('PASS: historical 4/3/withdrawn/2, frozen evidence, original scenario unchanged',flush=True)

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--exercise',action='store_true');args=p.parse_args()
    try:asyncio.run(verify(args.exercise))
    except Exception:p.exit(2,'Live streaming check failed; inspect private service diagnostics.\n')

if __name__=='__main__':main()
