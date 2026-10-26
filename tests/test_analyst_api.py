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
