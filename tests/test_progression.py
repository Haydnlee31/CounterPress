import json
import sqlite3
from pathlib import Path

from pydantic import TypeAdapter, ValidationError
import pytest

from counterpress.api.snapshots import BASELINE, CURRENT, END, SnapshotService
from counterpress.audience import ViewingPreferences
from counterpress.domain.models import Event, MatchTime, ObservationWindow
from counterpress.domain.pressure import Publication
from counterpress.domain.progression import ProgressionEvidence, ProgressionPolicy, analyze_progression
from counterpress.fixture import PossessionFixture, load_fixture
from counterpress.history import SQLiteHistoryStore
from counterpress.replay import ReplaySession

ROOT=Path(__file__).resolve().parents[1]
EXPECTED=json.loads((ROOT/'tests/expected_progression.json').read_text())


def fixture(name='increase'):
    return load_fixture(ROOT/f'fixtures/progression/{name}.json')


def time(ms):
    return MatchTime(period=2,elapsed_ms=ms)


def analyze(feed=None, *, cutoff=780000, baseline=BASELINE, current=CURRENT, **kwargs):
    session=feed if isinstance(feed,ReplaySession) else ReplaySession(feed or fixture(),end=time(max(cutoff,780000)))
    return analyze_progression(session,'eastbridge',baseline,current,time(cutoff),**kwargs)


def corrections():
    return TypeAdapter(tuple[Event,...]).validate_json((ROOT/'fixtures/progression/replay_corrections.json').read_text())


@pytest.mark.parametrize('name',['increase','control'])
def test_independent_controls_and_continuous_geometry(name):
    feed=fixture(name);expected=EXPECTED[name]
    ball=(30.0,34.0);holder='np04'
    for event in feed.events:
        own=event.actor.team_id=='eastbridge'
        position=(event.position.x,event.position.y) if own else (105-event.position.x,68-event.position.y)
        assert position == ball
        if event.action.kind=='recovery':
            holder=event.actor.player_id
        else:
            assert event.actor.player_id == holder
        if event.action.kind in ('pass','carry'):
            end=event.action.end_position
            ball=(end.x,end.y) if own else (105-end.x,68-end.y)
            if event.action.kind=='pass' and event.action.recipient:
                holder=event.action.recipient.player_id
    evidence=analyze(feed)
    for key,w in (('baseline',evidence.baseline),('current',evidence.current)):
        assert list(w.included)==expected[key+'_ids']
        assert list(w.without_progression)==expected[key+'_without_progression']
        assert [e.forward_gain_m for e in evidence.episodes if e.episode_id in w.included]==expected[key+'_gains']
        assert not w.pending and not w.boundary_excluded and not w.brief_excluded and not w.limited_space
    assert all(e.completed_actions==3 and e.controlled_span_ms==22000 for e in evidence.episodes)
    d=evidence.decisions[0]
    assert [d.baseline_numerator,d.baseline_denominator,d.current_numerator,d.current_denominator]==expected['fraction']
    assert d.status==expected['status']
    assert ProgressionEvidence.model_validate_json(evidence.model_dump_json())==evidence


def one_episode(*,start=181000,span=20000,gain=15.0,start_x=30.0,resolve=True):
    raw=fixture().model_dump(mode='json')
    # Explicitly place a controlled forward pass, backward pass and final carry.
    rows=raw['events'][1:7]
    rows[0]['position']['x']=start_x
    rows[1]['position']['x']=start_x;rows[1]['action']['end_position']['x']=start_x+gain
    rows[2]['position']['x']=start_x+gain;rows[2]['action']['end_position']['x']=start_x
    rows[3]['position']['x']=start_x;rows[3]['action']['end_position']['x']=start_x+1
    rows[4]['position']['x']=start_x+1;rows[4]['action']['end_position']['x']=start_x
    rows[5]['position']['x']=105-start_x
    for row,offset in zip(rows,(0,5000,10000,span,span+1000,span+2000)):
        row['occurred_at']['elapsed_ms']=row['available_at']['elapsed_ms']=start+offset
    raw['events']=rows if resolve else rows[:-1]
    return PossessionFixture.model_validate_json(json.dumps(raw))


@pytest.mark.parametrize('gain,stalled',[(14.999,True),(15.0,False),(20.0,False)])
def test_furthest_controlled_position_and_exact_gain_threshold(gain,stalled):
    evidence=analyze(one_episode(gain=gain))
    assert evidence.baseline.completed==1
    assert evidence.baseline.without_progression_count==int(stalled)
    assert evidence.episodes[0].forward_gain_m==gain


@pytest.mark.parametrize('start,span,category',[(181000,19999,'brief_excluded'),(181000,20000,'included'),
    (180000,20000,'boundary_excluded'),(480000,20000,'boundary_excluded'),(458000,20000,'included')])
def test_observation_span_and_window_boundaries(start,span,category):
    evidence=analyze(one_episode(start=start,span=span))
    w=evidence.current if start>=480000 else evidence.baseline
    assert getattr(w,category)==('b1-start',)


def test_cross_window_episode_is_pending_then_boundary_excluded():
    evidence=analyze(one_episode(start=470000))
    assert evidence.baseline.pending==('b1-start',)
    assert evidence.current.boundary_excluded==('b1-start',)
    assert evidence.baseline.completed==evidence.current.completed==0


def test_unfinished_possessions_never_enter_denominator():
    evidence=analyze(one_episode(resolve=False))
    assert evidence.episodes[0].end is None and evidence.current.pending==('b1-start',)
    assert evidence.baseline.pending==('b1-start',) and evidence.baseline.rate is None
    assert evidence.decisions[0].change is None


def test_initial_possession_without_observed_recovery_is_censored():
    raw=one_episode().model_dump(mode='json');raw['events']=raw['events'][1:]
    raw['initial_state']['controlled_possession_team_id']='eastbridge'
    evidence=analyze(PossessionFixture.model_validate_json(json.dumps(raw)))
    assert evidence.baseline.left_censored==('b1-pass1',) and evidence.baseline.completed==0


@pytest.mark.parametrize('start_x,category',[(90.0,'included'),(90.001,'limited_space')])
def test_no_progression_requires_enough_forward_space(start_x,category):
    evidence=analyze(one_episode(start_x=start_x,gain=1.0))
    assert getattr(evidence.baseline,category)==('b1-start',)


def test_incomplete_pass_endpoint_cannot_manufacture_progression_or_duration():
    raw=one_episode(gain=5,span=19000).model_dump(mode='json')
    loss=raw['events'][-2];loss['action']['end_position']['x']=100.0
    loss['occurred_at']['elapsed_ms']=loss['available_at']['elapsed_ms']=300000
    raw['events'][-1]['occurred_at']['elapsed_ms']=raw['events'][-1]['available_at']['elapsed_ms']=310000
    evidence=analyze(PossessionFixture.model_validate_json(json.dumps(raw)))
    assert evidence.episodes[0].forward_gain_m==5 and evidence.episodes[0].controlled_span_ms==19000
    assert evidence.baseline.brief_excluded==('b1-start',)


def test_zero_distance_carry_does_not_satisfy_completed_action_minimum():
    raw=one_episode(gain=5).model_dump(mode='json')
    raw['events'][3]['action']['end_position']=raw['events'][3]['position']
    evidence=analyze(PossessionFixture.model_validate_json(json.dumps(raw)))
    assert evidence.episodes[0].completed_actions==2
    assert evidence.baseline.brief_excluded==('b1-start',)


def test_minimum_required_separately_in_each_window():
    a=analyze(policy=ProgressionPolicy(minimum_episodes=7))
    assert a.decisions[0].status=='insufficient_sample'
    b=analyze(current=ObservationWindow(start=BASELINE.end,end=time(560000)))
    assert b.baseline.completed==6 and b.current.completed==2
    assert b.decisions[0].status=='insufficient_sample'
    c=analyze(baseline=ObservationWindow(start=time(360000),end=BASELINE.end))
    assert c.baseline.completed==2 and c.current.completed==6 and c.decisions[0].status=='insufficient_sample'


def test_cooldown_scope_expiry_and_correction_bypass():
    receipt=Publication(match_id=fixture().match_id,team_id='eastbridge',metric='possession_without_progression',
        baseline=ObservationWindow(start=time(180000),end=time(300000)),current=ObservationWindow(start=time(300000),end=time(400000)),published_at=time(750000))
    assert analyze(publications=(receipt,)).decisions[0].status=='cooldown'
    assert analyze(cutoff=810000,publications=(receipt,)).decisions[0].status=='eligible'
    for update in ({'metric':'pressure_exposure'},{'team_id':'northport'},{'published_at':time(785000)}, {'baseline':BASELINE,'current':CURRENT,'published_at':END}):
        assert analyze(publications=(receipt.model_copy(update=update),)).decisions[0].status=='eligible'


def test_late_resolution_is_pending_until_available():
    raw=one_episode(start=750000).model_dump(mode='json')
    raw['events'][-1]['available_at']['elapsed_ms']=785000
    feed=PossessionFixture.model_validate_json(json.dumps(raw))
    assert analyze(feed).current.pending==('b1-start',)
    assert analyze(feed,cutoff=785000).current.included==('b1-start',)


@pytest.mark.parametrize('change',[{'forward_gain_m':float('nan')},{'forward_gain_m':0},{'minimum_completed_actions':0},{'minimum_controlled_span_ms':-1}])
def test_invalid_policy(change):
    with pytest.raises(ValidationError):ProgressionPolicy(**change)


def test_evidence_rejects_invented_rates_or_missing_source_revisions():
    raw=analyze().model_dump()
    raw['current']['rate']=0.99
    with pytest.raises(ValidationError):ProgressionEvidence.model_validate(raw)
    raw=analyze().model_dump();raw['records']=raw['records'][2:]
    with pytest.raises(ValidationError,match='missing'):ProgressionEvidence.model_validate(raw)


def test_durable_update_withdraw_restore_and_historical_evidence(tmp_path):
    db=tmp_path/'history.sqlite3';s=SnapshotService(ROOT/'fixtures',SQLiteHistoryStore(db))
    original=s.snapshot('progression-increase',780000)
    assert original.selected_kind=='pressure' and original.pressure.publication.metric=='possession_without_progression'
    result=s.ingest('progression-increase',corrections())
    changes=[c for c in result.pressure_changes if c.metric=='possession_without_progression']
    assert [(c.revision,c.operation,c.decision.current_numerator) for c in changes]==[(1,'create',4),(2,'update',3),(3,'withdraw',1),(4,'create',4)]
    assert s.ingest('progression-increase',corrections())==result
    restarted=SnapshotService(tmp_path/'no-fixtures',SQLiteHistoryStore(db))
    assert restarted.snapshot('progression-increase',780000).pressure==original.pressure
    assert restarted.snapshot('progression-increase',790000).selected_kind is None
    assert restarted.snapshot('progression-increase',795000).pressure.publication.revision==4
    assert restarted.pressure_evidence('progression-increase',changes[0].insight_id,3,790000).operation=='withdraw'
    with pytest.raises(KeyError):restarted.pressure_evidence('progression-increase',changes[0].insight_id,4,790000)


def test_new_rule_backfill_does_not_rewrite_existing_pressure_publications(tmp_path):
    seed=SnapshotService(ROOT/'fixtures');prior=seed.ingest('pressure-increase',TypeAdapter(tuple[Event,...]).validate_json((ROOT/'fixtures/pressure/replay_corrections.json').read_text()))
    store=SQLiteHistoryStore(tmp_path/'legacy.sqlite3')
    store.transact('pressure-increase',lambda _:prior.model_copy(update={'episode_rules_version':0}))
    with sqlite3.connect(store.path) as db:
        db.execute('ALTER TABLE pressure_checkpoints DROP COLUMN rules_version')
    upgraded=SnapshotService(tmp_path/'no-fixtures',store).history('pressure-increase')
    assert upgraded.pressure_changes==prior.pressure_changes and upgraded.records==prior.records
    assert upgraded.episode_rules_version==2
    # A fully checkpointed old history with no progression streams gains them once.
    new=seed.history('progression-increase')
    store.transact('progression-increase',lambda _:new.model_copy(update={'pressure_changes':(),'episode_rules_version':0}))
    service=SnapshotService(tmp_path/'no-fixtures',store)
    assert len(service.history('progression-increase').pressure_changes)==1
    assert len(service.history('progression-increase').pressure_changes)==1


@pytest.mark.parametrize('language',['en','zh-Hans'])
def test_audience_controls_and_shared_budget(language):
    s=SnapshotService(ROOT/'fixtures')
    prefs=ViewingPreferences(language=language,depth='casual',player_id='eb08',metric_focus='possession_without_progression')
    x=s.snapshot('progression-increase',780000,preferences=prefs)
    assert '1/6' in x.pressure.variant.explanation and '4/6' in x.pressure.variant.explanation
    assert x.pressure.variant.language==language
    assert s.snapshot('progression-increase',780000,preferences=prefs.model_copy(update={'card_budget':0})).selected_kind is None
    assert s.snapshot('progression-control',780000).selected_kind is None
    assert not s.snapshot('progression-increase',779999).pressure_lifecycle
