"""Hand-authored arithmetic and causal boundaries, independent of generators."""
from contextlib import nullcontext
from types import SimpleNamespace
import json
import math
import pytest
from pydantic import ValidationError
from counterpress.analyst.contracts import AnalystRequest, MATCH_IDS, TRIGGER_TYPES
from counterpress.analyst.metrics import geometric_xg, difficulty, turns
from counterpress.analyst.service import build_snapshot, build_agent_packet
from counterpress.personalization.contracts import Action, Appearance, Fixture

MID=MATCH_IDS[0]


def event(i,ms,**kw):
    return Action(**({'match_id':MID,'event_id':f'e{i}','revision':1,'delivery_sequence':i,'occurrence_order':i,
        'period':1,'elapsed_ms':ms,'available_period':1,'available_ms':ms,'club_id':'home','player_id':'h1',
        'kind':'pass','outcome':'complete','source_reference':'independent-test'}|kw))


def career(events,source='calibrated_simulation'):
    fixture=Fixture(match_id=MID,season='2026',kickoff='2026-10-20T10:00:00Z',home_id='home',away_id='away',competition='Test',source_kind=source,
        appearances=tuple(Appearance(player_id=p,club_id=c,start_ms=0,end_ms=5400000,starter=True) for p,c in [('h1','home'),('h2','home'),('a1','away')]))
    return SimpleNamespace(store=SimpleNamespace(snapshot=nullcontext,row=lambda m:{'fixture':fixture.model_dump_json()},events=lambda m:events,
        clubs={'home':SimpleNamespace(name='Home'),'away':SimpleNamespace(name='Away')},
        players={p:SimpleNamespace(name=p,role='MF')for p in ('h1','h2','a1')}))


def snap(events,ms=600000,period=1,source='calibrated_simulation',**kw):
    return build_snapshot(career(events,source),MID,AnalystRequest(cutoff={'period':period,'elapsed_ms':ms},**kw))


def metric(s,key,club='home',window='prefix'):
    return next(m for m in s['metrics'] if m['id']==f'{window}:{club}:{key}')


def test_independent_pass_geometry_outcomes_and_heatmap():
    rows=[event(1,1000,start={'x':0,'y':0},end={'x':3,'y':4}),event(2,2000,outcome='incomplete'),event(3,3000,outcome='unknown')]
    s=snap(rows)
    assert metric(s,'passes')['value']==3
    assert metric(s,'passes_completed')['value']==1
    assert metric(s,'pass_accuracy')['value']==50
    assert metric(s,'pass_accuracy')['status']=='partial'
    assert metric(s,'pass_accuracy')['coverage']=={'numerator':2,'denominator':3}
    assert metric(s,'completed_pass_distance')['value']==5
    assert metric(s,'heatmap')['value']['cells']==[{'column':0,'row':0,'count':1}]
    assert metric(s,'pass_speed')['value'] is None
    assert metric(s,'pass_routes')['value']['passes'][0]['end']=={'x':3.0,'y':4.0}


def test_current_previous_windows_exclude_start_include_end():
    rows=[event(i,t,kind='shot',outcome='off_target') for i,t in enumerate([0,1,300000,300001,600000,600001],1)]
    s=snap(rows)
    assert metric(s,'shots',window='previous')['value']==2
    assert metric(s,'shots',window='current')['value']==2
    assert metric(s,'shots')['value']==5
    assert len(s['evidence'])==5


def test_availability_occurrence_sequence_and_revision_retraction():
    a=event(1,1000)
    corrected=a.model_copy(update={'revision':2,'delivery_sequence':3,'available_ms':3000,'outcome':'incomplete'})
    removed=corrected.model_copy(update={'revision':3,'delivery_sequence':4,'available_ms':4000,'retracted':True})
    rows=[a,event(2,2000),corrected,removed]
    assert metric(snap(rows,2500),'passes_completed')['value']==2
    assert metric(snap(rows,3500),'passes_completed')['value']==1
    assert metric(snap(rows,4500),'passes')['value']==1
    assert metric(snap(rows,4500,through_sequence=2),'passes_completed')['value']==2
    assert snap(rows,2500)['snapshot_id']==snap(rows[:2],2500)['snapshot_id']
    assert snap(rows,3500)['snapshot_id']!=snap(rows,4500)['snapshot_id']
    assert snap(rows,4500,through_sequence=0)['through_sequence']==0


def test_unknown_future_events_and_duplicate_deliveries_do_not_change_visible_identity():
    old=[event(1,1000)]
    assert snap(old,1000)==snap(old+old,1000)
    assert snap(old,1000)['snapshot_id']==snap(old+[event(2,1001)],1000)['snapshot_id']
    assert {e['event_id']for e in snap(old+[event(2,1001)],1000)['evidence']}=={'e1'}


def test_halftime_comparisons_never_reuse_prior_half():
    rows=[event(1,2699000),event(2,1000,period=2,available_period=2)]
    s=snap(rows,2000,2)
    assert metric(s,'passes')['value']==2
    assert metric(s,'passes',window='current')['value']==1
    assert metric(s,'passes',window='previous')['value']==0
    assert not s['signals']


def test_own_goal_counts_for_beneficiary_but_not_shooter_goal_or_shot():
    s=snap([event(1,1000,kind='shot',outcome='own_goal',goal_for='away')])
    assert s['score']=={'home':0,'away':1}
    assert metric(s,'goals','away')['value']==1
    assert metric(s,'goals','h1')['value']==0
    assert metric(s,'shots')['value']==0


def test_authored_ball_speed_requires_arrival_and_is_not_player_speed():
    shot=event(1,1000,kind='shot',outcome='off_target',start={'x':75,'y':34},end={'x':105,'y':34},flight_ms=1000,available_ms=2000,telemetry_basis='authored_physics')
    assert metric(snap([shot],1999),'shot_speed')['value'] is None
    s=snap([shot],2000)
    assert metric(s,'shot_speed')['value']==108
    assert metric(s,'player_top_speed')['value'] is None
    assert metric(s,'player_distance')['status']=='unavailable'
    assert metric(s,'sprints')['value'] is None


def test_authored_xg_and_geometric_estimate_are_separate():
    shot=event(1,1000,kind='shot',outcome='off_target',start={'x':94,'y':34},expected_goal_probability=.2,estimate_version='authored-test')
    s=snap([shot])
    assert metric(s,'xg_authored')['value']==.2
    assert metric(s,'xg_geometry')['basis']=='uncalibrated_heuristic'
    assert 0<metric(s,'xg_geometry')['value']<1
    assert metric(s,'xg_geometry')['value']!=.2
    for x,y in [(105,34),(105,30.34),(0,0)]:
        assert math.isfinite(geometric_xg(shot.model_copy(update={'start':shot.start.model_copy(update={'x':x,'y':y})})))


def test_pass_difficulty_has_independent_known_arithmetic():
    e=event(1,1000,start={'x':0,'y':0},end={'x':30,'y':0})
    assert difficulty(e)==pytest.approx(.5875)
    s=snap([e]);assert metric(s,'pass_difficulty_geometry')['value']==.5875
    assert metric(s,'pass_difficulty_authored')['value'] is None


def test_no_unknown_tackles_fouls_ppda_or_tracking_fabricated():
    s=snap([event(1,1000,kind='duel',outcome='won')],source='adapted_archive')
    assert metric(s,'duels_won')['value']==1
    for key in ['tackles_won','ppda','interceptions','fouls','yellow_cards','red_cards','corners','recoveries','pressures','possession_seconds','detection_precision','performance_rating']:
        assert metric(s,key)['value'] is None


def test_shot_increase_needs_closer_chances_and_full_windows():
    shots=[event(i,t,kind='shot',outcome='off_target',start={'x':94,'y':34}) for i,t in enumerate([100000,350000,400000,500000],1)]
    s=snap(shots)
    assert any(x['id']=='closer_chances:home'for x in s['signals'])
    assert not any(x['id']=='closer_chances:home'for x in snap(shots,599999)['signals'])
    outside=[e.model_copy(update={'start':e.start.model_copy(update={'x':60})})for e in shots]
    assert any(x['id']=='outside_shots:home'for x in snap(outside)['signals'])
    assert not any(x['id']=='closer_chances:home'for x in snap(outside)['signals'])


def test_transition_signal_requires_linked_actors_no_restart_no_interruption():
    rows=[event(1,450000,club_id='away',player_id='a1',outcome='incomplete'),
        event(2,452000,kind='recovery',outcome='won'),
        event(3,455000,recipient_id='h2'),
        event(4,460000,player_id='h2',kind='shot',outcome='off_target')]
    s=snap(rows)
    assert any(x['id']=='turnover_chance:home'for x in s['signals'])
    for edit in [{'player_id':'h1'},{'restart':True},{'elapsed_ms':470001,'available_ms':470001}]:
        assert not any(x['id']=='turnover_chance:home'for x in snap(rows[:-1]+[rows[-1].model_copy(update=edit)])['signals'])
    assert turns([rows[0],rows[1].model_copy(update={'period':2,'available_period':2})])==[]


def test_signal_ids_resolve_and_agent_packet_is_bounded_and_role_scoped():
    rows=[event(i,i*2000)for i in range(1,220)]
    s=snap(rows)
    assert len(s['evidence'])<=64
    for signal in s['signals']:
        assert set(signal['evidence_ids'])<={e['id']for e in s['evidence']}
        assert set(signal['metric_ids'])<={m['id']for m in s['metrics']}
    for role in ('chance','control','defence','players'):
        p=build_agent_packet(s,role)
        assert p['snapshot_id']==s['snapshot_id']
        assert len(p['evidence'])<=64
        assert all(x['role']==role for x in p['signals'])
        assert not any(m['key']=='heatmap'for m in p['metrics'])
    assert set(t['id']for t in s['triggers'])==set(TRIGGER_TYPES)
    json.dumps(s,allow_nan=False)


@pytest.mark.parametrize('payload',[
    {'cutoff':{'period':0,'elapsed_ms':0}}, {'cutoff':{'period':1,'elapsed_ms':-1}},
    {'cutoff':{'period':1,'elapsed_ms':True}}, {'cutoff':{'period':1,'elapsed_ms':1.2}},
    {'cutoff':{'period':1,'elapsed_ms':0},'through_sequence':-1},
    {'cutoff':{'period':1,'elapsed_ms':0},'language':'xx'},
    {'cutoff':{'period':1,'elapsed_ms':0},'focus_player_id':'../escape'},
    {'cutoff':{'period':1,'elapsed_ms':0},'extra':'no'}])
def test_strict_request(payload):
    with pytest.raises(ValidationError):AnalystRequest.model_validate(payload)


def test_invalid_scope_rejected():
    with pytest.raises(KeyError):build_snapshot(career([]),'unknown',AnalystRequest(cutoff={'period':1,'elapsed_ms':0}))
    with pytest.raises(ValueError):snap([],2700001)
    with pytest.raises(ValueError):snap([],focus_player_id='outside')
    with pytest.raises(ValueError):snap([],through_sequence=1)


@pytest.mark.parametrize('period',[True,False,1.0,2.0,'1'])
def test_period_requires_exact_integer(period):
    with pytest.raises(ValidationError):AnalystRequest(cutoff={'period':period,'elapsed_ms':0})


def test_lost_duel_credits_opposing_winner_consistently():
    s=snap([event(1,1000,kind='duel',outcome='lost',opponent_id='a1')])
    assert metric(s,'duels_won','away')['value']==1
    assert metric(s,'duels_won','a1')['value']==1
    assert metric(s,'tackles_won','away')['value'] is None


def test_dispatch_preserves_required_pairs_and_bounded_citations():
    from counterpress.analyst.service import build_dispatch_packet
    prior=[event(i+1,100000+i*10000,start={'x':60,'y':34},end={'x':80 if i<3 else 65,'y':34})for i in range(10)]
    current=[event(i+11,350000+i*10000,outcome='complete'if i<6 else'incomplete',start={'x':60,'y':34},end={'x':65,'y':34})for i in range(10)]
    s=snap(prior+current);p=build_dispatch_packet(s)
    raw=json.dumps(p,ensure_ascii=False,separators=(',',':'))
    assert len(raw)<=24000 and len(raw.encode())<=32000
    assert p['windows']==s['windows']
    for key in ('pass_accuracy','final_third_entries'):
        assert {f'{w}:home:{key}'for w in ('current','previous')}<={m['id']for m in p['metrics']}
    for candidate in p['candidates']:
        reading=candidate['reading']
        assert set(reading['evidence_ids'])<={e['id']for e in p['evidence']}
        assert set(reading['metric_ids'])<={m['id']for m in p['metrics']}
    assert all(m['id'] in {ref for c in p['candidates']for ref in c['reading']['metric_ids']}for m in p['metrics'])


def test_zero_and_missing_remain_distinct():
    s=snap([])
    assert metric(s,'shots')['value']==0
    assert metric(s,'pass_accuracy')['value'] is None
    assert metric(s,'shot_speed')['value'] is None
    assert metric(s,'player_distance')['value'] is None
    assert metric(s,'carry_progression')['value'] is None


def test_all_reference_trigger_families_are_explicit_without_forced_narration():
    s=snap([],2700000)
    triggers={t['id']:t for t in s['triggers']}
    assert len(triggers)==15
    assert triggers['half_time']['active']
    assert not triggers['full_time']['active']
    assert triggers['card']['status']=='unsupported'
    assert s['signals']==[]


def test_canonical_fulltime_scores_and_dispatch_bounds():
    from pathlib import Path
    from counterpress.personalization.store import DataStore
    from counterpress.personalization.service import CareerService
    from counterpress.analyst.service import build_dispatch_packet
    store=DataStore(Path('fixtures/personalization'));c=CareerService(store)
    expected={MATCH_IDS[0]:[4,2],MATCH_IDS[1]:[3,2],MATCH_IDS[2]:[2,2]}
    for mid in MATCH_IDS:
        fixture=store.original(mid).fixture
        for period,ms in [(1,0),(1,600000),(2,600000),(2,fixture.period_lengths_ms[1])]:
            s=build_snapshot(c,mid,AnalystRequest(cutoff={'period':period,'elapsed_ms':ms}))
            p=build_dispatch_packet(s)
            assert len(json.dumps(p,ensure_ascii=False,separators=(',',':')))<=24000
            assert all((e['period'],e['elapsed_ms'])<=(period,ms)for e in p['evidence'])
            if period==2 and ms==fixture.period_lengths_ms[1]:assert list(s['score'].values())==expected[mid]
