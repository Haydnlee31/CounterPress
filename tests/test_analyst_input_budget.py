import asyncio
import json
from types import SimpleNamespace

import httpx
import pytest
from pydantic import SecretStr

from counterpress.adaptation.azure import AzureConfig, ProviderFailure
from counterpress.analyst.discussion import guard_azure_request
from counterpress.assistant.planner import structured_request


def config():
    return AzureConfig(endpoint='https://unit-test.openai.azure.com', deployment='gpt-5-mini', api_key=SecretStr('unit-test-only'))


@pytest.mark.parametrize('count,allowed', [(11904, True), (11905, False)])
def test_input_bound_includes_provider_framing_reserve(monkeypatch, count, allowed):
    monkeypatch.setattr('tiktoken.get_encoding', lambda _: SimpleNamespace(encode=lambda *a, **kw: range(count)))
    if allowed:
        guard_azure_request(b'{}')
    else:
        with pytest.raises(ProviderFailure, match='input_budget_exceeded'):
            guard_azure_request(b'{}')


def test_tokenizer_failure_closes_dispatch(monkeypatch):
    def fail(_):
        raise OSError('unavailable')
    monkeypatch.setattr('tiktoken.get_encoding', fail)
    with pytest.raises(ProviderFailure, match='input_budget_unavailable'):
        guard_azure_request(b'{}')


def test_guard_sees_actual_body_schema_and_history_before_transport(monkeypatch):
    seen=[]
    def encode(text, **kwargs):
        seen.append(json.loads(text))
        return range(11905)
    monkeypatch.setattr('tiktoken.get_encoding', lambda _: SimpleNamespace(encode=encode))
    sent=[]
    def transport(request):
        sent.append(request)
        return httpx.Response(500)
    with pytest.raises(ProviderFailure, match='input_budget_exceeded'):
        asyncio.run(structured_request(config(), httpx.MockTransport(transport), 'system',
            {'conversation':[{'text':'prior finding'}]}, {'type':'object'}, 'analyst_control',2200,20,
            request_guard=guard_azure_request))
    assert sent == []
    assert seen[0]['messages'][0]['content']=='system'
    assert json.loads(seen[0]['messages'][1]['content'])['conversation'][0]['text']=='prior finding'
    assert seen[0]['response_format']['json_schema']['schema']=={'type':'object'}
    assert seen[0]['max_completion_tokens']==2200


def test_allowed_body_sent_once_without_retry_and_reports_usage(monkeypatch):
    monkeypatch.setattr('tiktoken.get_encoding', lambda _: SimpleNamespace(encode=lambda *a, **kw: range(100)))
    sent=[]
    def transport(request):
        sent.append(request)
        return httpx.Response(200,json={'choices':[{'finish_reason':'stop','message':{'content':'{}'}}],
            'usage':{'prompt_tokens':100,'completion_tokens':25,'total_tokens':125}})
    _, usage=asyncio.run(structured_request(config(),httpx.MockTransport(transport),'system',{},
        {'type':'object'},'analyst_control',2200,20,request_guard=guard_azure_request))
    assert len(sent)==1 and usage['prompt_tokens']==100 and usage['completion_tokens']==25
