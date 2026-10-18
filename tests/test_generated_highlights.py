import json
from pathlib import Path
from fastapi.testclient import TestClient
from counterpress.api.main import create_app
from counterpress.fixture import load_fixture
ROOT=Path(__file__).resolve().parents[1]


def test_highlights_preserve_parent_actions_and_score_context():
    parent=load_fixture(ROOT/'fixtures/gi/synthetic/events.json')
    by_id={e.event_id:e for e in parent.events}
    manifest=json.loads((ROOT/'fixtures/showcases/generated_manifest.json').read_text())
    assert manifest['parent_match_id']==parent.match_id
    assert len(manifest['highlights'])==3
    with TestClient(create_app()) as client:
        for item,score in zip(manifest['highlights'],[(1,1),(2,1),(2,2)]):
            clip=load_fixture(ROOT/f"fixtures/showcases/{item['scenario_id']}.json")
            assert len(clip.events)==6
            for event,ref in zip(clip.events,item['events']):
                original=by_id[ref['event_id']]
                assert event.action==original.action and event.actor==original.actor and event.position==original.position
                assert ref['parent_time']==original.occurred_at.model_dump()
                assert event.available_at==event.occurred_at
            data=client.get(f"/api/scenarios/{item['scenario_id']}/snapshot?at_ms=780000").json()
            assert data['state']['score']==dict(zip(('eastbridge','northport'),score))
            assert len(data['pitch_events'])==6
            assert data['insight'] is None


def test_archive_dates_are_distinct_presentation_dates():
    with TestClient(create_app()) as client:
        dates=[client.get('/api/gi/matches/'+mid).json()['display_date'] for mid in
               ['wyscout-2058017','wyscout-2058007','synthetic-32fe41c5d304ce68d7d9']]
        assert dates==['2026-10-16','2026-10-17','2026-10-18']
