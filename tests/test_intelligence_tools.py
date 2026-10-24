"""Hand-authored expected football accounting; no generator/model dependency."""
import gzip
from pathlib import Path
import pytest
from counterpress.domain.models import PitchPosition
from counterpress.personalization.contracts import Action, Appearance, Fixture, MatchRecord
from counterpress.assistant.intelligence import goal_buildup, involvement, compare_windows


def fixture(source='calibrated_simulation'):
    return Fixture(match_id='match-one', season='2026-27', kickoff='2026-10-19T15:00:00Z',
        home_id='home', away_id='away', competition='Test', source_kind=source,
        appearances=tuple(Appearance(player_id=p, club_id=c, start_ms=0, end_ms=5400000, starter=True)
                          for p,c in [('h1','home'),('h2','home'),('h3','home'),('a1','away')]))


def action(i,kind,ms,player='h1',club='home',**kw):
    defaults = dict(match_id='match-one',event_id=f'e{i}',revision=1,delivery_sequence=i,
        occurrence_order=i,period=1,elapsed_ms=ms,available_period=1,available_ms=ms,
        club_id=club,player_id=player,kind=kind,outcome='established',source_reference=f'test:e{i}')
    return Action(**(defaults|kw))


def play():
    # Independently specified: regain at 10s and x25, 2 passes, 1 carry,
    # shot at20s/x91. Three participants;10 seconds;66m net progression.
    return [action(1,'recovery',10000,start=PitchPosition(x=25,y=30)),
        action(2,'pass',12000,outcome='completed',recipient_id='h2'),
        action(3,'pressure',13000,player='a1',club='away'),
        action(4,'pass',16000,player='h2',outcome='completed',recipient_id='h3'),
        action(5,'carry',18000,player='h3',outcome='controlled'),
        action(6,'shot',20000,player='h3',outcome='goal',goal_for='home',available_ms=20700,
               start=PitchPosition(x=91,y=34),end=PitchPosition(x=105,y=34))]


def test_complete_buildup_expected_facts_and_contributions():
    result=goal_buildup(fixture(),play(),event_id='e6',cutoff=(1,20700),expected_revision=1)
    assert result['metrics']==dict(completed_passes=2,carry_count=1,participant_count=3,
        observed_duration_seconds=10,regain_to_shot_seconds=10,net_progression_m=66)
    assert result['coverage']['complete_possession'] is True
    assert result['coverage']['assist_credit']=='not_inferred'
    assert [r['event_id'] for r in result['timeline']]==['e1','e2','e3','e4','e5','e6']
    rows={c['player_id']:c for c in result['contributions']}
    assert set(rows)=={'h1','h2','h3'}
    assert (rows['h2']['receptions'],rows['h2']['completed_passes'])==(1,1)
    assert (rows['h3']['receptions'],rows['h3']['carries'],rows['h3']['shots'])==(1,1,1)


def test_goal_not_visible_until_outcome_available():
    assert goal_buildup(fixture(),play(),event_id='e6',cutoff=(1,20699))['reason']=='selected_event_not_visible'


def test_latest_revision_available_then_retracted_or_changed():
    events=play();goal=events[-1]
    revision=goal.model_copy(update={'revision':2,'delivery_sequence':7,'available_ms':25000,'retracted':True})
    assert goal_buildup(fixture(),events+[revision],event_id='e6',cutoff=(1,24999))['status']=='available'
    assert goal_buildup(fixture(),events+[revision],event_id='e6',cutoff=(1,25000))['status']=='unavailable'
    changed=revision.model_copy(update={'retracted':False,'outcome':'saved','goal_for':None})
    assert goal_buildup(fixture(),events+[changed],event_id='e6')['reason']=='selected_event_is_not_a_goal'
    assert goal_buildup(fixture(),events+[goal.model_copy(update={'revision':2,'delivery_sequence':7})],event_id='e6',expected_revision=1)['reason']=='selected_revision_changed'


def test_duplicates_idempotent_and_conflicts_rejected():
    events=play()
    assert goal_buildup(fixture(),events+events,event_id='e6')==goal_buildup(fixture(),events,event_id='e6')
    with pytest.raises(ValueError,match='Conflicting'):
        goal_buildup(fixture(),events+[events[0].model_copy(update={'outcome':'lost'})],event_id='e6')
    with pytest.raises(ValueError,match='another match'):
        goal_buildup(fixture(),[events[0].model_copy(update={'match_id':'another'})],event_id='e6')


@pytest.mark.parametrize('barrier',[
    dict(kind='duel',outcome='won'),dict(kind='other',outcome='unknown'),
    dict(kind='pass',outcome='incomplete'),dict(kind='pass',outcome='unknown'),
    dict(kind='carry',outcome='unknown'),dict(kind='pass',outcome='complete',club_id='away',player_id='a1'),
    dict(kind='shot',outcome='blocked')])
def test_uncertain_continuity_cannot_claim_regain(barrier):
    events=play();events[1]=events[1].model_copy(update=barrier|{'recipient_id':None})
    result=goal_buildup(fixture(),events,event_id='e6')
    assert not result['coverage']['start_known']
    assert result['metrics']['regain_to_shot_seconds'] is None
    assert result['metrics']['observed_duration_seconds']==4


def test_period_boundary_not_a_known_possession_start():
    events=play()
    events[-1]=events[-1].model_copy(update={'period':2,'elapsed_ms':1000,'available_period':2,'available_ms':2000})
    result=goal_buildup(fixture(),events,event_id='e6')
    assert result['coverage']['start_reason']=='period_boundary'
    assert result['metrics']['completed_passes']==0


def test_restart_and_missing_geometry_are_distinct():
    events=play()[1:];events[0]=events[0].model_copy(update={'restart':True})
    result=goal_buildup(fixture(),events,event_id='e6')
    assert result['coverage']['start_known']
    assert result['metrics']['regain_to_shot_seconds'] is None
    assert result['metrics']['net_progression_m'] is None


def test_involvement_counts_and_denominators_are_not_touches():
    result=involvement(fixture(),play(),player_id='h2',cutoff=(1,21000))
    assert result['metrics']==dict(passes=1,completed_passes=1,receptions=1,carries=0,shots=0,
                                   recoveries=0,observed_actions=1,action_share_pct=20,minutes=.35)
    assert result['denominators']['team_actions']==5
    assert result['coverage']['basis']=='recorded_actions'


def test_unknown_recipient_and_archive_missingness_not_zero():
    events=play();events[1]=events[1].model_copy(update={'recipient_id':None,'outcome':'complete'})
    result=involvement(fixture(),events,player_id='h2')
    assert result['metrics']['receptions'] is None
    result=involvement(fixture('adapted_archive'),events,player_id='h2')
    assert result['metrics']['recoveries'] is None
    assert result['metrics']['carries'] is None


def test_changes_equal_complete_windows_no_change_control():
    events=[action(i,'pass',ms,outcome='completed',recipient_id='h2') for i,ms in enumerate([0,1000,2000,3000,4000],1)]
    result=compare_windows(fixture(),events,club_id='home',period=1,start_ms=0,split_ms=2000,end_ms=4000,cutoff=(1,4000),min_actions=2)
    assert result['status']=='available'
    assert result['before']['passes']==result['after']['passes']==2
    assert set(result['delta'].values())=={0}
    assert [r['event_id'] for r in result['evidence']]==['e2','e3','e4','e5']
    assert compare_windows(fixture(),events,club_id='home',period=1,start_ms=0,split_ms=2000,end_ms=4000,cutoff=(1,3999),min_actions=2)['reason']=='window_not_completed'
    assert compare_windows(fixture(),events,club_id='home',period=1,start_ms=0,split_ms=2000,end_ms=5000,cutoff=(1,5000))['reason']=='incomparable_windows'
    assert compare_windows(fixture(),events,club_id='home',period=1,start_ms=0,split_ms=2000,end_ms=4000,cutoff=(1,4000))['reason']=='insufficient_observations'


def test_all_featured_goals_are_accounted_with_real_source_coverage():
    paths=[p for p in Path('fixtures/personalization').glob('*.json.gz') if p.name!='ledger.json.gz']
    assert len(paths)==4
    count=0;known=0
    for path in paths:
        record=MatchRecord.model_validate_json(gzip.decompress(path.read_bytes()))
        for e in record.events:
            if e.kind!='shot' or e.outcome!='goal':continue
            result=goal_buildup(record.fixture,record.events,event_id=e.event_id,cutoff=(e.available_period,e.available_ms))
            assert result['status']=='available'
            assert result['timeline'][-1]['event_id']==e.event_id
            assert all(r['period']==e.period and r['elapsed_ms']<=e.elapsed_ms for r in result['evidence'])
            if record.fixture.source_kind=='adapted_archive':assert not result['coverage']['start_known'] or e.penalty
            count+=1;known+=result['coverage']['start_known']
    assert count==19
    assert known>0


def test_unobserved_transfer_does_not_connect_a_known_regain():
    events=play()
    # Recorded pass reaches h3, but h2 then makes the next pass: no recorded
    # h3-to-h2 action is present. Never invent it to connect the earlier regain.
    events[1]=events[1].model_copy(update={'recipient_id':'h3'})
    result=goal_buildup(fixture(),events,event_id='e6')
    assert result['coverage']['start_reason']=='unobserved_transfer'
    assert result['coverage']['complete_possession'] is False
    assert result['metrics']['regain_to_shot_seconds'] is None
    assert result['metrics']['completed_passes']==1


def test_failed_recoveries_not_counted_as_regains():
    events=play();events[0]=events[0].model_copy(update={'outcome':'lost'})
    assert involvement(fixture(),events,player_id='h1')['metrics']['recoveries']==0
    assert goal_buildup(fixture(),events,event_id='e6')['metrics']['regain_to_shot_seconds'] is None


def test_unknown_recipient_prevents_complete_chain_claim():
    events=play();events[1]=events[1].model_copy(update={'outcome':'complete','recipient_id':None})
    result=goal_buildup(fixture(),events,event_id='e6')
    assert result['coverage']['start_known'] is True
    assert result['coverage']['complete_possession'] is False


def test_invalid_window_start_unavailable():
    assert involvement(fixture(),play(),player_id='h1',window_start=(3,0))['reason']=='invalid_observation_window'


def test_unvalidated_copy_cannot_bypass_temporal_coherence():
    events=play();events[-1]=events[-1].model_copy(update={'available_ms':1})
    with pytest.raises(ValueError,match='Availability precedes occurrence'):
        goal_buildup(fixture(),events,event_id='e6')


def test_revision_identity_and_chronology_cannot_change():
    events=play();goal=events[-1]
    bad=goal.model_copy(update={'revision':2,'delivery_sequence':7,'occurrence_order':100})
    with pytest.raises(ValueError,match='Occurrence order is immutable'):
        goal_buildup(fixture(),events+[bad],event_id='e6')
    bad=goal.model_copy(update={'revision':2,'delivery_sequence':7,'available_ms':20500})
    with pytest.raises(ValueError,match='Revision chronology'):
        goal_buildup(fixture(),events+[bad],event_id='e6')


@pytest.mark.parametrize('source', ['calibrated_simulation', 'adapted_archive'])
def test_unknown_pass_outcomes_are_observed_counts_not_complete_totals(source):
    events = [action(1, 'pass', 1000, outcome='unknown'),
              action(2, 'pass', 2000, outcome='incomplete'),
              action(3, 'pass', 3000, outcome='completed', recipient_id='h2')]
    result = involvement(fixture(source), events, player_id='h1', cutoff=(1, 3000))
    assert result['metrics']['passes'] == 3
    assert result['metrics']['completed_passes'] == 1
    assert result['metric_labels']['completed_passes'] == 'Recorded completed passes'
    assert result['denominators']['passes_with_known_outcomes'] == 2
    assert result['coverage']['unknown_pass_outcomes'] == 1
    assert result['coverage']['pass_outcomes_complete'] is False
    empty_known = involvement(fixture(source), events[:1], player_id='h1', cutoff=(1, 1000))
    assert empty_known['metrics']['completed_passes'] == 0  # zero observed, not zero actual
    assert empty_known['denominators']['passes_with_known_outcomes'] == 0
    assert empty_known['coverage']['pass_outcomes_complete'] is False


def test_unknown_team_pass_cannot_claim_zero_receptions_and_revision_restores_coverage():
    event = action(1, 'pass', 1000, outcome='unknown')
    corrected = event.model_copy(update={'revision': 2, 'delivery_sequence': 2,
        'available_ms': 3000, 'outcome': 'completed', 'recipient_id': 'h2'})
    before = involvement(fixture(), [event, corrected], player_id='h2', cutoff=(1, 2999))
    assert before['metrics']['receptions'] is None
    assert before['coverage']['receptions_complete'] is False
    # The receiver's own passing completeness is distinct from team reception coverage.
    assert before['coverage']['pass_outcomes_complete'] is True
    assert before['denominators']['team_unknown_pass_outcomes'] == 1
    after = involvement(fixture(), [event, corrected], player_id='h2', cutoff=(1, 3000))
    assert after['metrics']['receptions'] == 1
    assert after['coverage']['receptions_complete'] is True
    assert after['evidence'][0]['revision'] == 2


def test_comparison_pass_coverage_is_per_window_and_uses_available_revision():
    first = action(1, 'pass', 1000, outcome='unknown')
    second = action(2, 'pass', 3000, outcome='completed', recipient_id='h2')
    corrected = first.model_copy(update={'revision': 2, 'delivery_sequence': 3,
        'available_ms': 5000, 'outcome': 'incomplete'})
    args = dict(club_id='home', period=1, start_ms=0, split_ms=2000, end_ms=4000, min_actions=1)
    before = compare_windows(fixture(), [first, second, corrected], cutoff=(1, 4000), **args)
    assert before['before']['completed_passes'] == 0
    assert before['after']['completed_passes'] == 1
    assert before['coverage']['pass_outcomes_complete'] is False
    assert before['coverage']['pass_outcomes_complete_by_window'] == [False, True]
    assert before['coverage']['unknown_pass_outcomes'] == [1, 0]
    assert before['metric_labels']['completed_passes'] == 'Recorded completed passes'
    after = compare_windows(fixture(), [first, second, corrected], cutoff=(1, 5000), **args)
    assert after['coverage']['pass_outcomes_complete'] is True
    assert after['coverage']['unknown_pass_outcomes'] == [0, 0]
    assert after['before'] == before['before']  # same known successes, different coverage
