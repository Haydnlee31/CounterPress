import asyncio
import json
from types import SimpleNamespace

import httpx
import pytest

from counterpress.analyst.provider import FoundryAnalyst, validate_result

ENDPOINT = 'https://unit-test.services.ai.azure.com/api/projects/test'
PACKET = {'snapshot_id': 'a' * 64, 'match_id': 'm', 'cutoff': {'period': 1, 'elapsed_ms': 600000},
          'through_sequence': 10, 'evidence': [{'id': 'e1'}],
          'metrics': [{'id': 'm1', 'value': 3, 'status': 'available', 'role': 'chance'}]}
READING = {'role': 'chance', 'headline': 'Closer chances', 'explanation': 'More attacks are reaching shooting positions.',
           'alternative': 'The recent sample is small.', 'watch_next': 'Watch whether the next attacks reach the box.',
           'evidence_ids': ['e1'], 'metric_ids': ['m1'], 'confidence': 'medium'}


def result():
    return {**{k: PACKET[k] for k in ('snapshot_id', 'match_id', 'cutoff', 'through_sequence')},
            'status': 'complete', 'readings': [READING],
            'summary': {k: READING[k] for k in ('headline', 'explanation', 'evidence_ids', 'metric_ids')},
            'usage': {'model_calls': 1}}


class Credential:
    async def __aenter__(self): return self
    async def __aexit__(self, *args): pass
    async def get_token(self, scope):
        assert scope == 'https://ai.azure.com/.default'
        return SimpleNamespace(token='test-only')


@pytest.mark.parametrize('bad', ['http://unit-test.services.ai.azure.com/api/projects/test',
    'https://attacker.example/api/projects/test', ENDPOINT + '?redirect=x',
    'https://user:password@unit-test.services.ai.azure.com/api/projects/test'])
def test_non_tls_or_untrusted_endpoints_rejected(bad):
    with pytest.raises(ValueError):
        FoundryAnalyst(bad, 'director', '1', 'a' * 64)


def test_wrong_snapshot_and_unverified_summary_rejected():
    wrong = result(); wrong['snapshot_id'] = 'future'
    with pytest.raises(ValueError): validate_result(wrong, PACKET)
    wrong = result(); wrong['summary'] = {'headline': 'Invented'}
    with pytest.raises(ValueError): validate_result(wrong, PACKET)
    wrong = result(); wrong['readings'] = [{**READING, 'evidence_ids': ['future-event']}]
    with pytest.raises(ValueError): validate_result(wrong, PACKET)


@pytest.mark.parametrize('failure', [False, True])
def test_native_session_is_pinned_and_cleaned_even_on_provider_failure(monkeypatch, failure):
    calls = []
    def handler(request):
        calls.append(request)
        if request.url.path.endswith('/responses'):
            body = json.loads(request.content)
            assert body['agent_reference'] == {'type': 'agent_reference', 'name': 'director', 'version': '7'}
            assert len(body['agent_session_id']) == 36
            assert 'conversation' not in body
            if failure: return httpx.Response(500)
            return httpx.Response(200, json={'status': 'completed', 'output': [{'type': 'message', 'content': [
                {'type': 'output_text', 'text': json.dumps(result())}]}]})
        return httpx.Response(204)
    monkeypatch.setattr('counterpress.analyst.service.build_dispatch_packet', lambda s: dict(PACKET), raising=False)
    provider = FoundryAnalyst(ENDPOINT, 'director', '7', 'b' * 64, Credential,
                             lambda **kwargs: httpx.AsyncClient(transport=httpx.MockTransport(handler), **kwargs))
    request = SimpleNamespace(language='en', depth='analyst', focus_player_id=None)
    if failure:
        with pytest.raises(httpx.HTTPStatusError): asyncio.run(provider.analyze(PACKET, request))
    else:
        assert asyncio.run(provider.analyze(PACKET, request))['execution']['runtime'] == 'foundry_hosted'
    assert [r.method for r in calls] == ['POST', 'POST', 'DELETE']
    sid = json.loads(calls[0].content)['agent_session_id']
    assert sid in calls[1].url.path and sid in calls[2].url.path
