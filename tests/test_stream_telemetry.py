import asyncio
from datetime import datetime, timedelta, timezone
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock
import pytest
from counterpress.streaming.telemetry import StreamTelemetry, COUNTERS
from counterpress.streaming.consumer import DeliveryProcessor
from test_streaming import setup


def test_numeric_window_uses_transport_time_retains_pending_and_resets_counters(capsys):
    now = datetime(2026, 1, 1, tzinfo=timezone.utc)
    clock = [10.0]
    t = StreamTelemetry(enabled=True, clock=lambda: clock[0], utcnow=lambda: now)
    event = SimpleNamespace(enqueued_time=now-timedelta(seconds=20), sequence_number=7,
                            body=b'private body', partition_key='private match')
    t.begin(event, SimpleNamespace(last_enqueued_event_properties={'sequence_number': 10}))
    t.increment('retries');clock[0]=70
    t.emit();data=json.loads(capsys.readouterr().out)
    assert data['retries']==1 and data['pending_seconds']==60 and data['observed_backlog']==3
    assert data['max_delivery_age_seconds']==20
    assert set(data)=={'schema','window_seconds',*COUNTERS,'max_delivery_age_seconds','pending_seconds','observed_backlog'}
    assert all(isinstance(v,(float,int)) for k,v in data.items() if k!='schema')
    clock[0]=80;t.begin(event, SimpleNamespace())
    assert t.snapshot()['pending_seconds']==70  # Retry cannot reset a stalled delivery's timer.
    t.finish();data=t.snapshot()
    assert data['processed']==1 and data['retries']==0 and data['pending_seconds']==0
    with pytest.raises(ValueError):t.increment('private body')


def test_disabled_telemetry_emits_nothing(capsys):
    t=StreamTelemetry(enabled=False);t.increment('retries');t.emit()
    assert capsys.readouterr().out==''


def test_failed_publish_and_checkpoint_count_retries_without_counting_success(monkeypatch):
    s,d,e,p,pub,q=setup();t=StreamTelemetry(enabled=True)
    pub.publish.side_effect=[RuntimeError('private endpoint'),None,None]
    p.update_checkpoint.side_effect=[RuntimeError('private credential'),None]
    monkeypatch.setattr('counterpress.streaming.consumer.asyncio.sleep',AsyncMock())
    asyncio.run(DeliveryProcessor(s,pub,q,t).on_event(p,e))
    data=t.snapshot()
    assert {k:data[k] for k in COUNTERS}=={'processed':1,'rejected':0,'retries':2,'publish_failures':1,'checkpoint_failures':1,'consumer_failures':0}
    assert len(s.history('increase').records)==93


def test_quarantine_is_counted_only_after_durable_checkpoint():
    s,d,e,p,pub,q=setup();e.body=[b'bad'];t=StreamTelemetry(enabled=True)
    p.update_checkpoint.side_effect=RuntimeError('private endpoint')
    with pytest.raises(RuntimeError):asyncio.run(DeliveryProcessor(s,pub,q,t).process(p,e))
    assert t.snapshot()['rejected']==0
    p.update_checkpoint.side_effect=None
    asyncio.run(DeliveryProcessor(s,pub,q,t).process(p,e))
    assert t.snapshot()['rejected']==1
