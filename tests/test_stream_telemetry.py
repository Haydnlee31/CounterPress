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
    assert {k:data[k] for k in COUNTERS}=={'processed':1,'rejected':0,'retries':2,'publish_failures':1,'checkpoint_failures':1,'consumer_failures':0,'export_failures':0}
    assert len(s.history('increase').records)==93


def test_quarantine_is_counted_only_after_durable_checkpoint():
    s,d,e,p,pub,q=setup();e.body=[b'bad'];t=StreamTelemetry(enabled=True)
    p.update_checkpoint.side_effect=RuntimeError('private endpoint')
    with pytest.raises(RuntimeError):asyncio.run(DeliveryProcessor(s,pub,q,t).process(p,e))
    assert t.snapshot()['rejected']==0
    p.update_checkpoint.side_effect=None
    asyncio.run(DeliveryProcessor(s,pub,q,t).process(p,e))
    assert t.snapshot()['rejected']==1


def test_export_failure_is_bounded_sanitized_and_does_not_break_processing(capsys,caplog):
    t=StreamTelemetry(enabled=True)
    sender=AsyncMock(side_effect=RuntimeError('private-token-and-endpoint'))
    asyncio.run(t.flush(sender))
    assert t.snapshot()['export_failures']==1
    assert 'private-token-and-endpoint' not in capsys.readouterr().out+caplog.text
    assert 'stream_metrics_export_failed' in caplog.text


def test_monitor_wire_record_has_no_free_text_or_unapproved_fields():
    from counterpress.streaming.monitor import monitor_record
    record=StreamTelemetry(enabled=True).snapshot()
    result=monitor_record(record|{'unapproved':'private payload'})
    assert 'unapproved' not in result
    assert set(result)==set(record)|{'TimeGenerated'}
    with pytest.raises(ValueError):monitor_record(record|{'processed':'private token'})
    with pytest.raises(ValueError):monitor_record(record|{'pending_seconds':float('nan')})


def test_monitor_accepts_only_acknowledged_upload_and_uses_correct_audience(monkeypatch):
    from counterpress.streaming.monitor import MonitorPublisher
    for k,v in {'COUNTERPRESS_MONITOR_ENDPOINT':'https://example.ingest.monitor.azure.com','COUNTERPRESS_MONITOR_DCR_ID':'dcr-'+'a'*32}.items():monkeypatch.setenv(k,v)
    status=[204];sent=[]
    class Response:
        async def __aenter__(self):return SimpleNamespace(status=status[0])
        async def __aexit__(self,*args):pass
    class Session:
        def post(self,url,**kwargs):sent.append((url,kwargs));return Response()
    credential=SimpleNamespace(get_token=AsyncMock(return_value=SimpleNamespace(token='test-only-token')))
    publisher=MonitorPublisher(credential,Session())
    asyncio.run(publisher.send(StreamTelemetry().snapshot()))
    credential.get_token.assert_awaited_with('https://monitor.azure.com/.default')
    assert sent[0][1]['headers']=={'Authorization':'Bearer test-only-token'}
    assert len(sent[0][1]['json'])==1
    assert sent[0][0].endswith('/streams/Custom-CounterPressOperations?api-version=2023-01-01')
    status[0]=403
    with pytest.raises(RuntimeError,match='not acknowledged'):asyncio.run(publisher.send(StreamTelemetry().snapshot()))
