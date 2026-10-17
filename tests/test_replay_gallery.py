"""Separately authored story expectations; no external tracking dataset is required."""
import json
from pathlib import Path
import pytest
from counterpress.api.snapshots import SnapshotService
from counterpress.fixture import load_fixture
from counterpress.replay import ReplaySession
from counterpress.domain.models import Event, MatchTime

ROOT = Path(__file__).resolve().parents[1]
EXPECTED = json.loads((ROOT / 'tests/expected_replay_gallery.json').read_text())

@pytest.mark.parametrize('scenario', EXPECTED)
def test_short_replays_have_continuous_ball_paths_and_independent_outcomes(scenario):
    expected = EXPECTED[scenario]
    fixture = load_fixture(ROOT / 'fixtures/showcases' / expected['file'])
    assert len({p for t in fixture.teams for p in t.player_ids}) == 22
    assert [e.actor.player_id for e in fixture.events] == expected['actors']
    assert [e.action.kind for e in fixture.events] == expected['kinds']
    assert fixture.events[-1].actor.player_id == expected['scorer']
    assert fixture.events[-1].occurred_at.elapsed_ms - fixture.events[0].occurred_at.elapsed_ms == expected['seconds'] * 1000
    for a,b in zip(fixture.events,fixture.events[1:]):
        assert a.action.end_position == b.position
    session = ReplaySession(fixture, end=MatchTime(period=2,elapsed_ms=782000))
    assert session.snapshot(MatchTime(period=2,elapsed_ms=779999)).state.score['eastbridge'] == expected['initial']
    result = session.snapshot(MatchTime(period=2,elapsed_ms=780000))
    assert result.state.score['eastbridge'] == expected['final']
    assert result.metrics[0].pass_completions == expected['passes']
    # A later save correction must retract the goal without altering the earlier view.
    correction = fixture.events[-1].model_dump()
    correction.update(revision=2,source_delivery_sequence=6,available_at={'period':2,'elapsed_ms':782000})
    correction['action'].update(outcome='saved',end_position={'x':103,'y':36})
    session.deliver((Event.model_validate(correction),))
    assert session.snapshot(MatchTime(period=2,elapsed_ms=782000)).state.score['eastbridge'] == expected['initial']
    assert session.snapshot(MatchTime(period=2,elapsed_ms=780000)).state.score['eastbridge'] == expected['final']
    show = SnapshotService(ROOT/'fixtures').snapshot(scenario,780000)
    assert show.insight is None and not show.recap.statements
    assert show.pressure_lifecycle == show.contribution_lifecycle == ()
