import asyncio
from copy import deepcopy
from decimal import Decimal
import json

import httpx2
import pytest

from counterpress.adaptation.azure import ProviderFailure
from counterpress.audience import ViewingPreferences
from counterpress.api.snapshots import SnapshotService
from counterpress.cosmos_history import CosmosHistoryStore
from counterpress.evaluation.editorial import (
    evaluate_suite, prepare, validate_presentation, verified_cases, summarize,
)
from counterpress.evaluation.meter import Meter, MeteredTransport
from counterpress.recaps import build_recap
from counterpress.workflow.single_editor import SingleEditorService
from test_cosmos_history import AtomicContainer
from test_recap_workflow import ROOT, snapshots, Script
from test_history import updates
from test_workflow import CONFIG, completion, content


def single_response(request, decision='accept', mutate=None):
    package = json.loads(content(json.loads(request.content)['messages'][-1]))
    selected = package['stories'] if decision == 'accept' else package['stories'][:1] if decision == 'narrow' else []
    plan = {'fingerprint': package['fingerprint'], 'decision': decision, 'stories': selected,
            'reason': {'accept': 'supported_comparisons', 'narrow': 'focused_subset',
                       'reject': 'insufficient_evidence'}[decision],
            'draft': {'fingerprint': package['fingerprint'], 'language': package['language'],
                      'heading': 'key_changes', 'stories': [s | {'template': 'brief'} for s in selected]}
                     if selected else None}
    if mutate:
        mutate(plan)
    result = completion(plan)
    body = json.loads(result.content)
    body['usage'] = {'prompt_tokens': 1200, 'completion_tokens': 250}
    return httpx2.Response(200, json=body)


def service(app, handler=single_response, **kwargs):
    return SingleEditorService(app, CONFIG, transport_factory=lambda: httpx2.MockTransport(handler), **kwargs)


@pytest.mark.parametrize('language', ['en', 'zh-Hans'])
@pytest.mark.parametrize('decision,status,size', [('accept', 'accepted', 2), ('narrow', 'narrowed', 1), ('reject', 'rejected', 2)])
def test_one_editor_preserves_facts_and_perspective_in_one_request(language, decision, status, size):
    app = snapshots()
    prefs = ViewingPreferences(language=language)
    before = app.snapshot('pressure-increase', 780000, preferences=prefs)
    result = asyncio.run(service(app, lambda r: single_response(r, decision)).run('pressure-increase', 780000, prefs))
    assert result.status == status
    assert result.prompt_version == 'recap-single-editor-v1'
    assert (result.analyst_requests, result.producer_requests, result.tool_invocations) == (0, 1, 0)
    after = app.snapshot('pressure-increase', 780000, preferences=prefs)
    assert after.recap == before.recap
    displayed = after.adapted_recap or after.recap
    assert len(displayed.statements) == size
    assert all(s.citation in [x.citation for x in before.recap.statements] for s in displayed.statements)
    assert after.recap_workflow.applied == (status != 'rejected')


@pytest.mark.parametrize('mutate', [
    lambda p: p.update(fingerprint='wrong'),
    lambda p: p['stories'][0].update(revision=999),
    lambda p: p['stories'].reverse(),
    lambda p: p.update(stories=p['stories'][:1]),
    lambda p: p['draft'].update(language='zh-Hans'),
    lambda p: p['draft'].update(prose='Invented tactical superiority'),
    lambda p: p['draft']['stories'][0].update(template='free_text'),
    lambda p: p['draft']['stories'].pop(),
    lambda p: p.update(draft=None),
])
def test_invalid_editor_output_never_replaces_factual_recap(mutate):
    app = snapshots()
    attempt = asyncio.run(service(app, lambda r: single_response(r, mutate=mutate)).run('pressure-increase', 780000))
    assert attempt.status == 'invalid' and attempt.draft is None
    assert app.snapshot('pressure-increase', 780000).adapted_recap is None


def test_concurrent_correction_discards_single_editor_without_holding_a_transaction():
    app = snapshots()
    async def exercise():
        entered, release = asyncio.Event(), asyncio.Event()
        async def pending(request):
            entered.set()
            await release.wait()
            return single_response(request)
        task = asyncio.create_task(service(app, pending).run('increase', 780000))
        await asyncio.wait_for(entered.wait(), 2)
        assert app.snapshot('increase', 540000).recap.state == 'collecting'
        app.ingest('increase', updates())
        release.set()
        result = await task
        assert result.status == 'stale' and result.draft is None
        assert app.snapshot('increase', 795000).adapted_recap is None
    asyncio.run(exercise())


def test_single_editor_timeout_retains_factual_fallback():
    dispatched = []
    async def never(request):
        dispatched.append(request)
        await asyncio.Event().wait()
    app = snapshots()
    before = app.snapshot('increase', 780000).recap
    result = asyncio.run(service(app, never, timeout_seconds=.02).run('increase', 780000))
    assert result.status == 'timeout' and result.draft is None
    # The total deadline includes SDK setup: a busy runner may expire before dispatch.
    assert result.provider_requests == len(dispatched) <= 1
    after = app.snapshot('increase', 780000)
    assert after.adapted_recap is None and after.recap == before


def test_single_editor_cosmos_contract_survives_fresh_store_and_expiry(monkeypatch):
    container = AtomicContainer()
    app = SnapshotService(ROOT/'fixtures', CosmosHistoryStore(container))
    result = asyncio.run(service(app).run('increase', 780000))
    fresh = SnapshotService(ROOT/'missing', CosmosHistoryStore(container))
    assert fresh.history('increase').recap_workflows[-1] == result
    assert fresh.snapshot('increase', 780000).adapted_recap is not None
    monkeypatch.setattr('counterpress.api.snapshots.time', lambda: result.expires_at_unix_ms/1000)
    assert fresh.snapshot('increase', 780000).adapted_recap is None


def request(**changes):
    return httpx2.Request('POST', CONFIG.url, json={'messages': [{'role': 'user', 'content': 'test'}],
                                                  'max_tokens': 650, **changes})


def test_request_limit_and_estimated_allowance_fail_before_dispatch():
    meter = Meter(max_requests=1)
    meter.admit(request())
    with pytest.raises(ProviderFailure, match='evaluation_allowance_exhausted'):
        meter.admit(request())
    assert len(meter.receipts) == 1
    with pytest.raises(ProviderFailure):
        Meter(allowance_usd=Decimal('.00001')).admit(request())
    for bad in [request(stream=True), request(max_tokens=651), request(max_tokens=True),
                request(messages=[{'content': 'x'*65537}])]:
        with pytest.raises(ProviderFailure, match='evaluation_payload_limit'):
            Meter().admit(bad)


def test_usage_reports_known_tokens_and_keeps_missing_usage_unknown():
    async def exercise():
        meter = Meter()
        transport = MeteredTransport(meter, httpx2.MockTransport(lambda r: httpx2.Response(200, json={
            'usage': {'prompt_tokens': 1000, 'completion_tokens': 100}})))
        async with httpx2.AsyncClient(transport=transport) as client:
            await client.send(request())
        assert meter.receipts[0]['estimated_usd'] == .000616
        unknown = MeteredTransport(meter, httpx2.MockTransport(lambda r: httpx2.Response(500, json={})))
        async with httpx2.AsyncClient(transport=unknown) as client:
            await client.send(request())
        assert meter.receipts[1]['estimated_usd'] is None
        assert meter.reserved_usd > 0
    asyncio.run(exercise())


def test_full_frozen_matrix_runs_three_variants_with_no_paid_calls_for_ineligible_cases():
    existing = Script()
    def handler(r):
        name = json.loads(r.content)['response_format']['json_schema']['name']
        return single_response(r) if name == 'EditorialPlan' else existing(r)
    result = asyncio.run(evaluate_suite(live=True, config=CONFIG,
                        transport_factory=lambda: httpx2.MockTransport(handler)))
    assert result['checks'] == {'passed': 45, 'failed': 0, 'errored': 0}
    assert result['human_usefulness_ratings'] is None
    assert result['summary']['single_editor']['dispatched_requests'] == 11
    assert result['summary']['analyst_producer']['dispatched_requests'] == 33, [
        (row['case_id'], row['status'], row['reason'], row['dispatched_requests'])
        for row in result['rows'] if row['variant']=='analyst_producer' and row['model_eligible']]
    assert result['summary']['single_editor']['latency_ms_p95'] is None
    # Mock two-role responses deliberately omit usage; never silently price it as free.
    assert result['summary']['analyst_producer']['usage_missing_requests'] == 33
    assert result['summary']['analyst_producer']['estimated_usd_per_accepted_including_failures'] is None


def test_evaluator_rejects_changed_facts_citations_qualifications_and_order():
    case = verified_cases()[0]['cases'][0]
    app, prefs, snap = prepare(case)
    source = snap.recap
    brief = build_recap(app.history(case['scenario']), source.cutoff, source.windows,
                        prefs.model_copy(update={'depth': 'casual'}))
    assert validate_presentation(source, source, brief)
    for field, value in [('explanation', 'Nine goals prove tactical dominance'), ('qualification', ''), ('title', 'Made up')]:
        edited = source.statements[0].model_copy(update={'narrative': source.statements[0].narrative.model_copy(update={field: value})})
        assert not validate_presentation(source, source.model_copy(update={'statements': (edited, *source.statements[1:])}), brief)
    changed = source.statements[0].model_copy(update={'citation': source.statements[0].citation.model_copy(update={'revision': 999})})
    assert not validate_presentation(source, source.model_copy(update={'statements': (changed, *source.statements[1:])}), brief)
    assert not validate_presentation(source, source.model_copy(update={'statements': source.statements[::-1]}), brief)


def test_case_or_prompt_drift_requires_explicit_refreeze(monkeypatch):
    monkeypatch.setattr('counterpress.evaluation.editorial.source_hashes', lambda: {})
    with pytest.raises(ValueError, match='Frozen'):
        verified_cases()


def test_summary_does_not_count_fallback_as_successful_ai():
    result = asyncio.run(evaluate_suite())
    row = deepcopy(result['rows'][0])
    row.update(variant='single_editor', status='timeout', fallback=True, usage_missing_requests=1,
               dispatched_requests=1, observed_estimated_usd=0)
    summary = summarize([row])['single_editor']
    assert summary['supported_presentations'] == 1 and summary['accepted'] == 0
    assert summary['fallbacks_on_eligible'] == 1
    assert summary['estimated_usd_per_accepted_including_failures'] is None
