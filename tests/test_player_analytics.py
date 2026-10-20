"""Independent spatial/accounting expectations for the extended player views."""
import json
from pathlib import Path
from types import SimpleNamespace
import pytest
from fastapi.testclient import TestClient
from counterpress.domain.models import PitchPosition
from counterpress.personalization.contracts import MatchRecord
from counterpress.personalization.analytics import derive,aggregate,progressive,box,PlayerAnalytics,DEFINITIONS
from counterpress.personalization.metrics import select_events
from counterpress.personalization.store import DataStore
from counterpress.personalization.service import CareerService
from test_personalization_metrics import manual,event

ROOT=Path(__file__).resolve().parents[1]
P=lambda x,y=34:PitchPosition(x=float(x),y=float(y))


def test_geometry_boundaries_use_goal_distance_not_only_forward_x():
    assert progressive(P(10),P(40))
    assert not progressive(P(10),P(39.99))
    assert progressive(P(50),P(65))
    assert not progressive(P(50),P(64.99))
    assert progressive(P(70),P(80))
    assert not progressive(P(90),P(100,0))  # closer to end line, farther from goal
    assert box(P(88.5,13.84)) and box(P(105,54.16))
    assert not box(P(88.49)) and not box(P(100,54.17))


def test_handwritten_extended_accounting_keeps_consistent_totals(manual):
    rows=derive(manual);creator=rows['eb08'];scorer=rows['eb09']
    assert creator['stats']['progressive_passes_completed']==2
    assert creator['stats']['final_third_entries']==1
    assert creator['stats']['box_entries']==1
    assert creator['stats']['xa']==pytest.approx(.4)
    assert creator['stats']['key_passes']==2  # one goal and one blocked shot
    assert scorer['stats']['carries']==1
    assert scorer['stats']['carry_distance_m']==10
    assert scorer['stats']['shots_inside_box']==3
    assert scorer['stats']['xg_goals']==1
    assert scorer['timing']==[2,0,0,0,0,0]
    assert sum(creator['heat'].values())==creator['stats']['actions']
    assert sum(scorer['defense'].values())==0  # challenge has no recorded location
    assert rows['np01']['stats']['own_goals_conceded']==1
    metrics={m['key']:m for m in aggregate([(manual.fixture.model_dump(),scorer)])}
    assert metrics['goals_above_xg']['value']==pytest.approx(.6)  # matched xG shots only
    assert metrics['conversion']['value']==pytest.approx(200/3,abs=.0001)
    creators={m['key']:m for m in aggregate([(manual.fixture.model_dump(),creator)])}
    assert creators['passing_above_expected']['value']==30
    assert creators['mean_pass_speed']['value']==54


def test_duel_location_rotates_for_opponent_and_draw_awards_no_win(manual):
    duel=event(1,1000,'eb08','duel','lost',start=P(10,5),opponent_id='np08')
    draw=event(2,2000,'eb08','duel','draw',start=P(20),opponent_id='np08')
    rows=derive(MatchRecord(fixture=manual.fixture,events=(duel,draw)))
    assert rows['np08']['defense']=={'10:7':1}  # 95,63, normalized to opponent
    assert rows['eb08']['stats']['duels_lost']==1
    assert rows['np08']['stats']['duels_drawn']==1
    assert rows['eb08']['defense']=={}


def test_unknown_passes_excluded_from_accuracy_not_from_attempts(manual):
    known=event(1,1000,'eb08','pass','completed',start=P(1),end=P(40),recipient_id='eb09')
    unknown=event(2,2000,'eb08','pass','unknown',start=P(1),end=P(40))
    p=derive(MatchRecord(fixture=manual.fixture,events=(known,unknown)))['eb08']
    m={x['key']:x for x in aggregate([(manual.fixture.model_dump(),p)])}
    assert m['long_passes']['value']==2
    assert m['long_accuracy']['value']==100
    assert m['progressive_accuracy']['value']==100
    assert m['pass_accuracy']['value']==100


def test_partial_coverage_uses_covered_minutes_and_empty_is_unknown(manual):
    p=derive(manual)['eb08'];f=manual.fixture.model_dump()
    archive={**f,'source_kind':'adapted_archive','assist_basis':'provider_tags','shot_assists_complete':False}
    m={x['key']:x for x in aggregate([(f,p),(archive,p)])}
    assert m['xa']['value']==.4 and m['xa']['per90']==.4
    assert m['xa']['covered_matches']==1 and m['xa']['total_matches']==2
    assert m['passes']['value']==4 and m['passes']['per90']==2
    assert all(m['value'] is None for m in aggregate([]))


def test_xa_expires_after_long_carry_and_retracted_pass(manual):
    first,carry,goal=manual.events[:3]
    long=carry.model_copy(update={'end':P(92)})
    result=derive(MatchRecord(fixture=manual.fixture,events=(first,long,goal)))
    assert result['eb08']['stats']['xa']==0
    removed=first.model_copy(update={'revision':2,'retracted':True,'delivery_sequence':100,'available_ms':10000})
    selected=select_events([first,carry,goal,removed],(1,10000))
    assert derive(MatchRecord(fixture=manual.fixture,events=tuple(selected)))['eb08']['stats']['xa']==0


def test_first_half_added_time_stays_in_first_half_timing_bucket(manual):
    goal=manual.events[2].model_copy(update={'elapsed_ms':2760000,'available_ms':2760000})
    fixture=manual.fixture.model_copy(update={'period_lengths_ms':(2800000,2700000)})
    assert derive(MatchRecord(fixture=fixture,events=(goal,)))['eb09']['timing']==[0,0,1,0,0,0]


@pytest.fixture(scope='module')
def analytics():
    store=DataStore(ROOT/'fixtures/personalization')
    yield PlayerAnalytics(CareerService(store))
    store.close()


def test_all_featured_profiles_maps_and_statistics_reconcile(analytics):
    for player in analytics.store.players.values():
        if not player.featured:continue
        result=analytics.profile(player.player_id,before='2026-10-20T00:00:00Z')
        metrics={m['key']:m for m in result['metrics']}
        core=analytics.career.profile(player.player_id,before='2026-10-20T00:00:00Z')
        for key in ('goals','assists','passes','passes_completed','shots','duels_won'):
            assert metrics[key]['value']==core['totals'][key],(player.player_id,key)
        assert sum(c['actions'] for c in result['heatmap']['cells'])==metrics['actions']['value']
        assert len(result['shots'])==metrics['shots_inside_box']['value']+metrics['shots_outside_box']['value']
        assert sum(result['goal_timing'])==metrics['goals']['value']
        assert all(m['value'] is None or 0<=m['value']<=100 for m in result['metrics'] if m['unit']=='percent')
        assert all(m['percentile'] is None or 0<=m['percentile']<=100 for m in result['comparison']['metrics'])
        assert ('saves' in metrics)==(player.role=='GK')


def test_scope_filters_and_no_future_match_leakage(analytics):
    empty=analytics.profile('rh09',before='2010-01-01T00:00:00Z')
    assert empty['scope']['matches']==0 and empty['shots']==[]
    assert all(m['percentile'] is None for m in empty['comparison']['metrics'])
    result=analytics.profile('rh09',season='2026-27',before='2026-10-19T15:01:00Z')
    assert all(s['match_id']!='career-showcase-southbank-redhaven' for s in result['shots'])
    assert result['scope']['matches']<analytics.profile('rh09')['scope']['matches']


def test_revision_invalidates_materialized_metrics_and_historical_scope_is_preserved(analytics):
    store=analytics.store;mid='career-showcase-southbank-redhaven';record=store.original(mid)
    old=next(e for e in record.events if e.player_id=='rh09' and e.outcome=='goal')
    original=analytics.profile('rh09',before='2026-10-20T00:00:00Z')
    revision=old.model_copy(update={'revision':2,'delivery_sequence':max(e.delivery_sequence for e in record.events)+1,
        'available_period':2,'available_ms':2800000,'outcome':'off_target','goal_for':None})
    store.ingest(mid,[revision])
    try:
        updated=analytics.profile('rh09',before='2026-10-20T00:00:00Z')
        get=lambda r,k:next(m['value'] for m in r['metrics'] if m['key']==k)
        assert get(updated,'goals')==get(original,'goals')-1
        assert get(updated,'shots')==get(original,'shots')
        shot=next(s for s in updated['shots'] if s['match_id']==mid and s['event_id']==old.event_id)
        assert shot['revision']==2 and shot['outcome']=='off_target'
        earlier=analytics.profile('rh09',before='2026-10-19T16:46:00Z')
        assert get(earlier,'goals')==get(original,'goals')
    finally:
        with store.db:store.db.execute('DELETE FROM career_revisions WHERE match_id=?',(mid,))


def test_checksum_and_reducer_lineage_fail_closed(analytics,tmp_path):
    import gzip
    from hashlib import sha256
    root=tmp_path/'personalization';root.mkdir();dest=tmp_path/'analytics';dest.mkdir()
    raw=gzip.compress(json.dumps({**analytics.artifact,'ledger_sha256':'wrong'}).encode())
    (dest/'players.json.gz').write_bytes(raw)
    (dest/'manifest.json').write_text(json.dumps({'sha256':sha256(raw).hexdigest()}))
    career=SimpleNamespace(store=SimpleNamespace(root=root,manifest=analytics.store.manifest))
    with pytest.raises(ValueError,match='rebuilding'):PlayerAnalytics(career)
    (dest/'players.json.gz').write_bytes(b'bad')
    with pytest.raises(ValueError,match='checksum'):PlayerAnalytics(career)


def test_api_contract_and_invalid_input():
    from counterpress.api.main import create_app
    with TestClient(create_app()) as client:
        r=client.get('/api/data/players/eb01/analytics?season=2026-27&before=2026-10-20T00:00:00Z')
        assert r.status_code==200 and r.headers['cache-control']=='no-store'
        assert len(r.json()['metrics'])==len(DEFINITIONS)
        assert client.get('/api/data/players/missing/analytics').status_code==404
        assert client.get('/api/data/players/eb01/analytics?before=tomorrow').status_code==422


def test_contiguous_carry_is_one_run_and_restart_is_not_a_carry(manual):
    a=event(1,1000,'eb09','carry','controlled',start=P(70),end=P(78))
    b=event(2,5000,'eb09','carry','controlled',start=P(78),end=P(85))
    c=event(3,8000,'eb09','carry','controlled',start=P(52.5),end=P(52.5),restart=True)
    p=derive(MatchRecord(fixture=manual.fixture,events=(a,b,c)))['eb09']
    assert p['stats']['carries']==1
    assert p['stats']['progressive_carries']==1
    assert p['stats']['carry_distance_m']==15
    m={x['key']:x for x in aggregate([(manual.fixture.model_dump(),p)])}
    assert m['headed_shots']['value'] is None and m['woodwork']['value'] is None
