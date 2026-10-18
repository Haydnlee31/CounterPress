"""Checks for generated football continuity, reproducibility and calibration separation."""
import json
import math
from pathlib import Path
from counterpress.fixture import load_fixture
from counterpress.generator.calibrated import fit, generate_full, generated_metrics
from counterpress.gi.service import read_match

ROOT=Path(__file__).resolve().parents[1]
MODEL=json.loads((ROOT/'fixtures/generator/calibrated/model.json').read_text())
REPORT=json.loads((ROOT/'fixtures/generator/calibrated/report.json').read_text())


def test_calibration_uses_disjoint_whole_matches_and_only_aggregates():
    train={m['id'] for m in REPORT['training_matches']}
    holdout={m['id'] for m in REPORT['holdout_matches']}
    assert len(train)==15 and len(holdout)==5 and train.isdisjoint(holdout)
    assert set(MODEL['fit_match_ids'])==train
    assert not train.intersection({2058007,2058017})
    assert MODEL['source_event_count']==23753
    assert 'events' not in MODEL and 'players' not in MODEL
    sample={'matchId':1,'matchPeriod':'1H','eventSec':1,'id':1,'teamId':1,'eventName':'Pass','subEventName':'Simple pass','positions':[{'x':20,'y':30},{'x':40,'y':40}],'tags':[{'id':1801}]}
    assert fit([sample], [1])==fit([sample,{**sample,'matchId':2,'positions':[{'x':100,'y':100}]}],[1])


def test_showcase_reproduces_exactly_and_has_new_native_identities():
    expected=load_fixture(ROOT/'fixtures/gi/synthetic/events.json')
    generated=generate_full(MODEL,74)
    assert generated==expected
    assert generate_full(MODEL,75).match_id!=generated.match_id
    assert generated_metrics(generated)=={'passes':815,'pass_completion':700/815,'shots':23,'goals':4}
    assert len({p for t in generated.teams for p in t.player_ids})==22
    assert all(e.match_id==generated.match_id and e.event_id.startswith('a') for e in generated.events)
    match=read_match(ROOT/'fixtures/gi',generated.match_id)
    assert match.synthetic and match.video_url is None
    assert [t.score for t in match.teams]==[2,2]
    assert [e.goal_for for e in match.events if e.goal_for]==[9598,4418,4418,9598]
    assert all(e.provider_event_id is None for e in match.events)


def test_ball_and_possession_are_continuous_in_multiple_generated_matches():
    for seed in (0,19,74,99):
        feed=generate_full(MODEL,seed)
        assert {e.occurred_at.period for e in feed.events}=={1,2}
        for previous,current in zip(feed.events,feed.events[1:]):
            if previous.occurred_at.period!=current.occurred_at.period:continue
            assert current.available_at.key()>=previous.available_at.key()
            action=previous.action
            if action.kind not in ('pass','carry'):continue
            end=action.end_position
            mirrored=current.actor.team_id!=previous.actor.team_id
            target=(105-end.x,68-end.y) if mirrored else (end.x,end.y)
            assert math.isclose(current.position.x,target[0],abs_tol=.002)
            assert math.isclose(current.position.y,target[1],abs_tol=.002)
            if action.kind=='pass' and action.outcome=='completed':assert current.actor==action.recipient
            distance=math.hypot(end.x-previous.position.x,end.y-previous.position.y)
            seconds=(current.occurred_at.elapsed_ms-previous.occurred_at.elapsed_ms)/1000
            assert seconds>=distance/(25 if action.kind=='pass' else 7)-.002


def test_unselected_population_has_quiet_and_lively_games():
    rows=[generated_metrics(generate_full(MODEL,s)) for s in range(20)]
    assert min(r['goals'] for r in rows)==0
    assert max(r['goals'] for r in rows)>=4
    assert all(0.75<r['pass_completion']<.95 for r in rows)
    assert all(600<r['passes']<1200 and 5<r['shots']<50 for r in rows)
