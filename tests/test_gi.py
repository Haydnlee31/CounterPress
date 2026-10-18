"""Independent full-match expectations, including missing data and own-goal accounting."""
import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from counterpress.api.main import create_app
from counterpress.gi.service import read_match

ROOT = Path(__file__).resolve().parents[1] / 'fixtures'


def test_full_match_outcomes_and_lineage():
    match = read_match(ROOT / 'gi')
    assert len(match.events) == 1462
    assert len({e.event_id for e in match.events}) == 1462
    assert [sum(e.period == p for e in match.events) for p in (1, 2)] == [651, 811]
    assert [t.score for t in match.teams] == [4, 2]
    assert len(match.players) == len({p.alias_id for p in match.players}) == 27
    for tid, passes, complete, incomplete, unknown, shots, off in [
        (4418, 241, 186, 55, 0, 8, 1), (9598, 518, 429, 88, 1, 14, 6)
    ]:
        events = [e for e in match.events if e.team_id == tid]
        pp = [e for e in events if e.kind == 'Pass']
        assert len(pp) == passes
        assert [sum(e.outcome == o for e in pp) for o in ('complete', 'incomplete', 'unknown')] == [complete, incomplete, unknown]
        assert sum(e.kind == 'Shot' for e in events) == shots
        assert sum(e.kind == 'Shot' and e.outcome == 'off_target' for e in events) == off
    own = next(e for e in match.events if e.provider_event_id == 263884274)
    assert (own.team_id, own.goal_for, own.outcome) == (9598, 4418, 'own_goal')
    missing = next(e for e in match.events if e.kind == 'Pass' and e.outcome == 'unknown')
    assert missing.end is None
    assert [e.occurrence_order for e in match.events] == list(range(1, 1463))
    assert len({e.source_order for e in match.events}) == 1462
    assert [(e.period, e.elapsed_ms) for e in match.events] == sorted((e.period, e.elapsed_ms) for e in match.events)
    assert read_match(ROOT / 'gi') == match


def test_api_and_unknown_match():
    with TestClient(create_app()) as client:
        response = client.get('/api/gi/matches/wyscout-2058017')
        assert response.status_code == 200
        payload = response.json()
        assert len(payload['events']) == 1462
        assert payload['video_alignment'] == 'unverified'
        assert payload['source']['license'] == 'CC BY 4.0'
        assert client.get('/api/gi/matches/other').status_code == 404


def test_corrupt_source_fails_closed(tmp_path):
    root = tmp_path / 'gi'
    root.mkdir()
    (root / 'manifest.json').write_text((ROOT / 'gi/manifest.json').read_text())
    (root / 'france-croatia-2018.json').write_text('[]')
    with pytest.raises(ValueError, match='checksum'):
        read_match(root)
    with TestClient(create_app(fixture_dir=tmp_path)) as client:
        assert client.get('/api/gi/matches/wyscout-2058017').status_code == 503


def test_comeback_match_independent_counts_and_masking():
    match = read_match(ROOT / 'gi', 'wyscout-2058007')
    assert match.match_id == 'wyscout-2058007'
    assert [t.name for t in match.teams] == ['Eastbridge', 'Northport']
    assert [t.score for t in match.teams] == [3, 2]
    assert len(match.events) == len({e.event_id for e in match.events}) == 1682
    assert len(match.players) == len({p.alias_id for p in match.players}) == 26
    assert [sum(e.period == p for e in match.events) for p in (1, 2)] == [890, 792]
    assert [e.goal_for for e in match.events if e.goal_for] == [9598, 9598, 4418, 4418, 4418]
    for tid, passes, complete, incomplete, shots in [(4418,572,501,71,24),(9598,432,377,55,9)]:
        rows = [e for e in match.events if e.team_id == tid]
        assert sum(e.kind == 'Pass' for e in rows) == passes
        assert sum(e.kind == 'Pass' and e.outcome == 'complete' for e in rows) == complete
        assert sum(e.kind == 'Pass' and e.outcome == 'incomplete' for e in rows) == incomplete
        assert sum(e.kind == 'Shot' for e in rows) == shots
    assert match.source.license == 'CC BY 4.0'
    assert match.source_label == 'Belgium–Japan, 2018'
    assert all(e.team_id in {4418,9598} for e in match.events)
    assert {e.player_id for e in match.events} <= {p.player_id for p in match.players}
    assert not ({e.event_id for e in match.events} & {e.event_id for e in read_match(ROOT / 'gi').events})
    with TestClient(create_app()) as client:
        assert client.get('/api/gi/matches/wyscout-2058007').json()['teams'][0]['score'] == 3
        assert client.get('/api/gi/matches/wyscout-2058017').json()['teams'][0]['score'] == 4
