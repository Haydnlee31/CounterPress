"""Producer authorization, durable decisions, source races and withdrawal safety."""
import asyncio
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import httpx
import pytest

from counterpress.api.main import create_app
from counterpress.api.snapshots import SnapshotService
from counterpress.audience import ViewingPreferences
from counterpress.cosmos_history import CosmosHistoryStore
from counterpress.history import SQLiteHistoryStore, validate_history_update
from counterpress.studio.api import StudioAccess, configure_studio
from counterpress.studio.service import StudioService, ReviewRequest, DecisionRequest, ReviewConflict, render_export
from test_cosmos_history import AtomicContainer
from test_editorial_controls import signing_key, verifier, token, CLIENT
from test_history import updates

ROOT = Path(__file__).resolve().parents[1]
ACTOR = 'a' * 64


@pytest.fixture(params=['sqlite', 'cosmos'])
def services(request, tmp_path):
    if request.param == 'sqlite':
        factory = lambda: SQLiteHistoryStore(tmp_path/'review.sqlite3')
    else:
        container = AtomicContainer()
        factory = lambda: CosmosHistoryStore(container=container)
    return lambda: StudioService(SnapshotService(ROOT/'fixtures', factory()))


def decision(view, **changes):
    return DecisionRequest(preferences=view.recap.preferences, fingerprint=view.fingerprint, **changes)


def test_approval_and_revocation_survive_restart_and_are_idempotent(services):
    service = services()
    view = service.review('increase', ReviewRequest())
    assert view.status == 'unreviewed'
    approved = service.decide('increase', decision(view), ACTOR, 'approve')
    assert approved.status == 'approved'
    assert service.decide('increase', decision(view), ACTOR, 'approve') == approved
    restarted = services()
    assert restarted.review('increase', ReviewRequest()) == approved
    assert approved.fingerprint in restarted.export('increase', decision(view))
    revoked = restarted.decide('increase', decision(view), ACTOR, 'revoke')
    assert revoked.status == 'revoked'
    assert services().review('increase', ReviewRequest()) == revoked
    with pytest.raises(ReviewConflict):
        services().export('increase', decision(view))
    with pytest.raises(ValueError, match='cannot be rewritten'):
        old = restarted.snapshots.history('increase')
        validate_history_update(old, old.model_copy(update={'studio_decisions': ()}))


def test_correction_withdrawal_and_reappearance_never_reuse_approval(services):
    service = services()
    old = service.review('increase', ReviewRequest())
    service.decide('increase', decision(old), ACTOR, 'approve')
    for event in updates():
        service.snapshots.ingest('increase', (event,))
        with pytest.raises(ReviewConflict):
            service.decide('increase', decision(old), ACTOR, 'approve')
        with pytest.raises(ReviewConflict):
            service.export('increase', decision(old))
        current = services().review('increase', ReviewRequest())
        assert current.status in ('changed', 'unavailable')
        assert current.approval_id is None
    assert len(service.snapshots.history('increase').studio_decisions) == 1


def test_language_depth_and_source_identity_bind_approval(services):
    service = services()
    old = service.review('increase', ReviewRequest())
    service.decide('increase', decision(old), ACTOR, 'approve')
    for prefs in (ViewingPreferences(language='zh-Hans'), ViewingPreferences(depth='casual')):
        request = DecisionRequest(preferences=prefs, fingerprint=old.fingerprint)
        with pytest.raises(ReviewConflict):
            service.decide('increase', request, ACTOR, 'approve')
        with pytest.raises(ReviewConflict):
            service.export('increase', request)
    # Same numeric totals, changed supporting event: invalidation still required.
    from test_history import revise
    service.snapshots.ingest('increase', (revise(updates()[0], position={'x': 73, 'y': 38}),))
    assert service.snapshots.history('increase').changes[-1].insight.facts.current_count == 4
    assert service.review('increase', ReviewRequest()).status == 'changed'


def test_correction_between_review_and_transaction_fails_closed(services):
    service = services()
    old = service.review('increase', ReviewRequest())
    real = service.snapshots.store.transact
    def race(scenario, build):
        service.snapshots.store.transact = real
        service.snapshots.ingest(scenario, (updates()[0],))
        return real(scenario, build)
    service.snapshots.store.transact = race
    with pytest.raises(ReviewConflict):
        service.decide('increase', decision(old), ACTOR, 'approve')
    assert not service.snapshots.history('increase').studio_decisions


def test_concurrent_sqlite_approvals_have_one_durable_decision(tmp_path):
    def service():
        return StudioService(SnapshotService(ROOT/'fixtures', SQLiteHistoryStore(tmp_path/'concurrent.sqlite3')))
    old = service().review('increase', ReviewRequest())
    with ThreadPoolExecutor(max_workers=4) as pool:
        results = list(pool.map(lambda _: service().decide('increase', decision(old), ACTOR, 'approve'), range(4)))
    assert len({r.approval_id for r in results}) == 1
    assert len(service().snapshots.history('increase').studio_decisions) == 1


def test_empty_story_cannot_be_approved(services):
    service = services()
    view = service.review('control', ReviewRequest(preferences=ViewingPreferences(card_budget=0)))
    assert view.status == 'unavailable'
    with pytest.raises(ReviewConflict):
        service.decide('control', decision(view), ACTOR, 'approve')


def test_export_escapes_text_and_discloses_static_synthetic_artifact(services):
    service = services()
    view = service.review('increase', ReviewRequest())
    view = service.decide('increase', decision(view), ACTOR, 'approve')
    body = service.export('increase', decision(view))
    assert 'Synthetic football' in body and 'cannot recall' in body
    assert 'revision 1' in body and '<script' not in body
    statement = view.recap.statements[0]
    modified = statement.model_copy(update={'narrative': statement.narrative.model_copy(update={'title': '<script>alert(1)</script>'})})
    body = render_export(view.model_copy(update={'recap': view.recap.model_copy(update={'statements': (modified,)})}))
    assert '<script>' not in body and '&lt;script&gt;' in body


def test_api_authentication_and_no_model_configuration(signing_key, tmp_path, monkeypatch):
    monkeypatch.setenv('COUNTERPRESS_EDITORIAL', 'off')
    monkeypatch.setenv('COUNTERPRESS_STUDIO', 'off')
    app = create_app(db_path=tmp_path/'api.sqlite3', studio=StudioAccess(verifier(signing_key), CLIENT))
    async def check():
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://test') as client:
            for action in ('review', 'approve', 'revoke', 'export', 'broadcast'):
                body = {} if action == 'review' else {'fingerprint': 'a'*64}
                if action == 'broadcast': body.update(insight_id='test-story', format='lower-third')
                for jwt_token, status in [(None, 401), ('invalid', 401), (token(signing_key, roles=[]), 403), (token(signing_key, azp=CLIENT.replace('3','5')), 403)]:
                    response = await client.post(f'/api/studio/increase/{action}', json=body,
                        headers={'Authorization': f'Bearer {jwt_token}'} if jwt_token else {})
                    assert response.status_code == status
                    assert response.headers['Cache-Control'] == 'no-store'
            headers = {'Authorization': f'Bearer {token(signing_key)}'}
            response = await client.post('/api/studio/increase/review', json={}, headers=headers)
            assert response.status_code == 200
            data = response.json()
            body = {'fingerprint': data['fingerprint']}
            assert (await client.post('/api/studio/increase/approve', json=body, headers=headers)).json()['status'] == 'approved'
            assert (await client.post('/api/studio/increase/export', json=body, headers=headers)).status_code == 200
            for format in ('presenter-cue', 'lower-third'):
                choice = body | {'insight_id': data['recap']['statements'][0]['citation']['insight_id'], 'format': format}
                output = await client.post('/api/studio/increase/broadcast', json=choice, headers=headers)
                assert output.status_code == 200 and output.headers['Cache-Control'] == 'no-store'
                assert output.headers['Content-Disposition'] == f'attachment; filename="counterpress-{format}.html"'
                assert "default-src 'none'" in output.headers['Content-Security-Policy']
                for invalid in (choice | {'text': 'forged'}, choice | {'format': '../../bad'}):
                    assert (await client.post('/api/studio/increase/broadcast', json=invalid, headers=headers)).status_code == 422
            assert (await client.post('/api/studio/increase/approve', json=body | {'text':'forged'}, headers=headers)).status_code == 422
            assert (await client.post('/api/studio/unknown/review', json={}, headers=headers)).status_code == 404
            config = (await client.get('/api/studio/config')).json()
            assert set(config) == {'enabled', 'client_id', 'authority', 'scope'}
    asyncio.run(check())


def test_disabled_and_durable_storage_configuration(monkeypatch):
    monkeypatch.setenv('COUNTERPRESS_STUDIO', 'off')
    snapshots = SnapshotService(ROOT/'fixtures')
    assert configure_studio(snapshots) is None
    monkeypatch.setenv('COUNTERPRESS_STUDIO', 'entra')
    with pytest.raises(ValueError, match='durable'):
        configure_studio(snapshots)


def test_cosmos_etag_retry_rechecks_approval_against_winning_correction():
    container = AtomicContainer()
    first = StudioService(SnapshotService(ROOT/'fixtures', CosmosHistoryStore(container)))
    second = SnapshotService(ROOT/'fixtures', CosmosHistoryStore(container))
    view = first.review('increase', ReviewRequest())
    container.before_batch = lambda: second.ingest('increase', (updates()[0],))
    with pytest.raises(ReviewConflict):
        first.decide('increase', decision(view), ACTOR, 'approve')
    assert not first.snapshots.history('increase').studio_decisions


def test_storage_failure_does_not_leak_diagnostics_or_allow_export(signing_key):
    container = AtomicContainer()
    app = create_app(store=CosmosHistoryStore(container), studio=StudioAccess(verifier(signing_key), CLIENT))
    container.failure = 403
    async def check():
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://test') as client:
            for action in ('review', 'approve', 'export'):
                response = await client.post(f'/api/studio/increase/{action}', json={} if action == 'review' else {'fingerprint': 'a'*64},
                    headers={'Authorization': f'Bearer {token(signing_key)}'})
                assert response.status_code == 503
                assert 'canary' not in response.text
    asyncio.run(check())
