#!/usr/bin/env python3
"""Bounded, offline card lifecycle check against the real journal/HTTP boundaries.

Uses fresh temporary SQLite journals only. No assistant, model, Azure client,
production configuration, network sender, or existing journal is opened.
"""
import asyncio
from contextlib import ExitStack
import json
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'backend'))
from fastapi import FastAPI
from fastapi.testclient import TestClient
from counterpress.fan.api import install_fan
from counterpress.personalization.api import install_personalization
from counterpress.personalization.journal import SQLiteCareerJournal
from counterpress.personalization.service import CareerService
from counterpress.personalization.store import DataStore
from counterpress.streaming.consumer import DeliveryProcessor
from counterpress.streaming.contracts import CareerDelivery

EXPECTED = json.loads((ROOT / 'fixtures/evaluation/fan_card_lifecycle.json').read_text())


def verify(folder: Path):
    """Return sanitized evidence; raise AssertionError on any lifecycle mismatch."""
    expected = EXPECTED
    mid, hid = expected['match_id'], expected['highlight_id']
    with ExitStack() as stack:
        path = folder / 'card-lifecycle.sqlite3'
        assert not path.exists(), 'Verification requires a fresh isolated journal'
        writer_journal = SQLiteCareerJournal(path)
        stack.callback(writer_journal.close)
        writer = DataStore(ROOT / 'fixtures/personalization', journal=writer_journal)
        stack.callback(writer.close)
        assert writer.dataset == expected['dataset'], 'Review independent expectations after dataset changes'
        readers = []
        # Install only read-only data/fan endpoints. Explicitly pin each index to
        # :memory: so a developer's PROFILE_DB_PATH cannot touch a real index.
        def reader():
            journal = SQLiteCareerJournal(path)
            stack.callback(journal.close)
            app = FastAPI()
            # install_personalization lazily constructs its service, so replace
            # its configured index path only while constructing this local app.
            import os
            from unittest.mock import patch
            with patch.dict(os.environ, {'COUNTERPRESS_PROFILE_DB_PATH': ':memory:'}):
                get_career = install_personalization(app, ROOT / 'fixtures', journal)
                api_career = get_career()
            stack.callback(api_career.store.close)
            install_fan(app, get_career)
            return stack.enter_context(TestClient(app))
        readers.extend([reader(), reader()])
        original = writer.original(mid)
        goal = next(e for e in original.events if e.event_id == expected['goal_event_id'])
        passing = next(e for e in original.events if e.event_id == expected['pass_event_id'])
        assert goal.revision == passing.revision == 1
        assert (goal.period, goal.elapsed_ms) == (2, 1050020)
        assert (goal.available_period, goal.available_ms) == (2, 1050489)
        # Derive unused sequences from this isolated complete source, not a guessed
        # production sequence. Stable occurrence identity stays untouched.
        sequence = max(e.delivery_sequence for e in original.events)
        notices, checkpoints, generations, scores = [], [], [0], []
        async def publish(notice):
            assert writer_journal.read(writer.dataset).generation == notice.generation
            notices.append(notice.generation)
        async def quarantine(*_):
            raise AssertionError('Valid lifecycle delivery was quarantined')
        async def checkpoint(event):
            assert len(notices) == len(checkpoints) + 1, 'Publish must precede checkpoint'
            checkpoints.append(event.sequence_number)
        processor = DeliveryProcessor(None, SimpleNamespace(publish=publish), quarantine,
                                      career_service=lambda: CareerService(writer))
        partition = SimpleNamespace(partition_id='local', update_checkpoint=checkpoint)
        def deliver(actions, delivery_id):
            payload = CareerDelivery(dataset=writer.dataset, delivery_id=delivery_id,
                                     match_id=mid, events=tuple(actions))
            message = SimpleNamespace(body=[payload.model_dump_json().encode()], partition_key=mid,
                                      sequence_number=len(checkpoints) + 1)
            asyncio.run(processor.process(partition, message))
            generations.append(writer.revision_state()['generation'])
        def view(client, depth, cutoff, through_sequence=None):
            response = client.post(f'/api/fan/matches/{mid}', json={
                'cutoff': cutoff, 'through_sequence': through_sequence, 'card_budget': 5,
                'preferences': {'favorite_player_ids': ['rh04'], 'depth': depth, 'metric_focus': 'balanced'}})
            assert response.status_code == 200, 'Card endpoint must survive replay withdrawal'
            assert response.headers['cache-control'] == 'private, no-store'
            cards = [c for c in response.json()['cards'] if c['id'] == f'{mid}:e01019:buildup']
            assert len(cards) <= 1, 'A repeated delivery must not duplicate the card'
            return cards[0] if cards else None
        def pair(cutoff):
            return [view(client, depth, cutoff) for client, depth in zip(readers, ('casual', 'analyst'))]
        def score(redhaven_goals):
            for client in readers:
                response = client.get(f'/api/data/matches/{mid}/live', params={'period': 2, 'elapsed_ms': 1053000})
                assert response.status_code == 200
                assert response.json()['score'] == {'southbank': 2, 'redhaven': redhaven_goals}
            scores.append(redhaven_goals)

        def verify_facts(cards, key, revision):
            target = expected[key]
            for depth, card in zip(('casual', 'analyst'), cards):
                assert card and card['text'] == target[depth]
                assert [e['event_id'] for e in card['evidence']['events']] == target['events']
                assert card['evidence']['occurred_at'] == expected['occurred_at']
                assert card['evidence']['expires_at'] == expected['expires_at']
                assert card['evidence']['event_revision'] == revision
                assert card['ask_footie']['event_revision'] == revision
                assert card['replay_available'] is False
                facts = {f['metric']: f for f in card['facts']}
                assert facts['buildup_completed_passes']['value'] == target.get('favorite_passes', target.get('completed_passes'))
                assert facts['buildup_completed_passes']['subject_id'] == ('rh04' if key == 'baseline' else 'redhaven')
                if depth == 'analyst':
                    assert facts['observed_buildup_seconds']['value'] == target['observed_seconds']
                    assert facts['buildup_participants']['value'] == target['participants']
            assert cards[0]['id'] == cards[1]['id']
            assert cards[0]['content_version'] != cards[1]['content_version']
            assert cards[0]['evidence']['evidence_fingerprint'] == cards[1]['evidence']['evidence_fingerprint']
        def context(latest_ms, latest_sequence, revision, retracted, replay_available):
            response = readers[0].get(f'/api/data/highlights/{hid}/context')
            assert response.status_code == 200
            assert response.headers['cache-control'] == 'no-store'
            result = response.json()
            assert result['highlight_id'] == hid and result['match_id'] == mid
            assert result['original_cutoff'] == expected['original_cutoff']
            assert result['latest_cutoff'] == {'period': 2, 'elapsed_ms': latest_ms}
            assert result['original_sequence'] == sequence
            assert result['latest_sequence'] == latest_sequence
            assert result['replay_available'] is replay_available
            assert result['goal']['event_id'] == 'e01019'
            assert result['goal']['revision'] == revision
            assert result['goal']['retracted'] is retracted
            return result
        baseline_context = context(1050489, sequence, 1, False, True)
        baseline = pair(expected['original_cutoff'])
        verify_facts(baseline, 'baseline', 1)
        score(2)
        assert pair({'period': 2, 'elapsed_ms': 1050488}) == [None, None]
        assert readers[0].get(f'/api/data/highlights/{hid}/replay').status_code == 200
        before_update = pair(expected['updated_cutoff'])
        def historical_unchanged():
            assert pair(expected['original_cutoff']) == baseline
            assert [view(client, depth, expected['original_cutoff'], sequence)
                    for client, depth in zip(readers, ('casual', 'analyst'))] == baseline
        correction = passing.model_copy(update={'revision': 2, 'delivery_sequence': sequence + 1,
            'available_period': 2, 'available_ms': 1050800, 'recipient_id': 'rh13'})
        deliver([correction], 'local-card-correction')
        corrected_context = context(1050800, sequence + 1, 1, False, False)
        assert corrected_context['content_version'] != baseline_context['content_version']
        changed = pair(expected['updated_cutoff'])
        verify_facts(changed, 'corrected', 1)
        score(2)
        assert changed[0]['content_version'] != before_update[0]['content_version']
        assert changed[0]['evidence']['evidence_fingerprint'] != baseline[0]['evidence']['evidence_fingerprint']
        historical_unchanged()
        assert readers[0].get(f'/api/data/highlights/{hid}/replay').status_code == 409
        retract = goal.model_copy(update={'revision': 2, 'delivery_sequence': sequence + 2,
            'available_period': 2, 'available_ms': 1051000, 'retracted': True})
        deliver([retract], 'local-card-retraction')
        retracted_context = context(1051000, sequence + 2, 2, True, False)
        score(1)
        assert pair(expected['updated_cutoff']) == [None, None]
        assert pair({'period': 2, 'elapsed_ms': 1050999})[0]
        assert pair({'period': 2, 'elapsed_ms': 1051000}) == [None, None]
        historical_unchanged()
        deliver([retract], 'local-card-retraction')
        assert context(1051000, sequence + 2, 2, True, False) == retracted_context
        score(1)
        assert pair(expected['updated_cutoff']) == [None, None]
        assert readers[0].get('/api/data/revisions').json()['generation'] == 2
        restore = goal.model_copy(update={'revision': 3, 'delivery_sequence': sequence + 3,
            'available_period': 2, 'available_ms': 1052000})
        restore_pass = passing.model_copy(update={'revision': 3, 'delivery_sequence': sequence + 4,
            'available_period': 2, 'available_ms': 1052000})
        deliver([restore, restore_pass], 'local-card-restoration')
        # Reader B receives no hint. Its next authoritative polling read recovers
        # the committed generation and cards; real socket behavior is a UI test.
        assert readers[1].get('/api/data/revisions').json()['generation'] == 3
        context(1052000, sequence + 4, 3, False, False)
        restored = pair(expected['updated_cutoff'])
        verify_facts(restored, 'baseline', 3)
        score(2)
        assert restored[0]['id'] == baseline[0]['id']
        assert restored[0]['content_version'] != before_update[0]['content_version']
        assert restored[0]['evidence']['evidence_fingerprint'] != baseline[0]['evidence']['evidence_fingerprint']
        historical_unchanged()
        assert readers[0].get(f'/api/data/highlights/{hid}/replay').status_code == 409
        restarted = reader()
        assert view(restarted, 'analyst', expected['updated_cutoff']) == restored[1]
        assert pair({'period': 2, 'elapsed_ms': 1080019})[0]
        assert pair(expected['expires_at']) == [None, None]
        late = goal.model_copy(update={'revision': 4, 'delivery_sequence': sequence + 5,
            'available_period': 2, 'available_ms': 1080021})
        deliver([late], 'local-card-late-restoration')
        context(1080021, sequence + 5, 4, False, False)
        assert pair({'period': 2, 'elapsed_ms': 1080021}) == [None, None]
        historical_unchanged()
        assert pair(expected['updated_cutoff']) == restored
        assert generations == [0, 1, 2, 2, 3, 4]
        assert notices == [1, 2, 2, 3, 4] and len(checkpoints) == 5
        assert len(writer_journal.read(writer.dataset).actions) == 5
        return {'status': 'passed', 'match_id': mid, 'event_id': goal.event_id,
            'dataset': writer.dataset, 'generations': generations, 'stable_card_id': baseline[0]['id'],
            'baseline_evidence': baseline[0]['evidence']['evidence_fingerprint'],
            'corrected_evidence': changed[0]['evidence']['evidence_fingerprint'],
            'restored_evidence': restored[0]['evidence']['evidence_fingerprint'],
            'original_cutoff': expected['original_cutoff'], 'updated_cutoff': expected['updated_cutoff'],
            'expires_at': expected['expires_at'], 'checkpointed_deliveries': len(checkpoints),
            'redhaven_goals_at_updated_cutoff': scores,
            'context_available_after_409': True, 'historical_cutoff_preserved': True, 'replay_stays_withdrawn': True,
            'missed_hint_poll_recovery': True, 'restart_recovery': True,
            'azure_calls': 0, 'model_calls': 0}


def main():
    with tempfile.TemporaryDirectory(prefix='footie-card-lifecycle-') as folder:
        print(json.dumps(verify(Path(folder)), indent=2))


if __name__ == '__main__':
    main()
