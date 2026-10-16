"""Explicit, acknowledged Azure Monitor export of fixed numeric fields only."""
from datetime import datetime, timezone
import math
import re
from counterpress.streaming.telemetry import COUNTERS

NUMBERS = (*COUNTERS, 'window_seconds', 'max_delivery_age_seconds', 'pending_seconds', 'observed_backlog')


def monitor_record(record):
    if record.get('schema') != 'counterpress_ops_v1':
        raise ValueError('Invalid metric schema')
    result = {'TimeGenerated': datetime.now(timezone.utc).isoformat(), 'schema': 'counterpress_ops_v1'}
    for name in NUMBERS:
        value = record[name]
        if type(value) not in (float, int) or not math.isfinite(value) or not 0 <= value <= 1e12:
            raise ValueError('Invalid numeric metric')
        result[name] = int(value) if name in COUNTERS or name == 'observed_backlog' else value
    return result


class MonitorPublisher:
    def __init__(self, credential, session):
        from counterpress.streaming.azure import endpoint, required
        base = endpoint('COUNTERPRESS_MONITOR_ENDPOINT', '.ingest.monitor.azure.com')
        rule = required('COUNTERPRESS_MONITOR_DCR_ID')
        if not re.fullmatch(r'dcr-[0-9a-f]{32}', rule):
            raise ValueError('Invalid monitoring rule')
        self.url = f'{base}/dataCollectionRules/{rule}/streams/Custom-CounterPressOperations?api-version=2023-01-01'
        self.credential, self.session = credential, session

    async def send(self, record):
        payload = monitor_record(record)
        token = await self.credential.get_token('https://monitor.azure.com/.default')
        async with self.session.post(self.url, json=[payload],
                headers={'Authorization': 'Bearer '+token.token}) as response:
            if response.status != 204:
                # Never read/log an error response, endpoint or token.
                raise RuntimeError('Numeric telemetry was not acknowledged')
