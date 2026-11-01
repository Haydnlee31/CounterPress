"""Content-free Analyst telemetry, independent of Azure and paid model calls."""
import asyncio
import pytest
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
from opentelemetry.trace import StatusCode
from counterpress.assistant import observability as obs

@pytest.fixture
def captured(monkeypatch):
    output = InMemorySpanExporter()
    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(obs.SanitizingExporter(output)))
    monkeypatch.setattr(obs.trace, 'get_tracer', provider.get_tracer)
    yield output
    provider.shutdown()

@pytest.mark.parametrize('name', ['footie.analyst.request', 'footie.analyst.generate', 'footie.report.request', 'footie.report.generate'])
def test_outcomes_and_cache_export_without_payload(captured, name):
    @obs.traced_operation(name)
    async def operation(private_question):
        return {'status': 'complete', 'cached': True, 'reading': 'private response'}
    assert asyncio.run(operation('private question'))['reading'] == 'private response'
    span, = captured.get_finished_spans()
    assert span.name == name
    assert span.parent is None
    assert span.attributes['footie.outcome'] == 'complete'
    assert span.attributes['footie.cached'] is True
    assert 'private' not in str(span.attributes)

@pytest.mark.parametrize('failure', ['caught', 'raised', 'cancelled'])
def test_failures_are_visible_without_exception_content(captured, failure):
    @obs.traced_operation('footie.report.generate')
    async def operation():
        if failure == 'caught': return None
        if failure == 'cancelled': raise asyncio.CancelledError('secret')
        raise RuntimeError('secret')
    if failure == 'caught': assert asyncio.run(operation()) is None
    else:
        with pytest.raises((RuntimeError, asyncio.CancelledError)): asyncio.run(operation())
    span, = captured.get_finished_spans()
    assert span.status.status_code == StatusCode.ERROR
    assert not span.events
    assert span.status.description is None
    assert 'secret' not in str(span.attributes)

@pytest.mark.parametrize('role', ['players', 'control', 'chance', 'defence', 'footie'])
def test_existing_analyst_stages_survive_allowlist(captured, role):
    with obs.trace.get_tracer(__name__).start_as_current_span('footie.analyst.live.' + role) as span:
        span.set_attribute('footie.role', role)
        span.set_attribute('footie.snapshot_id', 'private-match')
        span.set_attribute('gen_ai.usage.input_tokens', 42)
        span.set_attribute('gen_ai.request.model', 'private-deployment')
    span, = captured.get_finished_spans()
    assert span.attributes['gen_ai.agent.id'] == 'footie-analyst-' + role
    assert span.attributes['gen_ai.usage.input_tokens'] == 42
    assert 'private' not in str(span.attributes)

def test_background_job_has_independent_visible_root(captured):
    @obs.traced_operation('footie.report.generate')
    async def job():
        with obs.agent_span('footie.report.draft'): pass
        return {'status': 'complete'}
    @obs.traced_operation('footie.report.request')
    async def request():
        await asyncio.create_task(job())
        return {'status': 'pending'}
    asyncio.run(request())
    spans = {s.name: s for s in captured.get_finished_spans()}
    assert spans['footie.report.generate'].parent is None
    assert spans['footie.report.request'].parent is None
    assert spans['footie.report.draft'].parent.span_id == spans['footie.report.generate'].context.span_id

@pytest.mark.parametrize('stage', ['draft', 'review'])
def test_report_model_stage_exports_usage_without_changing_output(captured, monkeypatch, stage):
    from counterpress.analyst.report import report_request
    async def request(*args, **kwargs):
        return 'private model response', {'prompt_tokens': 123, 'completion_tokens': 45}
    monkeypatch.setattr('counterpress.assistant.planner.structured_request', request)
    raw, usage = asyncio.run(report_request(stage))
    assert raw == 'private model response'
    span, = captured.get_finished_spans()
    assert span.name == 'footie.report.' + stage
    assert span.attributes['gen_ai.usage.input_tokens'] == 123
    assert span.attributes['gen_ai.usage.output_tokens'] == 45
    assert 'private' not in str(span.attributes)
