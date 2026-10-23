"""Opt-in, content-free agent traces for the Foundry-linked App Insights resource.

Only this exporter's allowlisted spans leave the process. We deliberately do not
install HTTP, FastAPI or logging auto-instrumentation: their URLs, payloads and
exceptions can contain user content or private infrastructure metadata.
"""
from contextlib import contextmanager
import logging
import math
import os
import re

from azure.monitor.opentelemetry.exporter import AzureMonitorTraceExporter
from opentelemetry import trace
from opentelemetry.trace import Status, StatusCode

LOG = logging.getLogger(__name__)
AGENT_IDS = {
    'orchestrator': 'footie-orchestrator',
    'match': 'footie-match-analyst',
    'career': 'footie-career-analyst',
}
_NAMES = {'footie.request', 'footie.route', 'footie.query', 'footie.story', 'footie.specialist', 'footie.synthesize',
          'footie.tool', 'footie.validate', 'footie.monitoring_check'}
_NUMERIC = {'footie.provider_requests', 'footie.tool_calls', 'footie.specialist_count',
            'footie.claim_count', 'gen_ai.usage.input_tokens', 'gen_ai.usage.output_tokens'}
_BOOL = {'footie.cached', 'footie.fallback', 'footie.partial'}
_ENUM = {
    'footie.role': set(AGENT_IDS),
    'footie.operation': {'stats', 'compare', 'recent', 'seasons', 'club_leaders',
                         'match', 'unsupported', 'clarify', 'compound'},
    'footie.status': {'ok', 'partial', 'unsupported', 'clarify', 'error', 'fallback'},
    'footie.workflow': {'multiagent', 'agent', 'structured_lookup'},
    'gen_ai.operation.name': {'invoke_agent', 'chat', 'execute_tool'},
    'gen_ai.provider.name': {'openai', 'azure.ai.openai'},
}
_provider = None
_credential = None


def safe_attributes(attributes):
    """Unknown attributes and arbitrary text are never exported, even on errors."""
    clean = {}
    for key, value in (attributes or {}).items():
        if key in _NUMERIC and type(value) in (int, float) and math.isfinite(value) and 0 <= value <= 10**9:
            clean[key] = value
        elif key in _BOOL and type(value) is bool:
            clean[key] = value
        elif key in _ENUM and isinstance(value, str) and value in _ENUM[key]:
            clean[key] = value
        elif key == 'footie.request_id' and isinstance(value, str) and re.fullmatch(r'[a-f0-9-]{16,36}', value):
            clean[key] = value
        elif key == 'gen_ai.agent.id' and value in AGENT_IDS.values():
            clean[key] = value
    return clean


def sanitized_span(span):
    """Return a detached allowlisted span; never mutate a shared SDK span."""
    from opentelemetry.sdk.resources import Resource
    from opentelemetry.sdk.trace import ReadableSpan
    attributes = safe_attributes(span.attributes)
    role = attributes.get('footie.role', 'orchestrator')
    attributes.setdefault('gen_ai.agent.id', AGENT_IDS[role])
    attributes['gen_ai.agent.name'] = attributes['gen_ai.agent.id']
    name = span.name if span.name in _NAMES else 'footie.operation'
    return ReadableSpan(
        name=name, context=span.context, parent=span.parent, kind=span.kind,
        attributes=attributes, events=(), links=(),
        status=Status(span.status.status_code), start_time=span.start_time,
        end_time=span.end_time, resource=Resource({'service.name': 'footie-agents'}),
    )


class ContentFreeAzureMonitorTraceExporter(AzureMonitorTraceExporter):
    """Final envelope boundary for the Azure exporter version pinned in uv.lock.

    Azure has no public envelope processor. Its conversion adds hostname tags
    after span sanitization and can emit an independent resource metric. Retest
    these private conversion hooks against the actual SDK on every upgrade.
    """

    def _should_collect_otel_resource_metric(self):
        return False

    def _span_events_to_envelopes(self, span):
        return []

    def _span_to_envelope(self, span):
        clean = sanitized_span(span)
        envelope = super()._span_to_envelope(clean)
        # Reconstruct rather than retain tags synthesized from the host by Azure.
        envelope.tags = {
            'ai.cloud.role': 'footie-agents',
            'ai.operation.id': f'{clean.context.trace_id:032x}',
            'ai.operation.name': clean.name,
        }
        if clean.parent and clean.parent.span_id:
            envelope.tags['ai.operation.parentId'] = f'{clean.parent.span_id:016x}'
        data = envelope.data.base_data
        data.name = clean.name
        # Azure custom dimensions are strings. Rebuild only approved properties.
        data.properties = {key: str(value) for key, value in clean.attributes.items()}
        data.measurements = {}
        for field in ('data', 'target', 'url', 'source'):
            if hasattr(data, field):
                setattr(data, field, None)
        return envelope


class SanitizingExporter:
    """Defense in depth even if a dependency enables sensitive instrumentation."""

    def __init__(self, delegate):
        self.delegate = delegate

    def export(self, spans):
        from opentelemetry.sdk.trace.export import SpanExportResult
        # Only explicit Footie operations are collected. SDK automatic spans can
        # contain arbitrary names and are excluded, rather than redacted later.
        safe = tuple(sanitized_span(s) for s in spans if s.name in _NAMES)
        if not safe:
            return SpanExportResult.SUCCESS
        try:
            result = self.delegate.export(safe)
            if result != SpanExportResult.SUCCESS:
                LOG.warning('agent_trace_export_failed')
            return result
        except Exception:
            LOG.warning('agent_trace_export_failed')
            return SpanExportResult.FAILURE

    def shutdown(self):
        self.delegate.shutdown()

    def force_flush(self, timeout_millis=30000):
        return self.delegate.force_flush(timeout_millis)


def configure_agent_tracing():
    """Called once at process startup. Failure must not break football queries.

    Returns a fixed state string for sanitized diagnostics. No credential or
    resource identifiers appear in error messages.
    """
    global _provider, _credential
    if os.environ.get('COUNTERPRESS_AGENT_TRACING', 'off') != 'azure':
        return 'off'
    if _provider is not None:
        return 'enabled'
    try:
        connection = os.environ['APPLICATIONINSIGHTS_CONNECTION_STRING']
        client_id = os.environ['COUNTERPRESS_AGENT_TRACING_CLIENT_ID']
        ratio = float(os.environ.get('COUNTERPRESS_AGENT_TRACE_SAMPLE_RATIO', '1.0'))
        if not connection or not re.fullmatch(r'[a-fA-F0-9-]{36}', client_id) or not 0 <= ratio <= 1:
            raise ValueError('Invalid tracing settings')
        # Disable SDK background telemetry/configuration channels. Only our
        # allowlisted traces are exported; no local failed-export disk cache.
        for key in ('APPLICATIONINSIGHTS_STATSBEAT_DISABLED_ALL',
                    'APPLICATIONINSIGHTS_SDKSTATS_DISABLED',
                    'APPLICATIONINSIGHTS_CONTROLPLANE_DISABLED',
                    'APPLICATIONINSIGHTS_OPENTELEMETRY_RESOURCE_METRIC_DISABLED'):
            os.environ[key] = 'true'
        from azure.identity import ManagedIdentityCredential
        from opentelemetry.sdk.resources import Resource
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.export import BatchSpanProcessor
        from opentelemetry.sdk.trace.sampling import ParentBased, TraceIdRatioBased
        # Exporter logs can contain private destinations; emit our fixed health
        # counters instead of forwarding its verbose logs to application output.
        exporter_log = logging.getLogger('azure.monitor.opentelemetry.exporter')
        exporter_log.handlers = [logging.NullHandler()]
        exporter_log.propagate = False
        credential = ManagedIdentityCredential(client_id=client_id)
        exporter = ContentFreeAzureMonitorTraceExporter(
            connection_string=connection, credential=credential,
            disable_offline_storage=True, timeout=5, retry_total=0,
            max_envelopes_per_second=20,
        )
        provider = TracerProvider(resource=Resource({'service.name': 'footie-agents'}),
                                  sampler=ParentBased(TraceIdRatioBased(ratio)))
        provider.add_span_processor(BatchSpanProcessor(SanitizingExporter(exporter),
            max_queue_size=256, max_export_batch_size=32, schedule_delay_millis=1000,
            export_timeout_millis=5000))
        trace.set_tracer_provider(provider)
        if trace.get_tracer_provider() is not provider:
            provider.shutdown()
            credential.close()
            return 'provider_conflict'
        _provider = provider
        _credential = credential
        return 'enabled'
    except Exception:
        LOG.warning('agent_trace_configuration_failed')
        return 'unavailable'


def flush_agent_tracing():
    """Bounded shutdown flush without shutting down the process-global provider."""
    if _provider is not None:
        try:
            return _provider.force_flush(timeout_millis=3000)
        except Exception:
            LOG.warning('agent_trace_flush_failed')
            return False
    return True


def shutdown_agent_tracing():
    """Application lifespan ends once per worker; flush, stop batcher, close MI."""
    if _provider is not None:
        try:
            flush_agent_tracing()
            _provider.shutdown()
        except Exception:
            LOG.warning('agent_trace_shutdown_failed')
        finally:
            if _credential is not None:
                _credential.close()


@contextmanager
def agent_span(name, *, role='orchestrator', attributes=None):
    """Safe stage spans; call set_attribute for the fixed counters in this module."""
    if name not in _NAMES or role not in AGENT_IDS:
        raise ValueError('Unknown agent trace stage')
    attrs = safe_attributes(attributes)
    attrs.update({'footie.role': role, 'gen_ai.agent.id': AGENT_IDS[role]})
    if name in {'footie.request', 'footie.specialist', 'footie.query'}:
        attrs['gen_ai.operation.name'] = 'invoke_agent'
    elif name in {'footie.route', 'footie.synthesize', 'footie.story'}:
        attrs['gen_ai.operation.name'] = 'chat'
    elif name == 'footie.tool':
        attrs['gen_ai.operation.name'] = 'execute_tool'
    with trace.get_tracer('counterpress.assistant').start_as_current_span(
        name, attributes=attrs, record_exception=False, set_status_on_exception=False,
    ) as span:
        try:
            yield span
        except BaseException:
            span.set_status(Status(StatusCode.ERROR))
            raise
