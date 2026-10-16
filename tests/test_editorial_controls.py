import asyncio
from concurrent.futures import ThreadPoolExecutor
from types import SimpleNamespace
from time import time

from cryptography.hazmat.primitives.asymmetric import rsa
import httpx
import httpx2
import jwt
import pytest

from counterpress.api.main import create_app
from counterpress.api.snapshots import SnapshotService
from counterpress.audience import ViewingPreferences
from counterpress.cosmos_history import CosmosHistoryStore
from counterpress.editorial.auth import AccessDenied, EntraSettings, EntraVerifier
from counterpress.editorial.api import configure_editorial
from counterpress.editorial.ledger import CosmosLedgerStore, Ledger, Limits, SQLiteLedgerStore
from counterpress.editorial.service import AdmittedTransport, EditorialController, EditorialRequest
from counterpress.history import HistoryStorageError
from counterpress.adaptation.azure import ProviderFailure
from test_cosmos_history import AtomicContainer
from test_editorial_evaluation import single_response
from test_history import updates
from test_recap_workflow import ROOT, snapshots
from test_workflow import CONFIG

TENANT = '11111111-1111-4111-8111-111111111111'
AUDIENCE = '22222222-2222-4222-8222-222222222222'
CLIENT = '33333333-3333-4333-8333-333333333333'
OBJECT = '44444444-4444-4444-8444-444444444444'
SETTINGS = EntraSettings(TENANT, AUDIENCE, (CLIENT,))


@pytest.fixture(scope='module')
def signing_key():
    return rsa.generate_private_key(public_exponent=65537, key_size=2048)


def verifier(key):
    return EntraVerifier(SETTINGS, SimpleNamespace(get_signing_key_from_jwt=lambda token: SimpleNamespace(key=key.public_key())))


def token(key, **changes):
    now = int(time())
    claims = dict(iss=SETTINGS.issuer, aud=AUDIENCE, tid=TENANT, azp=CLIENT, oid=OBJECT,
                  ver='2.0', iat=now, nbf=now-1, exp=now+60, scp='Editorial.Run', roles=['CounterPress.Editor'])
    claims.update(changes)
    return jwt.encode(claims, key, algorithm='RS256', headers={'kid': 'test-key'})


@pytest.mark.parametrize('changes,status', [
    ({'aud': CLIENT}, 401), ({'iss': 'https://invalid.example'}, 401),
    ({'tid': CLIENT}, 401), ({'ver': '1.0'}, 401), ({'exp': 1}, 401),
    ({'nbf': 9999999999}, 401), ({'oid': 'missing-object'}, 401),
    ({'azp': AUDIENCE}, 403), ({'scp': None}, 403),
    ({'scp': 'Editorial.Read'}, 403), ({'roles': []}, 403),
    ({'roles': 'CounterPress.Editor'}, 403),
])
def test_entra_rejects_wrong_identity_lifetime_client_scope_or_role(signing_key, changes, status):
    with pytest.raises(AccessDenied) as exc:
        verifier(signing_key).verify(token(signing_key, **changes))
    assert exc.value.status == status


def test_entra_checks_signature_algorithm_and_stable_private_actor(signing_key):
    auth = verifier(signing_key)
    actor = auth.verify(token(signing_key))
    assert len(actor) == 64 and OBJECT not in actor
    assert actor == auth.verify(token(signing_key, name='Changed display name'))
    forged_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    for bad in (token(forged_key), jwt.encode({'roles': ['CounterPress.Editor']}, '', algorithm='none'), 'x'*16385):
        with pytest.raises(AccessDenied):
            auth.verify(bad)


def test_unavailable_signing_keys_fail_closed(signing_key):
    def unavailable(token):
        raise jwt.PyJWKClientConnectionError('private diagnostic')
    auth = EntraVerifier(SETTINGS, SimpleNamespace(get_signing_key_from_jwt=unavailable))
    with pytest.raises(AccessDenied) as exc:
        auth.verify(token(signing_key))
    assert exc.value.status == 503


@pytest.fixture(params=['sqlite', 'cosmos'])
def ledger_factory(request, tmp_path):
    if request.param == 'cosmos':
        container = AtomicContainer()
        return lambda limits=Limits(): Ledger(CosmosLedgerStore(container), limits)
    return lambda limits=Limits(): Ledger(SQLiteLedgerStore(tmp_path/'controls.sqlite3'), limits)


def test_shared_lease_cache_and_crash_recovery_survive_restart(ledger_factory):
    first, second = ledger_factory(), ledger_factory()
    status, job = first.reserve('key', 'editor-a', 1000)
    assert status == 'reserved'
    assert second.reserve('key', 'editor-b', 1001)[0] == 'pending'
    assert second.dispatch('key', job.owner, 1002)
    assert not first.dispatch('key', job.owner, 1003)
    status, new = second.reserve('key', 'editor-b', 31000)
    assert status == 'reserved' and new.owner != job.owner
    assert not first.dispatch('key', job.owner, 31001)
    first.finish('key', job.owner, 31001)
    assert second.reserve('key', 'editor-a', 31002)[0] == 'pending'
    second.finish('key', new.owner, 31002)
    assert ledger_factory().reserve('key', 'editor-c', 31003)[0] == 'cached'


def test_lifetime_quota_has_no_refunds_or_daily_reset(ledger_factory):
    limits = Limits(lifetime=2, daily=2, per_editor_daily=1)
    ledger = ledger_factory(limits)
    _, job = ledger.reserve('a', 'one', 1000)
    ledger.finish('a', job.owner, 1001)
    assert ledger.reserve('b', 'one', 1002)[0] == 'quota_exceeded'
    assert ledger.reserve('b', 'two', 1002)[0] == 'reserved'
    assert ledger_factory(limits).reserve('c', 'three', 86401000)[0] == 'quota_exceeded'
    with pytest.raises(HistoryStorageError, match='policy'):
        ledger_factory().reserve('d', 'four', 86401000)


def test_distinct_contexts_share_global_concurrency_limit(ledger_factory):
    ledger = ledger_factory()
    assert ledger.reserve('a', 'one', 0)[0] == 'reserved'
    assert ledger.reserve('b', 'two', 0)[0] == 'reserved'
    assert ledger_factory().reserve('c', 'three', 0)[0] == 'busy'
    assert ledger_factory().reserve('c', 'three', 30000)[0] == 'reserved'


def test_daily_quota_is_shared_between_editors_and_utc_reset_is_bounded(ledger_factory):
    limits = Limits(daily=1)
    ledger = ledger_factory(limits)
    _, job = ledger.reserve('a', 'one', 1000)
    ledger.finish('a', job.owner, 1001)
    assert ledger_factory(limits).reserve('b', 'two', 1002)[0] == 'quota_exceeded'
    assert ledger_factory(limits).reserve('b', 'two', 86401000)[0] == 'reserved'


def test_sqlite_writers_atomically_deduplicate_across_connections(tmp_path):
    def reserve(_):
        return Ledger(SQLiteLedgerStore(tmp_path/'concurrent.sqlite3')).reserve('same', 'actor', 1000)[0]
    with ThreadPoolExecutor(max_workers=8) as pool:
        statuses = list(pool.map(reserve, range(8)))
    assert statuses.count('reserved') == 1 and statuses.count('pending') == 7


def test_cosmos_conflicting_reservation_rebuilds_from_winner_and_fails_closed():
    container = AtomicContainer()
    first, second = Ledger(CosmosLedgerStore(container)), Ledger(CosmosLedgerStore(container))
    container.before_batch = lambda: second.reserve('same', 'other', 1000)
    assert first.reserve('same', 'actor', 1000)[0] == 'pending'
    container.failure = 503
    with pytest.raises(HistoryStorageError):
        first.reserve('new', 'actor', 1000)


def controller(app, ledger, handler=single_response, **kwargs):
    return EditorialController(app, CONFIG, ledger,
        transport_factory=lambda: httpx2.MockTransport(handler), poll_seconds=.01, **kwargs)


async def request_for(control, scenario='increase', at=780000, prefs=ViewingPreferences()):
    context = await control.context(scenario, at, prefs)
    return EditorialRequest(at_ms=at, preferences=prefs, fingerprint=context.fingerprint)


@pytest.mark.parametrize('cloud', [False, True])
def test_success_and_cached_presentation_survive_fresh_store(tmp_path, cloud):
    container = AtomicContainer()
    def fresh():
        app = SnapshotService(ROOT/'fixtures', CosmosHistoryStore(container)) if cloud else snapshots(tmp_path/'app.sqlite3')
        ledger = Ledger(CosmosLedgerStore(container) if cloud else SQLiteLedgerStore(tmp_path/'app.sqlite3'))
        return controller(app, ledger, handler)
    calls = []
    def handler(r):
        calls.append(r)
        return single_response(r)
    async def exercise():
        control = fresh()
        req = await request_for(control)
        result = await control.run('increase', req, 'editor')
        assert result.status == 'completed' and result.workflow.applied
        restarted = await fresh().run('increase', req, 'another-editor')
        assert restarted.status == 'cached' and restarted.recap == result.recap
        assert len(calls) == 1
        context = await fresh().context('increase', 780000, ViewingPreferences(language='zh-Hans'))
        assert context.fingerprint != req.fingerprint
    asyncio.run(exercise())


def test_concurrent_explicit_requests_share_one_provider_call(tmp_path):
    async def exercise():
        entered, release = asyncio.Event(), asyncio.Event()
        calls = []
        async def handler(r):
            calls.append(r); entered.set()
            await release.wait()
            return single_response(r)
        control = controller(snapshots(tmp_path/'app.sqlite3'), Ledger(SQLiteLedgerStore(tmp_path/'app.sqlite3')), handler)
        other = controller(snapshots(tmp_path/'app.sqlite3'), Ledger(SQLiteLedgerStore(tmp_path/'app.sqlite3')), handler)
        req = await request_for(control)
        task = asyncio.create_task(control.run('increase', req, 'editor'))
        await asyncio.wait_for(entered.wait(), 3)
        try:
            assert (await other.run('increase', req, 'other')).status == 'pending'
        finally:
            release.set()
        assert (await task).status == 'completed'
        assert len(calls) == 1
    asyncio.run(exercise())


def test_expiry_and_changed_preferences_require_new_bounded_admission(tmp_path):
    calls, now = [], [int(time()*1000)]
    def handler(r):
        calls.append(r)
        return single_response(r)
    async def exercise():
        control = controller(snapshots(), Ledger(SQLiteLedgerStore(tmp_path/'control.sqlite3')), handler, now=lambda: now[0])
        english = await request_for(control)
        assert (await control.run('increase', english, 'editor')).status == 'completed'
        chinese = await request_for(control, prefs=ViewingPreferences(language='zh-Hans'))
        result = await control.run('increase', chinese, 'editor')
        assert result.status == 'completed' and result.recap.preferences.language == 'zh-Hans'
        assert (await control.run('increase', english, 'other')).status == 'cached'
        now[0] += 61000
        assert (await control.run('increase', english, 'editor')).status == 'completed'
        assert len(calls) == 3
    asyncio.run(exercise())


def test_revision_change_after_admission_and_dispatch_storage_failure_are_free(tmp_path):
    calls = []
    def handler(r):
        calls.append(r)
        return single_response(r)
    async def exercise():
        app = snapshots()
        ledger = Ledger(SQLiteLedgerStore(tmp_path/'control.sqlite3'))
        control = controller(app, ledger, handler)
        req = await request_for(control)
        reserve = ledger.reserve
        def correcting_reserve(*args):
            result = reserve(*args)
            app.ingest('increase', updates())
            return result
        ledger.reserve = correcting_reserve
        assert (await control.run('increase', req, 'editor')).status == 'stale'
        ledger.reserve = reserve
        def failed_dispatch(*args):
            raise HistoryStorageError('private diagnostic')
        ledger.dispatch = failed_dispatch
        latest = await request_for(control, at=795000)
        assert (await control.run('increase', latest, 'editor')).status == 'fallback'
        assert not calls
    asyncio.run(exercise())


def test_correction_cancels_pending_provider_and_invalidates_cached_output(tmp_path):
    async def exercise():
        entered, cancelled = asyncio.Event(), asyncio.Event()
        async def pending(r):
            entered.set()
            try:
                await asyncio.Event().wait()
            finally:
                cancelled.set()
        app = snapshots(tmp_path/'app.sqlite3')
        ledger = Ledger(SQLiteLedgerStore(tmp_path/'app.sqlite3'))
        control = controller(app, ledger, pending)
        req = await request_for(control)
        task = asyncio.create_task(control.run('increase', req, 'editor'))
        await asyncio.wait_for(entered.wait(), 3)
        app.ingest('increase', updates())
        result = await asyncio.wait_for(task, 3)
        assert result.status == 'stale' and cancelled.is_set()
        assert result.workflow is None
        assert app.snapshot('increase', 795000).adapted_recap is None
        assert (await control.run('increase', req, 'editor')).status == 'stale'
        # A new request at the new revision can be admitted independently.
        fresh = controller(app, ledger)
        latest = await request_for(fresh, at=795000)
        assert (await fresh.run('increase', latest, 'editor')).status == 'completed'
        assert (await fresh.run('increase', req, 'editor')).status == 'stale'
    asyncio.run(exercise())


def test_cancelled_request_keeps_reservation_and_cools_down(tmp_path):
    async def exercise():
        entered = asyncio.Event()
        async def pending(r):
            entered.set()
            await asyncio.Event().wait()
        store = SQLiteLedgerStore(tmp_path/'control.sqlite3')
        control = controller(snapshots(), Ledger(store), pending)
        req = await request_for(control)
        task = asyncio.create_task(control.run('increase', req, 'editor'))
        await asyncio.wait_for(entered.wait(), 3)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        assert (await control.run('increase', req, 'editor')).status == 'cached'
        state = store.transact(lambda state: state)
        assert state.admitted == 1
        assert next(iter(state.jobs.values())).dispatched
    asyncio.run(exercise())


def test_ineligible_old_context_and_unavailable_ledger_never_call_provider(tmp_path):
    calls = []
    def handler(r):
        calls.append(r)
        return single_response(r)
    async def exercise():
        control = controller(snapshots(), Ledger(SQLiteLedgerStore(tmp_path/'control.sqlite3')), handler)
        req = await request_for(control, at=540000)
        assert (await control.run('increase', req, 'editor')).status == 'ineligible'
        req = await request_for(control)
        assert (await control.run('increase', req.model_copy(update={'fingerprint': '0'*64}), 'editor')).status == 'stale'
        class Broken:
            def transact(self, build):
                raise HistoryStorageError('unavailable')
        control.ledger = Ledger(Broken())
        with pytest.raises(HistoryStorageError):
            await control.run('increase', req, 'editor')
        assert not calls
    asyncio.run(exercise())


def test_transport_bounds_and_lost_lease_prevent_dispatch(tmp_path):
    async def exercise():
        calls = []
        control = controller(snapshots(), Ledger(SQLiteLedgerStore(tmp_path/'control.sqlite3')))
        req = await request_for(control)
        transport = AdmittedTransport(control, 'increase', req, 'unreserved', 'owner',
            httpx2.MockTransport(lambda r: calls.append(r)))
        for body in ({'max_tokens': 651}, {'max_tokens': True}, {'max_tokens': 650, 'stream': True},
                     {'max_tokens': 650, 'padding': 'x'*65536}, {'max_tokens': 650}):
            with pytest.raises(ProviderFailure):
                await transport.handle_async_request(httpx2.Request('POST', CONFIG.url, json=body))
        assert not calls
    asyncio.run(exercise())


def test_http_authentication_private_headers_explicit_trigger_and_public_reads(signing_key, tmp_path):
    calls = []
    def handler(r):
        calls.append(r)
        return single_response(r)
    control = controller(snapshots(tmp_path/'app.sqlite3'), Ledger(SQLiteLedgerStore(tmp_path/'app.sqlite3')), handler)
    application = create_app(store=control.snapshots.store, editorial=(control, verifier(signing_key)))
    async def exercise():
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=application), base_url='http://test') as client:
            payload = {'at_ms': 780000}
            path = '/api/editorial/increase/'
            response = await client.post(path+'context', json=payload, headers={'X-MS-CLIENT-PRINCIPAL': 'forged'})
            assert response.status_code == 401 and response.headers['cache-control'] == 'no-store'
            response = await client.post(path+'context', json=payload, headers={'Authorization': 'Bearer '+token(signing_key, roles=[])})
            assert response.status_code == 403
            headers = {'Authorization': 'Bearer '+token(signing_key)}
            response = await client.post(path+'context', json=payload, headers=headers)
            assert response.status_code == 200 and not calls
            payload['fingerprint'] = response.json()['fingerprint']
            for path_read in ('/health', '/ready', '/api/scenarios/increase/snapshot?at_ms=780000'):
                assert (await client.get(path_read)).status_code == 200
            assert not calls
            response = await client.post(path+'run', json=payload, headers=headers)
            assert response.status_code == 200 and response.json()['status'] == 'completed'
            assert len(calls) == 1 and response.headers['referrer-policy'] == 'no-referrer'
            assert (await client.post(path+'run', json=payload, headers=headers)).json()['status'] == 'cached'
            assert len(calls) == 1
            invalid = await client.post(path+'run', json=payload | {'free_text': 'invent facts'}, headers=headers)
            assert invalid.status_code == 422
    asyncio.run(exercise())


def test_disabled_and_incomplete_configuration_fails_closed(monkeypatch):
    monkeypatch.setenv('COUNTERPRESS_EDITORIAL', 'off')
    assert configure_editorial(snapshots()) is None
    async def exercise():
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=create_app()), base_url='http://test') as client:
            response = await client.post('/api/editorial/increase/run', json={})
            assert response.status_code == 503
    asyncio.run(exercise())
    monkeypatch.setenv('COUNTERPRESS_EDITORIAL', 'entra')
    with pytest.raises(ValueError, match='Entra'):
        configure_editorial(snapshots())


def test_http_quota_stale_and_storage_failure_preserve_factual_response(signing_key, tmp_path):
    store = SQLiteLedgerStore(tmp_path/'controls.sqlite3')
    control = controller(snapshots(), Ledger(store, Limits(lifetime=1)))
    application = create_app(store=control.snapshots.store, editorial=(control, verifier(signing_key)))
    async def exercise():
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=application), base_url='http://test') as client:
            headers = {'Authorization': 'Bearer '+token(signing_key)}
            req = (await request_for(control)).model_dump(mode='json')
            path = '/api/editorial/increase/run'
            assert (await client.post(path, json=req, headers=headers)).status_code == 200
            response = await client.post(path, json=req | {'fingerprint': '0'*64}, headers=headers)
            assert response.status_code == 409 and response.json()['recap']['statements']
            chinese = (await request_for(control, prefs=ViewingPreferences(language='zh-Hans'))).model_dump(mode='json')
            response = await client.post(path, json=chinese, headers=headers)
            assert response.status_code == 429 and response.json()['status'] == 'quota_exceeded'
            assert response.json()['workflow'] is None and response.json()['recap']['statements']
            def broken(build):
                raise HistoryStorageError('private diagnostic')
            store.transact = broken
            response = await client.post(path, json=chinese, headers=headers)
            assert response.status_code == 503 and 'private diagnostic' not in response.text
            assert response.headers['cache-control'] == 'no-store'
    asyncio.run(exercise())
