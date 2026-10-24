"""Proactive cards use recorded facts, a bounded lifetime, and no model calls."""
from types import SimpleNamespace
import pytest
from counterpress.assistant.intelligence import goal_buildup
from counterpress.fan.contracts import FanPreferences, MatchRequest
from counterpress.fan.service import FanService
from counterpress.personalization.contracts import Action, Appearance, Fixture
from counterpress.personalization.metrics import select_events, digest


@pytest.fixture
def setup():
    f=Fixture(match_id='test-match',season='2026-27',kickoff='2026-10-19T15:00:00Z',home_id='home',away_id='away',competition='Test',source_kind='calibrated_simulation',
        appearances=tuple(Appearance(player_id=p,club_id=c,start_ms=0,end_ms=5400000,starter=True) for p,c in [('h1','home'),('h2','home'),('h3','home'),('a1','away')]))
    def event(i,kind,at,player,**updates):
        return Action(**(dict(match_id=f.match_id,event_id=f'e{i}',revision=1,delivery_sequence=i,occurrence_order=i,period=1,elapsed_ms=at,
            available_period=1,available_ms=at,club_id='home',player_id=player,kind=kind,outcome='established',source_reference=f'test:e{i}')|updates))
    es=[event(1,'recovery',1000,'h1'),event(2,'pass',2000,'h1',outcome='completed',recipient_id='h2'),
        event(3,'pass',4000,'h2',outcome='completed',recipient_id='h3'),event(4,'carry',6000,'h3',outcome='controlled'),
        event(5,'shot',9000,'h3',outcome='goal',goal_for='home',available_ms=9500)]
    store=SimpleNamespace(players={p:SimpleNamespace(name=n) for p,n in [('h1','Alex Finch'),('h2','Ben Hayes'),('h3','Cole Reed'),('a1','Dan Stone')]})
    return FanService(SimpleNamespace(store=store)),f,es


def build(setup, at=9500, preferences=None, events=None):
    fan,f,es=setup
    request=MatchRequest(cutoff={'period':1,'elapsed_ms':at},preferences=preferences or FanPreferences())
    selected=select_events(events if events is not None else es,(1,at))
    return fan.buildup_card(f,selected,request,digest(selected))


def test_goal_outcome_boundary_stable_context_and_no_replay_claim(setup):
    assert build(setup,9499) is None
    result=build(setup)
    assert result['kind']=='goal_buildup'
    assert 'Cole Reed took the scoring shot 8 seconds after the ball was won back.'==result['text']
    assert result['facts'][0]['value']==8
    assert result['ask_footie']=={'match_id':'test-match','event_id':'e5','event_revision':1,
        'cutoff':{'period':1,'elapsed_ms':9500},'question':'What made that goal happen?','label':'Cole Reed’s goal'}
    assert result['action']['kind']=='profile'
    assert result['replay_available'] is False and result['replay_status']=='not_attached'
    assert result['evidence']['expires_at']=={'period':1,'elapsed_ms':39000}
    assert result['evidence']['occurred_at']['elapsed_ms']==9000
    assert result['evidence']['available_at']['elapsed_ms']==9500


def test_two_fans_get_grounded_different_contributions_and_analyst_evidence(setup):
    scorer=build(setup,preferences=FanPreferences(favorite_player_ids=['h3']))
    passer=build(setup,preferences=FanPreferences(favorite_player_ids=['h1']))
    analyst=build(setup,preferences=FanPreferences(favorite_player_ids=['h1'],depth='analyst'))
    assert 'Alex Finch completed 1 pass' in passer['text']
    assert passer['facts'][0]['subject_id']=='h1' and passer['facts'][0]['value']==1
    assert 'recorded sequence spans 8 seconds and involves 3 players' in analyst['text']
    assert {scorer['id'],passer['id'],analyst['id']}=={'test-match:e5:buildup'}
    assert len({scorer['content_version'],passer['content_version'],analyst['content_version']})==3
    assert scorer['evidence']['evidence_fingerprint']==passer['evidence']['evidence_fingerprint']
    assert 'assist' not in passer['text']


def test_card_expires_at_fixed_occurrence_time_not_delayed_revision(setup):
    assert build(setup,38999)
    assert build(setup,39000) is None
    es=setup[2]
    late=es[-1].model_copy(update={'revision':2,'delivery_sequence':6,'available_ms':40000})
    assert build(setup,40000,events=es+[late]) is None


def test_retraction_withdrawal_restore_and_duplicate_delivery(setup):
    es=setup[2];original=build(setup)
    retract=es[-1].model_copy(update={'revision':2,'delivery_sequence':6,'available_ms':10000,'retracted':True})
    restore=es[-1].model_copy(update={'revision':3,'delivery_sequence':7,'available_ms':11000})
    assert build(setup,9500,events=es+[retract])==original
    assert build(setup,10000,events=es+[retract]) is None
    restored=build(setup,11000,events=es+[retract,restore])
    assert restored['id']==original['id'] and restored['content_version']!=original['content_version']
    assert restored['ask_footie']['event_revision']==3
    assert restored==build(setup,11000,events=es+[retract,restore,restore])


def test_set_piece_leads_with_situation_instead_of_zero_pass_count(setup):
    es=setup[2]
    goal=es[-1].model_copy(update={'situation':'free_kick','restart':True})
    result=build(setup,events=[goal],preferences=FanPreferences(depth='analyst'))
    assert result['text']=='Cole Reed scored from a free kick.'
    assert result['facts'][0]['metric']=='goal_situation'
    assert result['evidence']['events'][0]['situation']=='free_kick'
    assert '0' not in result['text']
    penalty=goal.model_copy(update={'penalty':True,'situation':'penalty'})
    assert build(setup,events=[penalty])['text']=='Cole Reed scored from a penalty.'


def test_shot_only_unknown_buildup_gets_no_proactive_claim(setup):
    assert build(setup,events=[setup[2][-1]]) is None


def test_chinese_same_facts_separate_audience(setup):
    english=build(setup)
    chinese=build(setup,preferences=FanPreferences(language='zh-Hans'))
    assert english['facts']==chinese['facts']
    assert '夺回球权8秒后' in chinese['text']
    assert english['evidence']['audience_id']!=chinese['evidence']['audience_id']
    assert chinese['ask_footie']['question']=='这粒进球是如何形成的？'


def test_invalidated_buildup_replaces_content_without_invented_transfer(setup):
    es=setup[2]
    changed=es[1].model_copy(update={'revision':2,'delivery_sequence':6,'available_ms':10000,'recipient_id':'h3'})
    updated=build(setup,10000,events=es+[changed])
    assert updated['id']==build(setup)['id']
    assert updated['evidence']['coverage']['complete_possession'] is False
    assert '1 completed pass' in updated['text']
    assert updated['content_version']!=build(setup)['content_version']


def test_explicit_scorer_focus_takes_precedence_over_other_favorites(setup):
    result=build(setup,preferences=FanPreferences(favorite_player_ids=['h1','h3'],focus_player_id='h3'))
    assert result['text'].startswith('Cole Reed took the scoring shot')
    assert result['action']['subject_id']=='h3'
