"""Real editor pipeline with synthetic transport; approval is bound to one attempt."""
import asyncio
from time import time

import httpx
import httpx2
import pytest

from counterpress.api.main import create_app
from counterpress.editorial.ledger import Ledger, SQLiteLedgerStore
from counterpress.editorial.service import EditorialController
from counterpress.studio.api import StudioAccess
from counterpress.studio.service import DecisionRequest, ReviewRequest, ReviewConflict
from counterpress.workflow.single_editor import SingleEditorService
from test_studio import services, ACTOR
from test_editorial_controls import signing_key, verifier, token, CLIENT
from test_editorial_evaluation import single_response
from test_history import updates
from test_workflow import CONFIG


def draft(service):
    attempt = asyncio.run(SingleEditorService(service.snapshots, CONFIG,
        transport_factory=lambda: httpx2.MockTransport(single_response)).run('increase', 780000))
    assert attempt.status == 'accepted'
    return attempt


def request(view):
    return DecisionRequest(preferences=view.recap.preferences, fingerprint=view.fingerprint, attempt_id=view.attempt_id)


def test_ai_approval_survives_restart_but_expires_at_exact_boundary(services):
    service = services()
    attempt = draft(service)
    service.now = lambda: attempt.expires_at_unix_ms-1
    req = ReviewRequest(attempt_id=attempt.attempt_id)
    view = service.review('increase', req)
    assert view.workflow.applied and view.valid_for_ms == 1
    approved = service.decide('increase', request(view), ACTOR, 'approve')
    restarted = services(); restarted.now = service.now
    assert restarted.review('increase', req).status == 'approved'
    assert attempt.attempt_id in restarted.export('increase', request(approved))
    restarted.now = lambda: attempt.expires_at_unix_ms
    expired = restarted.review('increase', req)
    assert expired.status == 'unavailable' and not expired.workflow.applied
    assert expired.workflow.status == 'expired' and expired.fingerprint != approved.fingerprint
    for operation in (lambda: restarted.export('increase', request(approved)),
                      lambda: restarted.decide('increase', request(approved), ACTOR, 'approve')):
        with pytest.raises(ReviewConflict): operation()
    assert restarted.review('increase', ReviewRequest()).status != 'approved'


def test_selected_attempt_is_not_replaced_by_another_editor_and_correction_locks_it(services):
    service = services(); first = draft(service)
    view = service.review('increase', ReviewRequest(attempt_id=first.attempt_id))
    service.decide('increase', request(view), ACTOR, 'approve')
    second = draft(service)
    assert first.attempt_id != second.attempt_id
    assert service.review('increase', ReviewRequest(attempt_id=first.attempt_id)).status == 'approved'
    assert service.review('increase', ReviewRequest(attempt_id=second.attempt_id)).status != 'approved'
    service.snapshots.ingest('increase', (updates()[0],))
    changed = service.review('increase', ReviewRequest(attempt_id=first.attempt_id))
    assert changed.workflow.status == 'stale' and changed.status == 'unavailable'
    with pytest.raises(ReviewConflict): service.export('increase', request(view))
    with pytest.raises(ReviewConflict): service.review('increase', ReviewRequest(attempt_id='missing'))


def test_expiry_during_approval_transaction_does_not_authorize(services):
    service = services(); attempt = draft(service)
    view = service.review('increase', ReviewRequest(attempt_id=attempt.attempt_id))
    real = service.snapshots.store.transact
    def transact(scenario, build):
        service.now = lambda: attempt.expires_at_unix_ms
        return real(scenario, build)
    service.snapshots.store.transact = transact
    with pytest.raises(ReviewConflict): service.decide('increase', request(view), ACTOR, 'approve')
    assert not service.snapshots.history('increase').studio_decisions


def test_authenticated_explicit_action_shared_cache_and_no_polling_calls(signing_key, tmp_path):
    from counterpress.api.snapshots import SnapshotService
    from counterpress.history import SQLiteHistoryStore
    from test_studio import ROOT
    store = SQLiteHistoryStore(tmp_path/'studio-ai.sqlite3')
    snapshots = SnapshotService(ROOT/'fixtures', store)
    calls = []
    def respond(r):
        calls.append(1)
        return single_response(r)
    controller = EditorialController(snapshots, CONFIG, Ledger(SQLiteLedgerStore(store.path)),
        transport_factory=lambda: httpx2.MockTransport(respond))
    app = create_app(store=store, editorial=(controller, verifier(signing_key)), studio=StudioAccess(verifier(signing_key), CLIENT))
    async def check():
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://test') as client:
            url = '/api/studio/increase/'
            headers = {'Authorization': f'Bearer {token(signing_key)}'}
            for jwt_token, status in [(None,401),(token(signing_key,roles=[]),403)]:
                r = await client.post(url+'draft', json={'fingerprint':'a'*64}, headers={'Authorization':f'Bearer {jwt_token}'} if jwt_token else {})
                assert r.status_code == status and r.headers['Cache-Control'] == 'no-store'
            v = (await client.post(url+'review',json={},headers=headers)).json()
            assert v['editor_enabled'] and not calls
            assert (await client.post(url+'draft',json={'fingerprint':'a'*64},headers=headers)).status_code == 409
            body={'fingerprint':v['fingerprint']}
            result=(await client.post(url+'draft',json=body,headers=headers)).json()
            assert result['workflow']['applied'] and result['editorial_status']=='completed' and len(calls)==1
            again=(await client.post(url+'draft',json=body,headers=headers)).json()
            assert again['attempt_id']==result['attempt_id'] and again['editorial_status']=='cached' and len(calls)==1
            choice={'attempt_id':result['attempt_id']}
            for _ in range(2):
                assert (await client.post(url+'review',json=choice,headers=headers)).status_code==200
            approved=choice|{'fingerprint':result['fingerprint']}
            assert (await client.post(url+'approve',json=approved,headers=headers)).json()['status']=='approved'
            assert (await client.post(url+'export',json=approved,headers=headers)).status_code==200
            assert len(calls)==1
    asyncio.run(check())
