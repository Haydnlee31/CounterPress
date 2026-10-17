"""Independent story oracle, contract failures and canonical goal corrections."""
import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from counterpress.api.snapshots import SnapshotService
from counterpress.domain.models import Event, MatchTime, ShotDetails
from counterpress.fixture import PossessionFixture, load_fixture
from counterpress.replay import ReplaySession

ROOT = Path(__file__).resolve().parents[1]
EXPECTED = json.loads((ROOT / 'tests/expected_last_gasp.json').read_text())


def fixture():
    return load_fixture(ROOT / 'fixtures/showcases/last_gasp.json')


def at(ms):
    return MatchTime(period=2, elapsed_ms=ms)


def test_story_matches_separately_written_oracle_and_continuous_ball_path():
    f = fixture()
    assert f.initial_state.score == EXPECTED['initial_score']
    assert [e.event_id for e in f.events] == EXPECTED['event_ids']
    assert [e.action.kind for e in f.events] == EXPECTED['kinds']
    shots = [e for e in f.events if isinstance(e.action, ShotDetails)]
    assert [e.action.outcome for e in shots] == EXPECTED['shot_outcomes']
    assert all(e.action.goalkeeper.player_id == EXPECTED['goalkeeper_with_two_saves'] for e in shots[:2])
    assert shots[-1].actor.player_id == EXPECTED['scorer']
    assert shots[-1].event_id == EXPECTED['goal_id']
    assert f.events[-1].occurred_at.elapsed_ms - f.events[0].occurred_at.elapsed_ms == EXPECTED['duration_ms']
    # At a change of possession both axes invert; the ball must not teleport.
    def world(p, team):
        return (105-p.x, 68-p.y) if team == 'northport' else (p.x, p.y)
    for previous, following in zip(f.events, f.events[1:]):
        end = getattr(previous.action, 'rebound_position', None) or getattr(previous.action, 'end_position', previous.position)
        assert world(end, previous.actor.team_id) == world(following.position, following.actor.team_id)
    result = ReplaySession(f).snapshot(at(780000))
    assert result.state.score == EXPECTED['final_score']
    east, north = result.metrics
    assert east.pass_completions == EXPECTED['eastbridge_passes_completed']
    assert north.pass_attempts == EXPECTED['northport_pass_attempts']
    assert sum(len(m.high_recoveries) for m in result.metrics) == EXPECTED['high_recoveries']


def test_goals_follow_availability_rewind_revision_and_exact_retransmission():
    f = fixture()
    session = ReplaySession(f, end=at(782000))
    assert session.snapshot(at(779999)).state.score == EXPECTED['initial_score']
    assert session.snapshot(at(780000)).state.score == EXPECTED['final_score']
    session.deliver((f.events[-1], f.events[-1]))
    assert session.snapshot(at(780000)).state.score == EXPECTED['final_score']
    raw = f.events[-1].model_dump()
    raw.update(revision=2, source_delivery_sequence=11, available_at=at(782000).model_dump())
    raw['action'].update(outcome='saved', end_position={'x':103.0,'y':33.0})
    correction = Event.model_validate(raw)
    session.deliver((correction,))
    assert session.snapshot(at(781999)).state.score == EXPECTED['final_score']
    assert session.snapshot(at(782000)).state.score == EXPECTED['initial_score']
    assert session.snapshot(at(780000)).state.score == EXPECTED['final_score']
    assert session.snapshot(at(779999)).state.score == EXPECTED['initial_score']


@pytest.mark.parametrize('change', [
    {'outcome':'saved','goalkeeper':None},
    {'outcome':'goal','end_position':{'x':104.0,'y':34.0}},
    {'outcome':'goal','end_position':{'x':105.0,'y':40.0}},
    {'outcome':'goal','rebound_position':{'x':99.0,'y':34.0}},
    {'goalkeeper':{'team_id':'northport','player_id':'np01'}},
])
def test_invalid_shots_rejected(change):
    raw = fixture().events[0].model_dump()
    if change.get('outcome') == 'goal':
        raw['action']['rebound_position'] = None
    raw['action'].update(change)
    with pytest.raises(ValidationError):
        Event.model_validate(raw)


def test_unregistered_goalkeeper_rejected_in_fixture_and_deliveries():
    f = fixture()
    raw = f.model_dump()
    raw['events'][0]['action']['goalkeeper']['player_id'] = 'unregistered'
    with pytest.raises(ValidationError, match='registered'):
        PossessionFixture.model_validate(raw)
    with pytest.raises(ValueError, match='unregistered'):
        ReplaySession(f).deliver((Event.model_validate(raw['events'][0]),))


def test_showcase_is_isolated_and_does_not_publish_window_comparisons():
    service = SnapshotService(ROOT / 'fixtures')
    before = service.snapshot('increase', 780000)
    show = service.snapshot('last-gasp', 780000)
    assert show.state.score == EXPECTED['final_score']
    assert len(show.pitch_events) == 10
    assert show.insight is None
    assert show.pressure_lifecycle == show.contribution_lifecycle == ()
    assert not show.recap.statements
    assert service.snapshot('increase', 780000) == before
