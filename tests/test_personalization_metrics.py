import json
from pathlib import Path
import pytest
from counterpress.personalization.contracts import Action,Appearance,Fixture,MatchRecord
from counterpress.domain.models import PitchPosition
from counterpress.personalization.metrics import reduce_record,rates,empty,select_events


def event(n,at,player,kind,outcome,**kwargs):
    club='eastbridge' if player.startswith('eb') else 'northport'
    return Action(match_id='manual',event_id=f'e{n}',revision=1,delivery_sequence=n,occurrence_order=n,period=1,
        elapsed_ms=at,available_period=1,available_ms=at+(kwargs.get('flight_ms') or 0),club_id=club,player_id=player,kind=kind,outcome=outcome,
        source_reference='independent-test',**kwargs)


@pytest.fixture
def manual():
    fixture=Fixture(match_id='manual',season='2026-27',kickoff='2026-10-19T15:00:00Z',home_id='eastbridge',away_id='northport',
        competition='Unit test',source_kind='calibrated_simulation',appearances=tuple(
            Appearance(player_id=p,club_id='eastbridge' if p.startswith('eb') else 'northport',start_ms=0,end_ms=5400000,starter=True)
            for p in ('eb01','eb08','eb09','np01','np08')))
    p=lambda x:PitchPosition(x=float(x),y=34.)
    events=(event(1,1000,'eb08','pass','completed',start=p(50),end=p(80),intended_end=p(80),recipient_id='eb09',flight_ms=2000,
        completion_probability=.8,estimate_version='test-v1',telemetry_basis='authored_physics'),
        event(2,4000,'eb09','carry','controlled',start=p(80),end=p(90)),
        event(3,5000,'eb09','shot','goal',start=p(90),end=p(105),goal_for='eastbridge',goalkeeper_id='np01',expected_goal_probability=.4,estimate_version='test-v1'),
        event(4,10000,'np08','recovery','established'),
        event(5,11000,'np08','pass','incomplete',start=p(40),end=p(50)),
        event(6,12000,'eb08','recovery','established'),
        event(7,13000,'eb08','pass','completed',start=p(80),end=p(90),intended_end=p(90),recipient_id='eb09',completion_probability=.6,estimate_version='test-v1'),
        event(8,14000,'eb09','shot','blocked',start=p(90),end=p(92)),
        event(9,15000,'eb09','shot','goal',start=p(92),end=p(105),goal_for='eastbridge',goalkeeper_id='np01'),
        event(10,20000,'np08','other','own_goal',goal_for='eastbridge'),
        event(11,25000,'eb09','duel','won',opponent_id='np08'))
    return MatchRecord(fixture=fixture,events=events)


def test_independently_written_accounting_and_rate_denominators(manual):
    expected=json.loads((Path(__file__).parent/'expected_personalization.json').read_text());summary=reduce_record(manual)
    assert summary['score']==expected['score']
    for label,pid in [('scorer','eb09'),('creator','eb08'),('opponent','np08')]:
        for metric,value in expected[label].items():assert summary['players'][pid][metric]==pytest.approx(value)
    creator=summary['players']['eb08'];r=rates(creator)
    assert r['passing_above_expected_per100']==30
    assert r['mean_pass_distance_m']==20
    assert r['mean_pass_speed_kmh']==54
    assert summary['clubs']['eastbridge']['goals']==sum(s['goals'] for p,s in summary['players'].items() if p.startswith('eb'))+1
    assert rates(empty())['goals_per90'] is None
    assert summary['players']['eb01']['clean_sheets']==1


def test_window_excludes_start_includes_end_and_keeps_assist_context(manual):
    whole=reduce_record(manual,(1,5000),window_start=(1,1000))
    assert whole['players']['eb08']['passes']==0
    assert whole['players']['eb08']['assists']==1  # pass is lead-in evidence
    assert whole['players']['eb09']['goals']==1
    assert whole['event_count']==2
    assert whole['players']['eb01']['clean_sheets']==0
    assert reduce_record(manual,(1,5000),window_start=(1,5000))['score']['eastbridge']==0


def test_revision_selection_uses_availability_not_future_knowledge(manual):
    old=manual.events[2];correction=old.model_copy(update={'revision':2,'delivery_sequence':100,'available_ms':30000,'outcome':'off_target','goal_for':None})
    assert select_events([old,correction],(1,29999))==[old]
    assert select_events([correction,old],(1,30000))==[correction]
    assert select_events([old,correction.model_copy(update={'retracted':True})],(1,30000))==[]
    delayed=old.model_copy(update={'available_ms':5100})
    record=MatchRecord(fixture=manual.fixture,events=(delayed,))
    assert reduce_record(record,(1,5099))['score']['eastbridge']==0
    assert reduce_record(record,(1,5100))['score']['eastbridge']==1


def test_invalid_goal_and_fake_speed_fail_schema():
    with pytest.raises(ValueError):event(1,1,'eb09','shot','goal')
    with pytest.raises(ValueError):event(1,1,'eb09','pass','incomplete',flight_ms=500)
    with pytest.raises(ValueError):event(1,1,'eb09','shot','goal',goal_for='northport')
    valid=event(1,1000,'eb09','shot','goal',goal_for='eastbridge',start=PitchPosition(x=90.,y=34.),end=PitchPosition(x=105.,y=34.),flight_ms=500,telemetry_basis='authored_physics')
    with pytest.raises(ValueError):Action.model_validate_json(valid.model_copy(update={'available_ms':1499}).model_dump_json())
