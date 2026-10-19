"""Personalization changes relevance and presentation, never the football facts."""
import json
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import ValidationError

from counterpress.api.main import create_app
from counterpress.fan.api import install_fan
from counterpress.fan.contracts import FanPreferences, HistoryRequest, HomeRequest, MatchRequest, CompareRequest
from counterpress.fan.service import FanService, PreferenceError
from counterpress.personalization.service import CareerService
from counterpress.personalization.store import DataStore

ROOT = Path(__file__).resolve().parents[1]
EXPECTED = json.loads((ROOT / 'tests/expected_fan_personalization.json').read_text())
MID = EXPECTED['match_id']
AS_OF = '2026-10-20T00:00:00Z'


@pytest.fixture(scope='module')
def fan():
    store = DataStore(ROOT / 'fixtures/personalization')
    yield FanService(CareerService(store))
    store.close()


def preferences(**overrides):
    return FanPreferences(favorite_club_ids=['redhaven'], favorite_player_ids=['rh08'], primary_club_id='redhaven', **overrides)


def match_request(**kwargs):
    return MatchRequest(preferences=kwargs.pop('preferences', preferences()), cutoff=kwargs.pop('cutoff', EXPECTED['after_goal']), **kwargs)


@pytest.mark.parametrize('bad', [
    {'favorite_player_ids': ['rh08', 'rh08']}, {'favorite_club_ids': ['a'] * 5},
    {'favorite_player_ids': ['a'] * 13}, {'primary_club_id': 'redhaven'},
    {'favorite_player_ids': ['../env']}, {'depth': 'expert'}, {'language': 'de'},
    {'version': 2}, {'version': True}, {'user_id': 'someone-else'}, {'metric_focus': 'sprint_speed'},
])
def test_strict_bounded_preference_contract(bad):
    with pytest.raises(ValidationError):
        FanPreferences(**bad)


def test_registry_validation_and_canonical_order(fan):
    with pytest.raises(PreferenceError):
        fan.validate(FanPreferences(favorite_player_ids=['unknown']))
    a = FanPreferences(favorite_player_ids=['sb09', 'rh08'])
    b = FanPreferences(favorite_player_ids=['rh08', 'sb09'])
    assert fan.envelope(HistoryRequest(preferences=a))['preference_id'] == fan.envelope(HistoryRequest(preferences=b))['preference_id']


def test_home_keeps_nine_highlights_and_four_matches_without_double_counting(fan):
    home = fan.home(HomeRequest(preferences=preferences(), as_of=AS_OF))
    assert home['highlight_total'] == EXPECTED['home_highlights']
    assert len(home['matches']) == EXPECTED['featured_matches']
    assert sum(h['tag'] == 'preloaded' for h in home['highlights']) == EXPECTED['preloaded_highlights']
    assert all(h['highlight_id'] != h['match_id'] for h in home['highlights'])
    assert home['matches'][0]['match_id'] == MID
    assert home['highlights'][0]['match_id'] == MID
    assert home['following']['players'][0]['player']['name'] == EXPECTED['player_name']
    total = fan.career.profile('rh08', before=AS_OF)['totals']['goals']
    goals = next(t for t in home['following']['players'][0]['tiles'] if t['metric'] == 'goals')
    assert goals['value'] == total == 20
    assert home['theme']['club_id'] == 'redhaven'
    assert 'involvement' not in json.dumps(home)


def test_cold_start_neutral_feed_and_player_only_following(fan):
    empty = fan.home(HomeRequest(as_of=AS_OF))
    followed = fan.home(HomeRequest(as_of=AS_OF, preferences=FanPreferences(favorite_player_ids=['sb09'])))
    assert empty['onboarding']['needs_favorites'] and empty['theme'] is None
    assert empty['following'] == {'players': [], 'clubs': []}
    assert followed['highlights'][0]['match_id'] == MID
    assert followed['theme'] is None
    assert {h['highlight_id'] for h in empty['highlights']} == {h['highlight_id'] for h in followed['highlights']}


def test_completed_history_filter_does_not_reveal_future_highlights_or_scores(fan):
    home = fan.home(HomeRequest(preferences=preferences(), as_of='2026-10-19T15:00:00Z'))
    assert MID not in {m['match_id'] for m in home['matches']}
    assert MID not in {h['match_id'] for h in home['highlights']}
    profile = fan.profile('rh08', 'player', HistoryRequest(as_of='2026-10-19T15:00:00Z'))
    assert profile['profile']['totals']['goals'] == 19
    season = fan.home(HomeRequest(as_of=AS_OF, season='2025-26'))
    assert season['matches'] == [] and season['highlights'] == []
    assert season['library_total'] == 4


def test_languages_and_depths_preserve_canonical_live_facts(fan):
    casual = fan.match(MID, match_request())
    analyst = fan.match(MID, match_request(preferences=preferences(depth='analyst')))
    chinese = fan.match(MID, match_request(preferences=preferences(language='zh-Hans')))
    assert casual['facts'] == analyst['facts'] == chinese['facts']
    assert casual['evidence'] == analyst['evidence'] == chinese['evidence']
    for result in (casual, analyst, chinese):
        m = next(c for c in result['cards'] if c['kind'] == 'career_goal_milestone')
        assert m['facts'][0]['value'] == EXPECTED['career_goals_after']
        assert m['facts'][0]['subject_id'] == EXPECTED['player_id']
        assert m['facts'][0]['scope']['kind'] == 'career_at_event'
        assert m['evidence']['event_id'] == EXPECTED['goal_event_id']
    assert casual['cards'][0]['text'] != analyst['cards'][0]['text'] != chinese['cards'][0]['text']
    assert len({v['view_id'] for v in (casual, analyst, chinese)}) == 3


def test_goal_boundary_focus_and_questions_have_no_future_leak(fan):
    before = fan.match(MID, match_request(cutoff=EXPECTED['before_goal']))
    after = fan.match(MID, match_request())
    assert before['facts']['players']['rh08']['career_at_cutoff']['goals'] == 19
    assert not any(c['kind'] == 'career_goal_milestone' for c in before['cards'])
    assert before['questions'] == []
    assert EXPECTED['goal_event_id'] not in {e['event_id'] for e in before['focus']['involvements']}
    assert after['facts']['score'] == EXPECTED['score_after']
    assert len(after['focus']['active_player_ids']) == 22
    assert after['focus']['player_id'] == 'rh08'
    assert after['focus']['status'] == 'on_pitch'
    assert after['questions'][0]['action']['event_id'] == EXPECTED['goal_event_id']
    assert all(q['answer_mode'] == 'data_view' for q in after['questions'])
    hidden = fan.match(MID, match_request(card_budget=0))
    assert hidden['cards'] == [] and hidden['questions'] == []
    assert hidden['facts'] == after['facts']


def test_focus_not_in_match_and_substitution_boundaries(fan):
    outsider = fan.match(MID, match_request(preferences=FanPreferences(focus_player_id='eb09')))
    assert outsider['focus']['status'] == 'not_in_match'
    assert outsider['focus']['involvements'] == [] and outsider['focus']['match_stats'] is None
    fixture = fan.store.original(MID).fixture
    sub = next(a for a in fixture.appearances if not a.starter)
    assert sub.start_ms > fixture.period_lengths_ms[0]
    sub_ms = sub.start_ms - fixture.period_lengths_ms[0]
    p = FanPreferences(focus_player_id=sub.player_id)
    before = fan.match(MID, match_request(preferences=p, cutoff={'period': 2, 'elapsed_ms': sub_ms - 1}))
    after = fan.match(MID, match_request(preferences=p, cutoff={'period': 2, 'elapsed_ms': sub_ms}))
    assert before['focus']['status'] == 'not_yet_on'
    assert before['focus']['involvements'] == []
    assert after['focus']['status'] == 'on_pitch'
    assert len(after['focus']['active_player_ids']) == 22
    assert sub.player_id not in before['focus']['active_player_ids']
    assert sub.player_id in after['focus']['active_player_ids']


def test_profile_tiles_coverage_and_semantic_claims(fan):
    view = fan.profile('eb09', 'player', HistoryRequest(as_of=AS_OF, preferences=FanPreferences(depth='analyst')))
    profile = view['profile']; tiles = {t['metric']: t for t in view['presentation']['tiles']}
    assert profile['coverage']['assists_unavailable_matches'] == 2
    assert tiles['assists']['value'] is None and tiles['assists']['coverage'] == 'partial'
    assert tiles['goals']['value'] == profile['totals']['goals']
    for c in view['presentation']['cards']:
        assert all(f['subject_id'] == 'eb09' and f['evidence_id'] == profile['evidence']['baseline_id'] for f in c['facts'])
    casual = fan.profile('rh08', 'player', HistoryRequest(as_of=AS_OF))
    analyst = fan.profile('rh08', 'player', HistoryRequest(as_of=AS_OF, preferences=FanPreferences(depth='analyst')))
    assert casual['profile'] == analyst['profile']
    assert len(casual['presentation']['tiles']) < len(analyst['presentation']['tiles'])
    assert casual['presentation']['activity_map']['total_actions'] == casual['profile']['heatmap']['total_actions']


def test_comparison_uses_same_scope_and_no_fabricated_winner(fan):
    request = CompareRequest(player_ids=['rh08', 'sb09'], season='2026-27', as_of=AS_OF)
    result = fan.compare(request)
    assert result['season'] == '2026-27' and result['as_of'] == AS_OF
    goals = next(m for m in result['metrics'] if m['metric'] == 'goals')
    for pid in request.player_ids:
        assert goals['values'][pid]['value'] == fan.career.profile(pid, season='2026-27', before=AS_OF)['totals']['goals']
    assert 'winner' not in result
    empty = fan.compare(CompareRequest(player_ids=['rh08', 'sb09'], as_of='2019-01-01T00:00:00Z'))
    assert empty['rate_comparison_available'] is False
    assert all(v['value'] is None for m in empty['metrics'] if m['metric'] == 'goals_per90' for v in m['values'].values())


def test_metric_focus_changes_selection_and_does_not_manufacture_statistics(fan):
    passing = fan.match(MID, match_request(preferences=preferences(metric_focus='passing'), card_budget=2))
    defending = fan.match(MID, match_request(preferences=preferences(metric_focus='defending'), card_budget=2))
    assert passing['facts'] == defending['facts']
    assert any(c['kind'] == 'player_passing' for c in passing['cards'])
    assert any(c['kind'] == 'player_duels' for c in defending['cards'])
    for c in defending['cards']:
        if c['kind'] == 'player_duels':
            assert c['facts'][0]['value'] == defending['facts']['players']['rh08']['match']['duels_won']


def test_changed_preloaded_source_hides_its_authored_card():
    app = create_app()
    with TestClient(app) as client:
        initial = client.post('/api/fan/home', json={'as_of': AS_OF}).json()
        assert 'last-gasp' in {h['highlight_id'] for h in initial['highlights']}
        snapshots = app.state.snapshots
        snapshots.snapshot('last-gasp', 780000)
        def revise(history):
            goal = history.records[-1]
            changed = goal.model_copy(update={'revision': 2, 'source_delivery_sequence': 100,
                'available_at': goal.available_at.model_copy(update={'elapsed_ms': 780100})})
            return history.model_copy(update={'records': (*history.records, changed)})
        snapshots.store.transact('last-gasp', revise)
        after = client.post('/api/fan/home', json={'as_of': AS_OF}).json()
        assert 'last-gasp' not in {h['highlight_id'] for h in after['highlights']}


def test_two_fans_can_read_concurrently_without_preference_leak(fan):
    a = HomeRequest(as_of=AS_OF, preferences=preferences(), request_id='red-fan')
    b = HomeRequest(as_of=AS_OF, preferences=FanPreferences(favorite_club_ids=['eastbridge'], primary_club_id='eastbridge', language='zh-Hans'), request_id='east-fan')
    with ThreadPoolExecutor(max_workers=2) as pool:
        red, east = list(pool.map(fan.home, (a, b)))
    assert red['request_id'] == 'red-fan' and east['request_id'] == 'east-fan'
    assert red['theme']['club_id'] == 'redhaven' and east['theme']['club_id'] == 'eastbridge'
    assert east['following']['players'] == []
    assert red['highlights'][0]['relevance']['favorite_player_ids'] == ['rh08']
    assert all(h['relevance']['favorite_player_ids'] == [] for h in east['highlights'])


def test_retraction_withdraws_personalized_milestone_and_stale_highlight():
    store = DataStore(ROOT / 'fixtures/personalization'); fan = FanService(CareerService(store))
    try:
        original = fan.match(MID, match_request())
        goal = next(e for e in store.original(MID).events if e.event_id == EXPECTED['goal_event_id'])
        end = max(e.delivery_sequence for e in store.original(MID).events)
        correction = goal.model_copy(update={'revision': 2, 'delivery_sequence': end + 1, 'available_ms': 2700100, 'retracted': True})
        store.ingest(MID, [correction])
        assert fan.match(MID, match_request()) == original
        later = fan.match(MID, match_request(cutoff={'period': 2, 'elapsed_ms': 2700100}))
        assert not any(c['kind'] == 'career_goal_milestone' for c in later['cards'])
        assert later['facts']['players']['rh08']['career_at_cutoff']['goals'] == 19
        assert later['view_id'] != original['view_id']
        legacy_delivery = fan.match(MID, match_request(cutoff={'period': 2, 'elapsed_ms': 2700100}, through_sequence=end))
        assert legacy_delivery['facts']['players']['rh08']['career_at_cutoff']['goals'] == 20
        home = fan.home(HomeRequest(preferences=preferences(), as_of=AS_OF))
        assert MID not in {h['match_id'] for h in home['highlights']}
        assert next(m for m in home['matches'] if m['match_id'] == MID)['score'] == {'southbank': 3, 'redhaven': 1}
    finally:
        store.close()


def test_corrected_career_baseline_does_not_keep_false_milestone_title():
    store = DataStore(ROOT / 'fixtures/personalization'); fan = FanService(CareerService(store))
    try:
        prior = next(r for r in store.rows(club='redhaven', before='2026-10-19T15:00:00Z')
                     if json.loads(r['summary'])['players'].get('rh08', {}).get('goals', 0))
        record = store.original(prior['id']); goal = next(e for e in record.events if e.player_id == 'rh08' and e.goal_for == 'redhaven')
        store.ingest(prior['id'], [goal.model_copy(update={'revision': 2, 'delivery_sequence': max(e.delivery_sequence for e in record.events) + 1,
            'available_period': 2, 'available_ms': 2700100, 'retracted': True})])
        home = fan.home(HomeRequest(as_of=AS_OF))
        clip = next(h for h in home['highlights'] if h['highlight_id'] == MID + '-e00615')
        assert '20 career goals' not in clip['title']
        assert clip['title'] == 'Enzo Clarke puts Redhaven ahead'
    finally:
        store.close()


def test_all_http_routes_errors_bounds_and_non_persistence():
    with TestClient(create_app()) as client:
        assert client.get('/api/fan/capabilities').json()['storage'] == 'device'
        assert client.get('/api/fan/capabilities').json()['assistant_available'] is False
        payload = {'preferences': preferences().model_dump(), 'request_id': 'browser-one', 'as_of': AS_OF}
        for route in ('home', 'players/rh08', 'clubs/redhaven'):
            response = client.post('/api/fan/' + route, json=payload)
            assert response.status_code == 200
            assert response.json()['request_id'] == 'browser-one'
            assert response.headers['cache-control'] == 'private, no-store'
            assert 'set-cookie' not in response.headers
        assert client.post('/api/fan/home', json={'as_of': AS_OF}).json()['following'] == {'players': [], 'clubs': []}
        assert client.post('/api/fan/players/compare', json={'player_ids': ['rh08', 'sb09'], 'as_of': AS_OF}).status_code == 200
        assert client.post('/api/fan/players/compare', json={'player_ids': ['rh08', 'rh08']}).status_code == 422
        assert client.post('/api/fan/home', json={'as_of': '2026-02-30T00:00:00Z'}).status_code == 422
        assert client.post('/api/fan/home', json={'limit': True}).status_code == 422
        assert client.post('/api/fan/preferences/validate', json={'preferences': {'favorite_player_ids': ['missing']}}).status_code == 422
        assert client.post('/api/fan/players/missing', json={}).status_code == 404
        assert client.post('/api/fan/matches/' + MID, json={'cutoff': {'period': 2, 'elapsed_ms': 99999999}}).status_code == 422
        assert client.post('/api/fan/matches/' + MID, json={'cutoff': {'period': True, 'elapsed_ms': 0}}).status_code == 422
        assert client.post('/api/fan/matches/' + MID, json=match_request().model_dump()).status_code == 200
        assert client.get('/api/fan/home').status_code == 405
        assert client.post('/api/fan/home', content=b' ' * 16385).status_code == 413
        chunks = (b' ' * 8000 for _ in range(3))
        assert client.post('/api/fan/home', content=chunks).status_code == 413
        assert client.get('/health').status_code == 200
        schemas = client.get('/openapi.json').json()['components']['schemas']
        assert 'FanPreferences' in schemas and 'MatchRequest' in schemas
