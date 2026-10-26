"""Independent event examples for trailing, causal and replaceable observations."""
from contextlib import nullcontext
from pathlib import Path
from types import SimpleNamespace

from fastapi import FastAPI
from fastapi.testclient import TestClient
import pytest

from counterpress.fan.api import install_fan
from counterpress.fan.contracts import FanPreferences, MatchRequest
from counterpress.fan.observations import rolling_observations
from counterpress.fan.service import FanService, PreferenceError
from counterpress.personalization.contracts import Action, Appearance, Fixture
from counterpress.personalization.service import CareerService
from counterpress.personalization.store import DataStore


def fixture(source='calibrated_simulation'):
    return Fixture(match_id='test-match', season='2026-27', kickoff='2026-10-19T15:00:00Z',
        home_id='home', away_id='away', competition='Test', source_kind=source,
        appearances=tuple(Appearance(player_id=p, club_id=c, start_ms=0, end_ms=5400000, starter=True)
            for p, c in [('h1', 'home'), ('h2', 'home'), ('a1', 'away')]))


def event(i, ms, kind='pass', **updates):
    return Action(**(dict(match_id='test-match', event_id=f'e{i}', revision=1,
        delivery_sequence=i, occurrence_order=i, period=1, elapsed_ms=ms,
        available_period=1, available_ms=ms, club_id='home', player_id='h1',
        kind=kind, outcome='complete' if kind == 'pass' else 'off_target',
        source_reference=f'test:e{i}') | updates))


def shots():
    # Exact cutoff 7:01. Earlier window (1:01,4:01] has one shot; current
    # window (4:01,7:01] has three. Five on-ball events in each window.
    return [event(1, 62000), event(2, 100000), event(3, 130000), event(4, 200000),
        event(5, 241000, 'shot'), event(6, 242000), event(7, 300000),
        event(8, 350000, 'shot'), event(9, 400000, 'shot'), event(10, 421000, 'shot')]


def passing():
    # Ten passes each: 10/10 before, 6/10 after. No percentage is obtained
    # from the system under test when writing these expected values.
    return [event(i + 1, 70000 + i * 15000) for i in range(10)] + [
        event(i + 11, 250000 + i * 15000, outcome='complete' if i < 6 else 'incomplete') for i in range(10)]


def observe(events=None, cutoff=(1, 421000), preferences=None, source='calibrated_simulation'):
    return rolling_observations(fixture(source), shots() if events is None else events,
        cutoff=cutoff, preferences=preferences or FanPreferences(),
        club_names={'home': 'Eastbridge', 'away': 'Northport'},
        player_names={'h1': 'Alex Finch', 'h2': 'Ben Reed', 'a1': 'Cole Stone'})


def fake_career(events):
    f = fixture()
    store = SimpleNamespace(
        clubs={cid: SimpleNamespace(name=name) for cid, name in [('home', 'Eastbridge'), ('away', 'Northport')]},
        players={pid: SimpleNamespace(name=name) for pid, name in [('h1', 'Alex Finch'), ('h2', 'Ben Reed'), ('a1', 'Cole Stone')]},
        manifest={'files': {'ledger.json.gz': 'test-ledger'}},
        row=lambda mid: {'fixture': f.model_dump_json()} if mid == f.match_id else {} ,
        events=lambda mid: events,
        snapshot=nullcontext)
    return SimpleNamespace(store=store)


def test_true_trailing_windows_and_inclusive_end_exclusive_start():
    result = observe(shots() + [event(11, 61000, 'shot'), event(12, 421001, 'shot')])[0]
    assert result['kind'] == 'shots_increase'
    assert result['metrics'] == {'metric': 'shots', 'before': 1, 'after': 3,
        'unit': 'count', 'sample_sizes': [5, 5]}
    assert result['windows'] == [
        {'period': 1, 'start_ms': 61000, 'end_ms': 241000, 'boundary': '(start,end]'},
        {'period': 1, 'start_ms': 241000, 'end_ms': 421000, 'boundary': '(start,end]'}]
    assert result['text'] == 'Eastbridge have taken 3 shots in the last 3 minutes, up from 1 in the previous 3.'
    assert {e['event_id'] for e in result['evidence']} == {f'e{i}' for i in range(1, 11)}
    assert observe(cutoff=(1, 420999)) == []


def test_delayed_outcome_does_not_leak_at_occurrence():
    rows = shots()
    rows[-1] = rows[-1].model_copy(update={'available_ms': 421500})
    assert observe(rows) == []
    assert observe(rows, cutoff=(1, 421500))[0]['metrics']['after'] == 3


def test_backwards_seek_withdraws_and_duplicate_deliveries_are_idempotent():
    current = observe()
    assert observe(shots() + shots()) == current
    assert observe(cutoff=(1, 350000)) == []
    assert observe() == current


def test_retraction_correction_and_restore_change_only_visible_snapshot():
    rows = shots() + [event(11, 70000), event(12, 350001)]
    original = rows[8]
    retract = original.model_copy(update={'revision': 2, 'delivery_sequence': 13,
        'available_ms': 422000, 'retracted': True})
    restore = retract.model_copy(update={'revision': 3, 'delivery_sequence': 14,
        'available_ms': 423000, 'retracted': False})
    assert observe(rows + [retract, restore]) == observe(rows)
    assert observe(rows + [retract, restore], cutoff=(1, 422000)) == []
    restored = observe(rows + [retract, restore], cutoff=(1, 423000))[0]
    assert restored['id'] == observe()[0]['id']
    assert restored['fingerprint'] != observe()[0]['fingerprint']
    assert next(e for e in restored['evidence'] if e['event_id'] == original.event_id)['revision'] == 3
    corrected = original.model_copy(update={'revision': 2, 'delivery_sequence': 13,
        'available_ms': 421000, 'kind': 'pass', 'outcome': 'complete'})
    assert observe(rows + [corrected]) == []


def test_expired_shots_leave_window_instead_of_retaining_old_card():
    assert observe(cutoff=(1, 600000)) == []


@pytest.mark.parametrize('cutoff', [(1, 0), (1, 359999), (2, 0), (2, 300000)])
def test_no_partial_windows_or_halftime_bleed(cutoff):
    assert observe(cutoff=cutoff) == []


def test_second_half_uses_its_own_observations():
    rows = shots()
    second = [e.model_copy(update={'event_id': e.event_id + '-second', 'period': 2,
        'available_period': 2, 'delivery_sequence': e.delivery_sequence + 20,
        'occurrence_order': e.occurrence_order + 20}) for e in rows]
    assert observe(rows, cutoff=(2, 421000)) == []
    result = observe(rows + second, cutoff=(2, 421000))[0]
    assert result['metrics']['before'] == 1 and result['metrics']['after'] == 3
    assert {e['period'] for e in result['evidence']} == {2}


def test_sparse_and_no_change_windows_say_nothing():
    assert observe(shots()[1:]) == []
    assert observe([e.model_copy(update={'kind': 'pass', 'outcome': 'complete'}) for e in shots()]) == []


def test_own_goals_do_not_count_as_attempted_shots():
    rows = shots()
    rows[-1] = rows[-1].model_copy(update={'outcome': 'own_goal', 'goal_for': 'away'})
    assert observe(rows) == []


def test_passing_rate_requires_complete_outcomes_and_minimum_denominators():
    row = observe(passing())[0]
    assert row['kind'] == 'passing_decline'
    assert row['metrics'] == {'metric': 'pass_completion_pct', 'before': 100.0, 'after': 60.0,
        'unit': 'percent', 'completed': [10, 6], 'attempted': [10, 10], 'sample_sizes': [10, 10]}
    assert observe(passing()[1:]) == []
    for i in (0, -1):
        rows = passing()
        rows[i] = rows[i].model_copy(update={'outcome': 'unknown'})
        assert observe(rows) == []


def test_passing_threshold_is_not_triggered_by_small_change_or_improvement():
    rows = passing()
    for i in range(16, 19):
        rows[i] = rows[i].model_copy(update={'outcome': 'complete'})
    assert observe(rows) == []  # 100% -> 90%, below 15 percentage points.
    reversed_rates = [e.model_copy(update={'outcome': 'incomplete' if i < 5 else 'complete'}) for i, e in enumerate(passing())]
    assert observe(reversed_rates) == []


def test_only_followed_player_actor_actions_create_player_observation():
    rows = [e.model_copy(update={'player_id': 'h2' if i < 5 else 'h1'}) for i, e in enumerate(shots())]
    assert [r['kind'] for r in observe(rows)] == ['shots_increase']
    selected = observe(rows, preferences=FanPreferences(favorite_player_ids=['h1']))
    assert selected[0]['kind'] == 'player_involvement'
    assert selected[0]['metrics'] == {'metric': 'recorded_on_ball_actions', 'before': 0,
        'after': 5, 'unit': 'count', 'sample_sizes': [5, 5]}
    assert selected[0]['player_id'] == 'h1'
    assert not any(r['kind'] == 'player_involvement' for r in observe(rows, preferences=FanPreferences(favorite_player_ids=['a1'])))


def test_favorites_language_and_depth_change_identity_not_football_counts():
    english = observe()[0]
    chinese = observe(preferences=FanPreferences(language='zh-Hans', depth='analyst', favorite_club_ids=['home']))[0]
    assert chinese['id'] == english['id']
    assert chinese['metrics'] == english['metrics'] and chinese['evidence'] == english['evidence']
    assert chinese['fingerprint'] != english['fingerprint']
    assert chinese['priority'] > english['priority']
    assert '最近3分钟' in chinese['text']


@pytest.mark.parametrize('source', ['adapted_archive', 'legacy_simulation', 'calibrated_simulation'])
def test_shot_and_pass_counts_are_supported_across_source_types(source):
    assert observe(source=source)[0]['metrics']['after'] == 3
    assert observe(passing(), source=source)[0]['metrics']['after'] == 60.0


def test_conflicting_revisions_and_cross_match_evidence_are_rejected():
    with pytest.raises(ValueError, match='Conflicting'):
        observe(shots() + [shots()[0].model_copy(update={'outcome': 'incomplete'})])
    with pytest.raises(ValueError, match='another match'):
        observe([shots()[0].model_copy(update={'match_id': 'another-match'})])


def test_service_returns_delivery_pin_and_applies_budget_without_inference():
    rows = shots()
    late = rows[-1].model_copy(update={'revision': 2, 'delivery_sequence': 11, 'available_ms': 421000, 'retracted': True})
    fan = FanService(fake_career(rows + [late]))
    request = MatchRequest(cutoff={'period': 1, 'elapsed_ms': 421000}, through_sequence=10)
    pinned = fan.observations('test-match', request)
    assert pinned['through_sequence'] == 10
    assert pinned['observations'][0]['metrics']['after'] == 3
    current = fan.observations('test-match', request.model_copy(update={'through_sequence': None}))
    assert current['through_sequence'] == 11 and current['observations'] == []
    assert fan.observations('test-match', request.model_copy(update={'card_budget': 0}))['observations'] == []
    assert fan.observations('test-match', request.model_copy(update={'through_sequence': 0}))['observations'] == []
    with pytest.raises(PreferenceError, match='ahead of received'):
        fan.observations('test-match', request.model_copy(update={'through_sequence': 12}))


def test_api_validates_preference_cutoff_and_private_snapshot_contract():
    app = FastAPI()
    career = fake_career(shots())
    install_fan(app, lambda: career)
    client = TestClient(app)
    url = '/api/fan/matches/test-match/observations'
    body = {'cutoff': {'period': 1, 'elapsed_ms': 421000}}
    response = client.post(url, json=body)
    assert response.status_code == 200
    assert response.headers['cache-control'] == 'private, no-store'
    assert response.json()['observations'][0]['metrics']['after'] == 3
    assert client.post(url, json={'cutoff': {'period': 1, 'elapsed_ms': 2700001}}).status_code == 422
    assert client.post(url, json={'cutoff': {'period': True, 'elapsed_ms': 421000}}).status_code == 422
    assert client.post(url, json=body | {'preferences': {'favorite_player_ids': ['not-a-player']}}).status_code == 422
    assert client.post(url, json=body | {'through_sequence': 11}).status_code == 422
    assert client.post('/api/fan/matches/missing/observations', json=body).status_code == 404


def test_canonical_matches_observations_only_use_visible_same_period_evidence():
    store = DataStore(Path(__file__).resolve().parents[1] / 'fixtures/personalization')
    try:
        fan = FanService(CareerService(store))
        for match in store.rows(featured=True):
            for period in (1, 2):
                for end in (360000, 1200000, 2400000):
                    request = MatchRequest(cutoff={'period': period, 'elapsed_ms': end}, card_budget=5)
                    result = fan.observations(match['id'], request)
                    for observation in result['observations']:
                        assert all(e['period'] == period and end - 360000 < e['elapsed_ms'] <= end
                            and (e['available_period'], e['available_ms']) <= (period, end)
                            for e in observation['evidence'])
                        assert observation['windows'][-1]['end_ms'] == end
                        assert observation['metrics']['sample_sizes'][0] >= 5
                        assert observation['metrics']['sample_sizes'][1] >= 5
    finally:
        store.close()
def test_aborted_observation_body_does_not_raise_in_header_middleware():
    import asyncio
    from fastapi import FastAPI
    from starlette.middleware.base import BaseHTTPMiddleware
    from counterpress.fan.api import FanBodyLimit

    async def verify():
        app = FastAPI()
        app.add_middleware(FanBodyLimit)

        async def headers(request, call_next):
            return await call_next(request)

        app.add_middleware(BaseHTTPMiddleware, dispatch=headers)
        received = iter([{'type': 'http.request', 'body': b'{', 'more_body': True},
                         {'type': 'http.disconnect'}])
        sent = []

        async def receive():
            return next(received, {'type': 'http.disconnect'})

        async def send(message):
            sent.append(message)

        await app({'type': 'http', 'method': 'POST', 'path': '/api/fan/matches/test/observations',
                   'root_path': '', 'query_string': b'', 'headers': [], 'scheme': 'http',
                   'server': ('testserver', 80), 'client': ('testclient', 42), 'http_version': '1.1'},
                  receive, send)
        assert [m['status'] for m in sent if m['type'] == 'http.response.start'] == [499]

    asyncio.run(verify())

