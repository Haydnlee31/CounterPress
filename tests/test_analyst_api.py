import asyncio
from contextlib import nullcontext
from types import SimpleNamespace

from fastapi import FastAPI
from fastapi.testclient import TestClient
import pytest

from counterpress.analyst.api import install_analyst
from counterpress.analyst.admission import Allowance, SQLiteStore

MID = 'wyscout-2058017'
BODY = {'cutoff': {'period': 1, 'elapsed_ms': 123456}}


class Provider:
    manifest_id = 'test-pinned-versions'
    def __init__(self):
        self.calls = 0
    async def analyze(self, snapshot, request):
        self.calls += 1
        await asyncio.sleep(.01)
        return {'status': 'insufficient_evidence', 'readings': [], 'summary': None}


@pytest.fixture
def setup(tmp_path, monkeypatch):
    def snapshot(career, mid, body):
        return {'snapshot_id': 'source-' + str(body.cutoff.elapsed_ms), 'match_id': mid,
                'cutoff': body.cutoff.model_dump(), 'through_sequence': 4,
                'evidence': [{'id': 'e1'}], 'metrics': [], 'signals': [], 'candidates': [{'id': 'supported'}]}
    monkeypatch.setattr('counterpress.analyst.api.build_snapshot', snapshot)
    career = SimpleNamespace(store=SimpleNamespace(snapshot=nullcontext))
    provider = Provider()
    app = FastAPI()
    allowance = Allowance(SQLiteStore(tmp_path / 'allowance.sqlite3'))
    install_analyst(app, lambda: career, provider=provider, allowance=allowance)
    return app, provider


def test_snapshot_exact_but_paid_analysis_quantizes_and_shares(setup):
    app, provider = setup
    with TestClient(app) as client:
        snap = client.post(f'/api/analyst/matches/{MID}/snapshot', json=BODY).json()
        assert snap['cutoff']['elapsed_ms'] == 123456
        first = client.post(f'/api/analyst/matches/{MID}/analysis', json=BODY).json()
        assert first['status'] == 'pending'
        assert first['cutoff']['elapsed_ms'] == 120000
        import time
        time.sleep(.05)
        repeated = client.post(f'/api/analyst/matches/{MID}/analysis', json={'cutoff': {'period': 1, 'elapsed_ms': 179999}}).json()
        assert repeated['status'] == 'insufficient_evidence'
        assert provider.calls == 1


def test_cross_site_oversized_and_unknown_match_rejected_before_inference(setup):
    app, provider = setup
    with TestClient(app) as client:
        url = f'/api/analyst/matches/{MID}/analysis'
        assert client.post(url, json=BODY, headers={'origin': 'https://attacker.example'}).status_code == 403
        assert client.post(url, content='x' * 4097).status_code == 413
        assert client.post('/api/analyst/matches/other/analysis', json=BODY).status_code == 404
        assert client.post(url, json={**BODY, 'extra': True}).status_code == 422
        assert provider.calls == 0


def test_unconfigured_mode_does_not_claim_native_agents(monkeypatch):
    monkeypatch.delenv('COUNTERPRESS_ANALYST_MODE', raising=False)
    app = FastAPI()
    install_analyst(app, lambda: None)
    with TestClient(app) as client:
        config = client.get('/api/analyst/config').json()
        assert config['mode'] == 'metrics'
        assert config['available'] is False
        assert len(config['roles']) == 4


def test_quiet_spell_never_reserves_allowance_or_starts_native_session(monkeypatch):
    def snapshot(career, mid, body):
        return {'snapshot_id': 'quiet', 'match_id': mid, 'cutoff': body.cutoff.model_dump(),
                'through_sequence': 1, 'evidence': [{'id': 'e1'}], 'candidates': []}
    monkeypatch.setattr('counterpress.analyst.api.build_snapshot', snapshot)
    class ForbiddenAllowance:
        def reserve(self, *args):
            pytest.fail('A quiet spell must not reserve spend')
    app = FastAPI(); provider = Provider()
    install_analyst(app, lambda: SimpleNamespace(store=SimpleNamespace(snapshot=nullcontext)),
                    provider=provider, allowance=ForbiddenAllowance())
    with TestClient(app) as client:
        response = client.post(f'/api/analyst/matches/{MID}/analysis', json=BODY)
        assert response.status_code == 200
        assert response.json()['status'] == 'insufficient_evidence'
        assert provider.calls == 0


def test_discussion_uses_shared_admission_but_not_legacy_candidate_templates(tmp_path,monkeypatch):
 import time
 def snapshot(career,mid,body):
  return {'snapshot_id':'s-'+str(body.cutoff.elapsed_ms),'match_id':mid,'cutoff':body.cutoff.model_dump(),'through_sequence':1,'evidence':[{'id':'e1'}],'candidates':[]}
 monkeypatch.setattr('counterpress.analyst.api.build_snapshot',snapshot)
 app=FastAPI(); provider=Provider()
 install_analyst(app,lambda:SimpleNamespace(store=SimpleNamespace(snapshot=nullcontext)),discussion_provider=provider,allowance=Allowance(SQLiteStore(tmp_path/'room.db')))
 with TestClient(app) as client:
  assert client.get('/api/analyst/config').json()['discussion_available'] is True
  url=f'/api/analyst/matches/{MID}/discussion'
  assert client.post(url,json={'cutoff':{'period':1,'elapsed_ms':30000}}).json()['status']=='insufficient_evidence'
  assert provider.calls==0
  assert client.post(url,json=BODY).json()['status']=='pending'
  time.sleep(.05)
  assert client.post(url,json=BODY).json()['status']=='insufficient_evidence'
  assert provider.calls==1
  assert client.post(f'/api/analyst/matches/{MID}/analysis',json=BODY).json()['status']=='disabled'


def test_cancel_last_viewer_stops_provider_but_shared_viewer_keeps_it_running(setup):
    import threading
    app, provider = setup
    started, cancelled = threading.Event(), threading.Event()
    async def blocked(snapshot, request):
        provider.calls += 1
        started.set()
        try:
            await asyncio.Event().wait()
        except asyncio.CancelledError:
            cancelled.set()
            raise
    provider.analyze = blocked
    first, second = 'a' * 32, 'b' * 32
    url = f'/api/analyst/matches/{MID}/analysis'
    with TestClient(app) as client:
        assert client.post(url, json=BODY, headers={'X-Analyst-View': first}).json()['status'] == 'pending'
        assert started.wait(2)
        assert client.post(url, json=BODY, headers={'X-Analyst-View': second}).json()['status'] == 'pending'
        assert client.post(f'/api/analyst/views/{first}/cancel').json()['local_jobs_cancelled'] == 0
        assert not cancelled.is_set()
        assert client.post(f'/api/analyst/views/{second}/cancel').json()['local_jobs_cancelled'] == 1
        assert cancelled.wait(2)
        assert provider.calls == 1
        # No resurrection or second paid round from a late request in a cancelled scope.
        assert client.post(url, json=BODY, headers={'X-Analyst-View': second}).json()['status'] == 'cancelled'
        assert provider.calls == 1


def test_cancel_arriving_before_initial_analysis_prevents_inference(setup):
    app, provider = setup
    with TestClient(app) as client:
        view = 'c' * 32
        assert client.post(f'/api/analyst/views/{view}/cancel').status_code == 200
        result = client.post(f'/api/analyst/matches/{MID}/analysis', json=BODY, headers={'X-Analyst-View': view})
        assert result.json()['status'] == 'cancelled'
        assert provider.calls == 0
        assert client.post('/api/analyst/views/invalid/cancel').status_code == 422


@pytest.mark.parametrize('storage', ['exhausted_cosmos', 'failed_cosmos', 'absent'])
def test_azure_activation_uses_existing_durable_admission_and_fails_closed(monkeypatch, storage):
    from azure.core.exceptions import AzureError
    import copy
    provider = Provider()
    monkeypatch.setenv('COUNTERPRESS_ANALYST_MODE', 'off')
    monkeypatch.setenv('COUNTERPRESS_ANALYST_DISCUSSION', 'azure')
    monkeypatch.delenv('COUNTERPRESS_ANALYST_LEDGER_PATH', raising=False)
    monkeypatch.setattr('counterpress.adaptation.azure.load_config', lambda: object())
    monkeypatch.setattr('counterpress.analyst.discussion.AzureDiscussion', lambda config: provider)
    monkeypatch.setattr('counterpress.analyst.api.build_snapshot', lambda career, mid, body: {
        'snapshot_id': 'existing-source', 'match_id': mid, 'cutoff': body.cutoff.model_dump(),
        'through_sequence': 4, 'evidence': [{'id': 'e1'}], 'candidates': []})
    class Container:
        def __init__(self):
            self.reads = []
            self.writes = []
        def read_item(self, item, partition_key):
            self.reads.append((item, partition_key))
            if storage == 'failed_cosmos': raise AzureError('unavailable')
            return {'_etag': 'existing', 'payload': {'spent_cents': 3000}}
        def execute_item_batch(self, *, batch_operations, partition_key):
            self.writes.append((copy.deepcopy(batch_operations), partition_key))
    container = Container()
    app = FastAPI()
    install_analyst(app, lambda: SimpleNamespace(store=SimpleNamespace(snapshot=nullcontext)),
                    history_store=None if storage == 'absent' else SimpleNamespace(container=container))
    with TestClient(app) as client:
        assert client.get('/api/analyst/config').json()['discussion_available'] == (storage != 'absent')
        result = client.post(f'/api/analyst/matches/{MID}/discussion', json=BODY)
        if storage == 'exhausted_cosmos':
            assert result.json()['status'] == 'budget_limit'
            assert container.reads == [('control', 'analyst-control-v1')]
            assert container.writes[0][0][0][1][1]['payload']['spent_cents'] == 3000
        elif storage == 'failed_cosmos': assert result.json()['status'] == 'unavailable'
        else: assert result.json()['status'] == 'disabled'
        assert provider.calls == 0
