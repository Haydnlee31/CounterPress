"""Independent concrete card expectations, durable corrections, observation pins."""
import importlib.util
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from counterpress.fan.api import install_fan
from counterpress.personalization.api import install_personalization
from counterpress.personalization.journal import SQLiteCareerJournal
from counterpress.personalization.store import DataStore

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('card_lifecycle_check', ROOT / 'scripts/check_fan_card_lifecycle.py')
check = importlib.util.module_from_spec(spec)
spec.loader.exec_module(check)


def test_real_fixture_two_audiences_full_durable_card_lifecycle(tmp_path):
    report = check.verify(tmp_path)
    assert report['generations'] == [0, 1, 2, 2, 3, 4]
    assert report['checkpointed_deliveries'] == 5
    assert len({report[key] for key in ('baseline_evidence', 'corrected_evidence', 'restored_evidence')}) == 3
    assert report['context_available_after_409']
    assert report['azure_calls'] == report['model_calls'] == 0


def test_check_refuses_to_reuse_an_existing_journal(tmp_path):
    target = tmp_path / 'card-lifecycle.sqlite3'
    target.write_text('leave-existing-state-alone')
    with pytest.raises(AssertionError, match='fresh isolated journal'):
        check.verify(tmp_path)
    assert target.read_text() == 'leave-existing-state-alone'


def test_same_availability_later_delivery_does_not_change_pinned_view(tmp_path, monkeypatch):
    # Availability timestamps need not be unique. A fixed time alone does not pin
    # the knowledge boundary when a valid later delivery shares that timestamp.
    monkeypatch.setenv('COUNTERPRESS_PROFILE_DB_PATH', ':memory:')
    path = tmp_path / 'same-time.sqlite3'
    writer_journal, reader_journal = SQLiteCareerJournal(path), SQLiteCareerJournal(path)
    writer = DataStore(ROOT / 'fixtures/personalization', journal=writer_journal)
    app = FastAPI()
    get_career = install_personalization(app, ROOT / 'fixtures', reader_journal)
    install_fan(app, get_career)
    expected = check.EXPECTED
    mid, hid = expected['match_id'], expected['highlight_id']
    original = writer.original(mid)
    goal = next(e for e in original.events if e.event_id == 'e01019')
    sequence = max(e.delivery_sequence for e in original.events)
    payload = {'cutoff': expected['original_cutoff'], 'through_sequence': sequence,
               'card_budget': 5, 'preferences': {'favorite_player_ids': ['rh04']}}
    try:
        with TestClient(app) as client:
            def cards(body):
                response = client.post(f'/api/fan/matches/{mid}', json=body)
                assert response.status_code == 200
                return [c for c in response.json()['cards'] if c['kind'] == 'goal_buildup']
            before = cards(payload)
            assert len(before) == 1 and before[0]['text'] == expected['baseline']['casual']
            retraction = goal.model_copy(update={'revision': 2, 'delivery_sequence': sequence + 1,
                                                 'retracted': True})
            assert writer.ingest(mid, [retraction])['accepted'] == 1
            metadata = client.get(f'/api/data/highlights/{hid}/context').json()
            assert metadata['original_cutoff'] == metadata['latest_cutoff'] == expected['original_cutoff']
            assert metadata['original_sequence'] == sequence
            assert metadata['latest_sequence'] == sequence + 1
            assert metadata['goal']['retracted'] is True
            assert cards(payload) == before
            assert cards({**payload, 'through_sequence': sequence + 1}) == []
            assert cards({**payload, 'through_sequence': None}) == []
            assert client.get(f'/api/data/highlights/{hid}/replay').status_code == 409
    finally:
        get_career().store.close()
        writer.close()
        writer_journal.close()
        reader_journal.close()
