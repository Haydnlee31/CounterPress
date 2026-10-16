"""Bounded numeric telemetry; never accept event bodies, identifiers or exceptions."""
import asyncio
from datetime import datetime, timezone
import json
import math
import os
import sys
from time import monotonic

COUNTERS = ('processed', 'rejected', 'retries', 'publish_failures',
            'checkpoint_failures', 'consumer_failures')


class StreamTelemetry:
    def __init__(self, enabled=None, clock=monotonic, utcnow=None):
        self.enabled = (os.environ.get('COUNTERPRESS_TELEMETRY') == 'on') if enabled is None else enabled
        self.clock = clock
        self.utcnow = utcnow or (lambda: datetime.now(timezone.utc))
        self.started = clock()
        self.counts = dict.fromkeys(COUNTERS, 0)
        self.pending_since = None
        self.pending_enqueued = None
        self.max_delivery_age = 0.0
        self.backlog = 0

    def increment(self, name):
        if name not in self.counts:
            raise ValueError('Unknown operational counter')
        self.counts[name] += 1

    def begin(self, event, partition):
        if self.pending_since is None:
            self.pending_since = self.clock()
            value = getattr(event, 'enqueued_time', None)
            self.pending_enqueued = value if isinstance(value, datetime) and value.tzinfo else None
        latest = getattr(partition, 'last_enqueued_event_properties', {}) or {}
        sequence = latest.get('sequence_number')
        current = getattr(event, 'sequence_number', None)
        if isinstance(sequence, int) and isinstance(current, int):
            self.backlog = max(0, sequence - current)

    def finish(self, rejected=False):
        self.increment('rejected' if rejected else 'processed')
        self.max_delivery_age = max(self.max_delivery_age, self.delivery_age())
        self.pending_since = self.pending_enqueued = None

    def delivery_age(self):
        return max(0.0, (self.utcnow() - self.pending_enqueued).total_seconds()) if self.pending_enqueued else 0.0

    def snapshot(self):
        now = self.clock()
        result = {'schema': 'counterpress_ops_v1', 'window_seconds': max(0, now-self.started), **self.counts,
                  'max_delivery_age_seconds': max(self.max_delivery_age, self.delivery_age()),
                  'pending_seconds': max(0, now-self.pending_since) if self.pending_since is not None else 0,
                  'observed_backlog': self.backlog}
        # Clamp numeric values; the wire shape cannot carry free text or NaN.
        result = {k: (min(1e12, round(v, 3)) if math.isfinite(v) else 0)
                  if isinstance(v, (int, float)) else v for k, v in result.items()}
        self.counts = dict.fromkeys(COUNTERS, 0)
        self.max_delivery_age = 0.0
        self.started = now
        return result

    def emit(self):
        if self.enabled:
            print(json.dumps(self.snapshot(), separators=(',', ':'), allow_nan=False), file=sys.stdout, flush=True)

    async def run(self):
        while True:
            self.emit()
            await asyncio.sleep(60)
