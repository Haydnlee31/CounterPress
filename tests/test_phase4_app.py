"""The isolated verifier cannot inherit production storage or inference routes."""
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from counterpress.api.phase4 import ISOLATION, CareerOnly, create_app
from counterpress.personalization.journal import SQLiteCareerJournal
from counterpress.streaming.telemetry import StreamTelemetry

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def configured(monkeypatch, tmp_path):
    for name, value in ISOLATION.items():
        monkeypatch.setenv(name, value)
    monkeypatch.delenv('COUNTERPRESS_STATIC_DIR', raising=False)
    journal = SQLiteCareerJournal(tmp_path / 'isolated.sqlite3')
    runtimes = []

    class Runtime:
        def __init__(self, service, career):
            self.telemetry = StreamTelemetry(enabled=False)
            self.publisher = SimpleNamespace(negotiate_career=self.negotiate)
            self.closed = False
            self.datasets = []
            runtimes.append(self)

        async def negotiate(self, dataset):
            self.datasets.append(dataset)
            return {'enabled': True, 'url': 'wss://example.webpubsub.azure.com/client/hubs/counterpress_phase4?access_token=test'}

        async def start(self):
            pass

        async def close(self):
            self.closed = True

    yield dict(fixture_dir=ROOT / 'fixtures', journal=journal, runtime_factory=Runtime), runtimes
    journal.close()


@pytest.mark.parametrize('key', list(ISOLATION))
def test_missing_or_mixed_configuration_rejected_before_storage(configured, monkeypatch, key):
    kwargs, _ = configured
    monkeypatch.delenv(key)
    with pytest.raises(ValueError, match='complete isolated'):
        create_app(**kwargs)
    monkeypatch.setenv(key, 'production')
    with pytest.raises(ValueError, match='complete isolated'):
        create_app(**kwargs)


def test_read_only_routes_reuse_career_contracts_without_inference(configured):
    kwargs, runtimes = configured
    with TestClient(create_app(**kwargs)) as client:
        assert client.get('/ready').status_code == 200
        cfg = client.get('/api/phase4/config')
        assert cfg.headers['cache-control'] == 'no-store'
        assert cfg.json()['inference'] is False
        assert cfg.json()['cosmos_container'] == 'histories-phase4'
        revisions = client.get('/api/data/revisions').json()
        assert revisions['enabled'] is True and revisions['generation'] == 0
        assert revisions['dataset'] == cfg.json()['dataset']
        for path in ['/api/fan/assistant/ask', '/api/studio', '/api/live/speech', '/api/editorial']:
            assert client.post(path, json={}).status_code == 404
        for path in ['/api/fan/assistant/config', '/api/live/speech/config']:
            assert client.get(path).status_code == 404
        assert client.get('/api/data/players/rh09').status_code == 200
        response = client.post('/api/fan/matches/career-showcase-southbank-redhaven', json={
            'cutoff': {'period': 2, 'elapsed_ms': 1050489}, 'preferences': {}})
        assert response.status_code == 200
    assert runtimes[0].closed


def test_receive_only_negotiation_rate_limit_and_counters_do_not_reset(configured):
    kwargs, runtimes = configured
    with TestClient(create_app(**kwargs)) as client:
        runtime = runtimes[0]
        runtime.telemetry.increment('processed')
        first = client.get('/api/phase4/telemetry').json()
        assert first['processed'] == 1 and first['pending'] is False
        assert client.get('/api/phase4/telemetry').json() == first
        for _ in range(30):
            result = client.get('/api/data/revisions/negotiate')
            assert result.status_code == 200
            assert result.headers['referrer-policy'] == 'no-referrer'
        assert len(set(runtime.datasets)) == 1
        assert client.get('/api/data/revisions/negotiate').status_code == 429


def test_noncareer_deliveries_are_rejected():
    with pytest.raises(ValueError, match='career deliveries only'):
        CareerOnly().history('increase')


def test_static_preview_serves_only_compiled_assets(configured, tmp_path):
    kwargs, _ = configured
    folder = tmp_path / 'static'
    (folder / 'assets').mkdir(parents=True)
    (folder / 'index.html').write_text('<html>Footie verification</html>')
    (folder / 'assets' / 'app.js').write_text('/* compiled */')
    (folder / 'private.txt').write_text('never serve this')
    with TestClient(create_app(**kwargs, static_dir=folder)) as client:
        assert client.get('/').headers['cache-control'] == 'no-store'
        assert client.get('/assets/app.js').status_code == 200
        for path in ['/private.txt', '/.env', '/fixtures/personalization/manifest.json',
                     '/assets/../private.txt', '/assets/%2e%2e/private.txt']:
            assert client.get(path).status_code == 404
