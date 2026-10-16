"""Commit -> notify -> checkpoint. Never checkpoint past a transient failure."""
import asyncio
import hashlib
import logging
from pydantic import ValidationError
from counterpress.api.snapshots import SCENARIOS, SnapshotService
from counterpress.streaming.contracts import Delivery, MAX_DELIVERY_BYTES, notice

from counterpress.streaming.telemetry import StreamTelemetry

log = logging.getLogger(__name__)

class DeliveryProcessor:
    def __init__(self, service: SnapshotService, publisher, quarantine, telemetry=None):
        self.service, self.publisher, self.quarantine = service, publisher, quarantine
        self.telemetry = telemetry or StreamTelemetry()

    async def process(self, partition, event):
        self.telemetry.begin(event, partition)
        # No raw bodies, SDK exceptions, endpoint URLs or tokens in logs.
        try:
            raw = b''.join(event.body)
            if len(raw) > MAX_DELIVERY_BYTES:
                raise ValueError('oversize')
            delivery = Delivery.model_validate_json(raw)
            partition_key = event.partition_key
            if isinstance(partition_key, bytes):
                partition_key = partition_key.decode('utf-8')
            if delivery.scenario_id not in SCENARIOS or partition_key != delivery.match_id:
                raise ValueError('invalid routing')
            history = await asyncio.to_thread(self.service.history, delivery.scenario_id)
            if history.fixture.match_id != delivery.match_id:
                raise ValueError('wrong match')
            history = await asyncio.to_thread(self.service.ingest, delivery.scenario_id, delivery.events)
        except (ValueError, KeyError, ValidationError, UnicodeError):
            # Durable quarantine before acknowledging a permanently invalid input.
            # Store bytes only within the limit; oversized records retain a digest.
            raw = locals().get('raw', b'')
            await self.quarantine(partition.partition_id, event.sequence_number,
                raw if len(raw) <= MAX_DELIVERY_BYTES else b'', hashlib.sha256(raw).hexdigest())
            await self.checkpoint(partition, event)
            self.telemetry.finish(rejected=True)
            log.warning('stream_delivery_rejected')
            return
        # Replay after a commit/send/checkpoint failure re-emits the current revision
        # heads even if all source events were already committed. No lost outbox gap.
        try:
            await self.publisher.publish(notice(delivery.scenario_id, history))
        except Exception:
            self.telemetry.increment('publish_failures')
            raise
        await self.checkpoint(partition, event)
        self.telemetry.finish()
        log.info('stream_delivery_checkpointed')

    async def checkpoint(self, partition, event):
        try:
            await partition.update_checkpoint(event)
        except Exception:
            self.telemetry.increment('checkpoint_failures')
            raise

    async def on_event(self, partition, event):
        if event is None:
            return
        delay = 1
        while True:
            try:
                await self.process(partition, event)
                return
            except asyncio.CancelledError:
                raise
            except Exception:
                # Do not return to the SDK and allow a later event to checkpoint
                # over this failed delivery. Restart replays from the durable cursor.
                self.telemetry.increment('retries')
                log.warning('stream_delivery_retry')
                await asyncio.sleep(delay)
                delay = min(delay * 2, 30)
