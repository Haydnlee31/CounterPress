"""A failed investigation must not disguise a partial direct lookup as complete."""
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from counterpress.adaptation.azure import ProviderFailure
from counterpress.assistant.api import install_assistant
from counterpress.personalization.service import CareerService
from counterpress.personalization.store import DataStore


@pytest.fixture(scope='module')
def career():
    store=DataStore(Path(__file__).resolve().parents[1]/'fixtures/personalization')
    yield CareerService(store)
    store.close()


class UnavailableResearch:
    max_requests=4
    deadline_seconds=24

    def __init__(self,reason):self.reason=reason

    async def research(self,service,request,reserve):
        if self.reason=='timeout':raise TimeoutError()
        raise ProviderFailure('limited',self.reason)


@pytest.mark.parametrize('question',[
    'Tell me what has changed during this game. Also give Mateo Cross’s pre-match career goal count.',
    'Review Mateo Cross’s performance in the current match, then show his goals from 2025-26.',
])
@pytest.mark.parametrize('reason',['model_allowance_exhausted','timeout'])
@pytest.mark.parametrize('language',['en','zh-Hans'])
def test_failed_investigation_discloses_incomplete_answer(career,question,reason,language):
    app=FastAPI();install_assistant(app,lambda:career,researcher=UnavailableResearch(reason))
    with TestClient(app) as client:
        answer=client.post('/api/fan/assistant/ask',json={
            'question':question,'match_id':'career-showcase-southbank-redhaven',
            'cutoff':{'period':2,'elapsed_ms':1632996},
            'preferences':{'language':language}}).json()
    assert answer['status']=='answered' and answer['facts']
    assert answer['mode']=='lookup_fallback'
    assert answer['research']=={'partial':True,'unavailable':['orchestrator']}
    assert answer['plan']['operation']=='clarify' and not answer['plan']['player_ids']
    assert answer['narrative']=={'mode':'calculated','blocks':[],
                                 'fallback_reason':'research_unavailable'}
    assert ('only part of your question' if language=='en' else '只回答了你问题的一部分') in answer['text'][-1]
    # The direct answer may remain useful, but must not invent the missing
    # historical clause's independently known 73-career / 14-season goal count.
    assert not any(f['metric']=='goals' and f['value'] in (73,14) for f in answer['facts'])


def test_missing_context_still_asks_for_context_without_partial_statistics(career):
    app=FastAPI();install_assistant(app,lambda:career,researcher=UnavailableResearch('timeout'))
    with TestClient(app) as client:
        answer=client.post('/api/fan/assistant/ask',json={'question':'Explain the buildup to this goal.'}).json()
    assert answer['status']=='clarify' and not answer['facts']
    assert 'research' not in answer
    assert not any('only part' in text for text in answer['text'])


@pytest.mark.parametrize('workflow,expected',[('unique',False),('lookup',False),('failed',True)])
def test_monitoring_distinguishes_calculated_answers_from_failed_research(career,monkeypatch,workflow,expected):
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import SimpleSpanProcessor
    from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
    from counterpress.assistant import observability
    from counterpress.assistant.contracts import AskRequest
    from counterpress.assistant.service import AssistantService
    from test_assistant_multiagent import fake_multi
    exporter=InMemorySpanExporter();provider=TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(observability.SanitizingExporter(exporter)))
    tracer=provider.get_tracer('fallback-regression')
    monkeypatch.setattr(observability.trace,'get_tracer',lambda *args,**kwargs:tracer)
    monkeypatch.delenv('COUNTERPRESS_ASSISTANT_MODEL',raising=False)
    body=AskRequest(question='What is Mateo Cross’s pass accuracy?')
    researcher=None
    if workflow=='unique':researcher,_=fake_multi(AssistantService(career),body)
    elif workflow=='failed':researcher=UnavailableResearch('timeout')
    app=FastAPI();install_assistant(app,lambda:career,researcher=researcher)
    try:
        with TestClient(app) as client:
            response=client.post('/api/fan/assistant/ask',json=body.model_dump(by_alias=True))
        assert response.status_code==200 and response.json()['status']=='answered'
        assert response.json()['narrative']['mode']=='calculated'
        assert response.json()['mode']==('azure_agent' if workflow=='unique' else 'lookup_fallback' if workflow=='failed' else 'lookup')
        root=[span for span in exporter.get_finished_spans() if span.name=='footie.request']
        assert len(root)==1 and root[0].attributes['footie.fallback'] is expected
    finally:provider.shutdown()
