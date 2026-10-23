import json
from unittest.mock import Mock

import pytest
from azure.monitor.opentelemetry.exporter import AzureMonitorTraceExporter, _utils
from azure.monitor.opentelemetry.exporter.export._base import ExportResult
from opentelemetry.trace import SpanContext, TraceFlags, SpanKind
from counterpress.assistant.observability import ContentFreeAzureMonitorTraceExporter

from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import ReadableSpan
from opentelemetry.sdk.trace.export import SpanExportResult
from opentelemetry.trace import Status, StatusCode

from counterpress.assistant.observability import SanitizingExporter, safe_attributes, sanitized_span


def test_exporter_removes_content_private_endpoints_and_exception_details():
    span = ReadableSpan(
        'footie.specialist', attributes={
            'footie.role': 'career', 'footie.provider_requests': 1,
            'gen_ai.usage.input_tokens': 111, 'footie.operation': 'compare',
            'gen_ai.input.messages': 'private question', 'server.address': 'private.azure.com',
            'exception.message': 'secret-token', 'footie.status': 'invented-secret',
            'footie.request_id': '12345678123456781234567812345678',
        }, resource=Resource({'host.name': 'private-host', 'secret': 'secret-token'}),
        status=Status(StatusCode.ERROR, 'secret-token'), events=('secret-event',),
    )
    clean = sanitized_span(span)
    assert clean.attributes == {
        'footie.role': 'career', 'footie.provider_requests': 1,
        'gen_ai.usage.input_tokens': 111, 'footie.operation': 'compare',
        'footie.request_id': '12345678123456781234567812345678',
        'gen_ai.agent.id': 'footie-career-analyst', 'gen_ai.agent.name': 'footie-career-analyst',
    }
    assert clean.status.status_code == StatusCode.ERROR and clean.status.description is None
    assert not clean.events and not clean.links
    assert dict(clean.resource.attributes) == {'service.name': 'footie-agents'}


def test_numeric_and_enum_attributes_cannot_smuggle_text():
    assert safe_attributes({'footie.provider_requests': 'https://private',
                            'footie.tool_calls': float('nan'),
                            'footie.claim_count': -1, 'footie.cached': 'secret',
                            'gen_ai.agent.id': 'private', 'footie.request_id': 'user@example.com'}) == {}


def test_automatic_sdk_spans_are_not_exported():
    class Capture:
        def export(self, spans):
            self.spans = spans
            return SpanExportResult.SUCCESS
    capture = Capture()
    exporter = SanitizingExporter(capture)
    exporter.export([ReadableSpan('chat private-model-name'), ReadableSpan('footie.route')])
    assert len(capture.spans) == 1
    assert capture.spans[0].name == 'footie.route'
    assert capture.spans[0].attributes['gen_ai.agent.id'] == 'footie-orchestrator'


def test_export_failures_do_not_raise_or_log_payload(caplog):
    class Broken:
        def export(self, spans):
            raise RuntimeError('private-key private-endpoint')
    result = SanitizingExporter(Broken()).export([ReadableSpan('footie.route')])
    assert result == SpanExportResult.FAILURE
    assert 'private-key' not in caplog.text and 'private-endpoint' not in caplog.text
    assert 'agent_trace_export_failed' in caplog.text


def test_parent_child_correlation_and_failure_status_without_exception_content(monkeypatch):
    import pytest
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import SimpleSpanProcessor
    from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
    from counterpress.assistant import observability as module
    exporter = InMemorySpanExporter()
    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(SanitizingExporter(exporter)))
    monkeypatch.setattr(module.trace, 'get_tracer', lambda name: provider.get_tracer(name))
    with module.agent_span('footie.request'):
        with pytest.raises(RuntimeError):
            with module.agent_span('footie.specialist', role='match'):
                raise RuntimeError('private prompt or provider endpoint')
    child, parent = exporter.get_finished_spans()
    assert child.context.trace_id == parent.context.trace_id
    assert child.parent.span_id == parent.context.span_id
    assert child.attributes['gen_ai.agent.id'] == 'footie-match-analyst'
    assert parent.attributes['gen_ai.agent.id'] == 'footie-orchestrator'
    assert child.status.status_code == StatusCode.ERROR
    assert child.events == () and child.status.description is None
    provider.shutdown()


def test_tracing_disabled_by_default_and_missing_configuration_does_not_break_api(monkeypatch, caplog):
    from counterpress.assistant import observability as module
    monkeypatch.delenv('COUNTERPRESS_AGENT_TRACING', raising=False)
    assert module.configure_agent_tracing() == 'off'
    monkeypatch.setenv('COUNTERPRESS_AGENT_TRACING', 'azure')
    monkeypatch.delenv('APPLICATIONINSIGHTS_CONNECTION_STRING', raising=False)
    assert module.configure_agent_tracing() == 'unavailable'
    assert 'agent_trace_configuration_failed' in caplog.text


# Exercise actual Azure conversion; transmission is always mocked.
CANARY = 'PRIVATE-HOST-QUESTION-TOKEN-CANARY'


def _azure_test_span(kind=SpanKind.INTERNAL, *, child=False):
    return ReadableSpan(
        name='footie.specialist' if child else 'footie.request',
        context=SpanContext(1, 3 if child else 2, False, TraceFlags(1)),
        parent=SpanContext(1, 2, False, TraceFlags(1)) if child else None,
        kind=kind, start_time=1000000000, end_time=2000000000,
        attributes={'footie.role': 'match' if child else 'orchestrator',
                    'footie.provider_requests': 1,
                    'gen_ai.input.messages': CANARY, 'server.address': CANARY},
        resource=Resource({'service.name': CANARY, 'host.name': CANARY}),
        status=Status(StatusCode.ERROR, CANARY),
        events=(), links=(),
    )


def _azure_test_exporter(cls=ContentFreeAzureMonitorTraceExporter):
    # No initialization, credentials, background threads, HTTP, or cloud calls.
    result = object.__new__(cls)
    result._instrumentation_key = '11111111-1111-4111-8111-111111111111'
    result._transmit = Mock(return_value=ExportResult.SUCCESS)
    result._handle_transmit_from_storage = Mock()
    return result


@pytest.mark.parametrize('kind', [SpanKind.INTERNAL, SpanKind.SERVER, SpanKind.CLIENT])
def test_real_sdk_conversion_strips_host_and_user_content_preserves_correlation(monkeypatch, kind):
    original = _utils._populate_part_a_fields
    def inject(resource):
        tags = original(resource)
        tags.update({'ai.device.id': CANARY, 'ai.cloud.roleInstance': CANARY,
                     'ai.internal.nodeName': CANARY, 'future.sdk.private': CANARY})
        return tags
    monkeypatch.setattr(_utils, '_populate_part_a_fields', inject)
    original_envelope = _azure_test_exporter(AzureMonitorTraceExporter)._span_to_envelope(sanitized_span(_azure_test_span(kind)))
    assert CANARY in json.dumps(original_envelope.as_dict())  # reproduces SDK leak
    instance = _azure_test_exporter()
    result = SanitizingExporter(instance).export([_azure_test_span(kind), _azure_test_span(kind, child=True)])
    assert result == SpanExportResult.SUCCESS
    envelopes = instance._transmit.call_args.args[0]
    assert len(envelopes) == 2  # no _OTELRESOURCE_ metric
    assert CANARY not in json.dumps([envelope.as_dict() for envelope in envelopes])
    parent, child = envelopes
    assert parent.tags == {'ai.cloud.role': 'footie-agents', 'ai.operation.id': '0'*31+'1',
                           'ai.operation.name': 'footie.request', 'ai.operation.parentId': ''}
    assert child.tags['ai.operation.parentId'] == parent.data.base_data.id
    assert child.tags['ai.operation.id'] == parent.tags['ai.operation.id']
    assert child.data.base_data.properties == {
        'footie.role': 'match', 'footie.provider_requests': '1',
        'gen_ai.agent.id': 'footie-match-analyst', 'gen_ai.agent.name': 'footie-match-analyst'}
    for envelope in envelopes:
        for field in ('data', 'target', 'url', 'source'):
            assert not getattr(envelope.data.base_data, field, None)
        assert envelope.data.base_data.measurements == {}


def test_resource_metric_and_event_bypass_disabled_even_without_env_flag(monkeypatch):
    monkeypatch.delenv('APPLICATIONINSIGHTS_OPENTELEMETRY_RESOURCE_METRIC_DISABLED', raising=False)
    instance = _azure_test_exporter()
    instance._get_otel_resource_envelope = Mock(side_effect=AssertionError('must not execute'))
    assert not instance._should_collect_otel_resource_metric()
    assert instance._span_events_to_envelopes(Mock(events=[CANARY])) == []
    assert instance.export([sanitized_span(_azure_test_span())]) == SpanExportResult.SUCCESS
    instance._get_otel_resource_envelope.assert_not_called()
    assert len(instance._transmit.call_args.args[0]) == 1


def test_foundry_discovers_trace_without_content_or_hidden_parent_and_counts_usage_once(monkeypatch):
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import SimpleSpanProcessor
    from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
    from counterpress.assistant import observability as module
    exporter = InMemorySpanExporter()
    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(SanitizingExporter(exporter)))
    tracer = provider.get_tracer('test')
    monkeypatch.setattr(module.trace, 'get_tracer', lambda name: tracer)
    with tracer.start_as_current_span('unexported-http-parent') as upstream:
        with module.agent_span('footie.request', attributes={
                'footie.workflow': 'multiagent', 'gen_ai.usage.input_tokens': 100,
                'gen_ai.usage.output_tokens': 20}) as root:
            with module.agent_span('footie.specialist', role='career', attributes={
                    'gen_ai.usage.input_tokens': 100, 'gen_ai.usage.output_tokens': 20}):
                pass
        assert root.get_span_context().trace_id != upstream.get_span_context().trace_id
    child, root = exporter.get_finished_spans()
    assert root.kind == SpanKind.SERVER and root.parent is None
    assert child.parent.span_id == root.context.span_id
    assert all(s.attributes['gen_ai.provider.name'] == 'azure.ai.openai' for s in (root, child))
    assert sum(s.attributes.get('gen_ai.usage.input_tokens', 0) for s in (root, child)) == 100
    assert sum(s.attributes.get('gen_ai.usage.output_tokens', 0) for s in (root, child)) == 20
    instance = _azure_test_exporter()
    envelope = instance._span_to_envelope(root)
    assert envelope.data.base_type == 'RequestData'
    assert envelope.tags['ai.operation.parentId'] == ''
    assert CANARY not in json.dumps(envelope.as_dict())
    provider.shutdown()
