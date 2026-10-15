import asyncio
from pathlib import Path

from httpx import ASGITransport, AsyncClient
from pydantic import TypeAdapter
import pytest

from counterpress.api.main import create_app
from counterpress.api.snapshots import SnapshotService
from counterpress.audience import ViewingPreferences
from counterpress.domain.models import Event
from counterpress.history import History, SQLiteHistoryStore

ROOT = Path(__file__).resolve().parents[1]


def corrections():
    return TypeAdapter(tuple[Event, ...]).validate_json((ROOT / 'fixtures/pressure/replay_corrections.json').read_text())


def request(app, path):
    async def get():
        async with AsyncClient(transport=ASGITransport(app=app), base_url='http://test') as client:
            return await client.get(path)
    return asyncio.run(get())


def test_seeded_pressure_screen_and_control_have_reviewed_fractions():
    service = SnapshotService(ROOT / 'fixtures')
    positive = service.snapshot('pressure-increase', 780000)
    assert positive.selected_kind == 'pressure' and positive.insight is None
    assert len(positive.pressure_lifecycle) == 2
    d = positive.pressure.publication.decision
    assert (d.baseline_numerator, d.baseline_denominator, d.current_numerator, d.current_denominator) == (3,6,6,6)
    escape = service.snapshot('pressure-increase',780000,preferences=ViewingPreferences(metric_focus='pressured_escape'))
    d = escape.pressure.publication.decision
    assert (d.baseline_numerator,d.baseline_denominator,d.current_numerator,d.current_denominator) == (3,3,1,6)
    assert service.snapshot('pressure-control',780000).selected_kind is None
    before = service.snapshot('pressure-increase',779999)
    assert before.pressure_lifecycle == () and before.pressure.publication is None
    assert before.pressure.state == 'collecting'


def test_independent_revisions_withdraw_restore_and_restart(tmp_path):
    db = tmp_path / 'history.sqlite3'
    service = SnapshotService(ROOT / 'fixtures', SQLiteHistoryStore(db))
    original = service.snapshot('pressure-increase',780000)
    initial = service.history('pressure-increase')
    updated = service.ingest('pressure-increase',corrections())
    assert [(c.metric,c.operation,c.revision) for c in updated.pressure_changes] == [
        ('pressure_exposure','create',1),('pressured_escape','create',1),
        ('pressure_exposure','update',2),('pressured_escape','withdraw',2),
        ('pressure_exposure','withdraw',3),('pressure_exposure','create',4),('pressured_escape','create',3)]
    assert service.ingest('pressure-increase',corrections()) == updated
    restarted = SnapshotService(tmp_path/'missing-fixtures',SQLiteHistoryStore(db))
    assert restarted.snapshot('pressure-increase',780000).pressure == original.pressure
    assert restarted.snapshot('pressure-increase',785000).pressure.publication.revision == 2
    withdrawn = restarted.snapshot('pressure-increase',790000)
    assert withdrawn.selected_kind is None and withdrawn.pressure.publication is None
    assert all(c.operation == 'withdraw' for c in withdrawn.pressure_lifecycle)
    restored = restarted.snapshot('pressure-increase',795000)
    assert restored.pressure.publication.revision == 4 and restored.pressure.publication.invalidates == (3,)
    assert initial.records == updated.records[:len(initial.records)]
    assert updated.pressure_version == len(updated.records)


def test_evidence_endpoint_is_id_version_and_cutoff_scoped():
    app = create_app()
    service = app.state.snapshots
    initial = service.snapshot('pressure-increase',780000)
    exposure, escape = initial.pressure_lifecycle
    service.ingest('pressure-increase',corrections())
    base = f'/api/scenarios/pressure-increase/pressure/{exposure.insight_id}/evidence/'
    assert request(app,base+'2?at_ms=780000').status_code == 404
    response = request(app,base+'2?at_ms=785000')
    assert response.status_code == 200 and response.headers['cache-control'] == 'no-store'
    assert response.json()['evidence']['baseline']['exposed'] == 2
    assert request(app,base+'3?at_ms=790000').json()['operation'] == 'withdraw'
    other = request(app,f'/api/scenarios/pressure-increase/pressure/{escape.insight_id}/evidence/2?at_ms=785000').json()
    assert other['operation'] == 'withdraw' and other['decision']['status'] == 'insufficient_sample'
    assert request(app,base+'1?at_ms=999999').status_code == 404


@pytest.mark.parametrize('language',['en','zh-Hans'])
@pytest.mark.parametrize('depth',['analyst','casual'])
def test_language_depth_and_actual_player_involvement_preserve_rates(language,depth):
    service = SnapshotService(ROOT / 'fixtures')
    prefs = ViewingPreferences(language=language,depth=depth,player_id='eb04',metric_focus='pressured_escape')
    value = service.snapshot('pressure-increase',780000,preferences=prefs)
    assert value.selected_kind == 'pressure'
    assert value.pressure.variant.language == language and value.pressure.variant.depth == depth
    assert '3/3' in value.pressure.variant.explanation and '1/6' in value.pressure.variant.explanation
    by_id = {event.event_id:event for event in value.pressure.publication.evidence.records}
    assert all(by_id[ref.event_id].actor.player_id == 'eb04' for ref in value.pressure.highlighted_events)
    missing = service.snapshot('pressure-increase',780000,preferences=prefs.model_copy(update={'player_id':'eb08'}))
    assert missing.selected_kind is None and missing.pressure.state == 'no_contribution'
    hidden = service.snapshot('pressure-increase',780000,preferences=prefs.model_copy(update={'card_budget':0}))
    assert hidden.selected_kind is None and hidden.pressure.publication is None


def test_backfill_legacy_history_preserves_other_streams_and_is_idempotent(tmp_path):
    seed = SnapshotService(ROOT / 'fixtures').history('pressure-increase')
    store = SQLiteHistoryStore(tmp_path/'old.sqlite3')
    legacy = History(fixture=seed.fixture,records=seed.records+corrections())
    store.transact('pressure-increase',lambda _:legacy)
    service = SnapshotService(tmp_path/'no-fixtures',store)
    backfilled = service.history('pressure-increase')
    assert len(backfilled.pressure_changes) == 7
    assert backfilled.records == legacy.records and backfilled.changes == legacy.changes
    assert service.history('pressure-increase') == backfilled
    assert service.snapshot('pressure-increase',790000).selected_kind is None


def test_atomic_rejection_keeps_pressure_and_source_ledger_unchanged(tmp_path):
    service = SnapshotService(ROOT/'fixtures',SQLiteHistoryStore(tmp_path/'state.sqlite3'))
    before = service.history('pressure-increase')
    good = corrections()[0]
    invalid = good.model_copy(update={'event_id':'b1-start','occurrence_order':2,'source_delivery_sequence':999})
    with pytest.raises(ValueError):
        service.ingest('pressure-increase',(good,invalid))
    assert service.history('pressure-increase') == before
    with pytest.raises(ValueError,match='rewritten'):
        service.store.transact('pressure-increase',lambda history:history.model_copy(update={'pressure_changes':()}))


def test_api_two_viewers_and_budget_cannot_change_authoritative_evidence():
    app=create_app()
    a=request(app,'/api/scenarios/pressure-increase/snapshot?at_ms=780000&scope_id=a&metric_focus=pressure_exposure').json()
    b=request(app,'/api/scenarios/pressure-increase/snapshot?at_ms=780000&scope_id=b&metric_focus=pressured_escape&language=zh-Hans&depth=casual').json()
    assert a['pressure_lifecycle'] == b['pressure_lifecycle']
    assert a['pressure']['publication']['metric'] == 'pressure_exposure'
    assert b['pressure']['publication']['metric'] == 'pressured_escape'
    assert a['scope_id'] != b['scope_id']
    assert request(app,'/api/scenarios/pressure-increase/snapshot?at_ms=780000&player_id=unknown').status_code == 422


def test_one_card_budget_ranks_recovery_and_pressure_together():
    from counterpress.api.snapshots import END, project
    from counterpress.generator.engine import generate
    from counterpress.generator.suite import profile
    feed=generate(profile(2)).feed
    service=SnapshotService(ROOT/'fixtures')
    service.store.transact('increase',lambda _:project(History(fixture=feed,records=feed.events),END))
    balanced=service.snapshot('increase',780000)
    assert balanced.selected_kind == 'recovery' and balanced.pressure.state == 'ready'
    focused=service.snapshot('increase',780000,preferences=ViewingPreferences(metric_focus='pressure_exposure'))
    assert focused.selected_kind == 'pressure'
    hidden=service.snapshot('increase',780000,preferences=ViewingPreferences(card_budget=0))
    assert hidden.selected_kind is None
