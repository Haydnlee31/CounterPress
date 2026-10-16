"""Independent recap expectations use the hand-reviewed detector fixture counts."""
from pathlib import Path

from fastapi.testclient import TestClient
from pydantic import TypeAdapter, ValidationError
import pytest

from counterpress.api.main import create_app
from counterpress.api.snapshots import SnapshotService
from counterpress.audience import ViewingPreferences
from counterpress.domain.models import Event
from counterpress.history import SQLiteHistoryStore
from counterpress.recaps import SegmentRecap

ROOT = Path(__file__).resolve().parents[1]


def corrections(path):
    return TypeAdapter(tuple[Event, ...]).validate_json((ROOT/'fixtures'/path).read_text())


@pytest.mark.parametrize('language', ['en', 'zh-Hans'])
@pytest.mark.parametrize('depth', ['casual', 'analyst'])
def test_independent_pressure_recap_fractions_and_viewpoint(language, depth):
    service = SnapshotService(ROOT/'fixtures')
    prefs = ViewingPreferences(language=language, depth=depth, metric_focus='pressure_exposure')
    recap = service.snapshot('pressure-increase', 780000, preferences=prefs).recap
    assert recap.state == 'ready' and recap.omitted_count == 0
    assert len(recap.statements) == 2
    # Authored from the reviewed fixture: six complete episodes in each window,
    # three then six exposed, three then one escaped while exposed.
    expected = [('3/6', '6/6'), ('3/3', '1/6')]
    for statement, (before, after) in zip(recap.statements, expected, strict=True):
        assert before in statement.narrative.explanation and after in statement.narrative.explanation
        assert '(48:00,53:00]' in statement.narrative.explanation
        assert '(53:00,58:00]' in statement.narrative.explanation
        assert statement.narrative.language == language and statement.narrative.depth == depth
        assert statement.citation.revision == 1
    other = service.snapshot('pressure-increase', 780000, preferences=prefs.model_copy(update={'metric_focus': 'pressured_escape'})).recap
    assert [s.citation for s in other.statements] == [s.citation for s in reversed(recap.statements)]
    assert service.snapshot('pressure-increase', 779999, preferences=prefs).recap.state == 'collecting'


def test_recaps_update_withdraw_restore_rewind_and_restart(tmp_path):
    db = tmp_path/'history.sqlite3'
    service = SnapshotService(ROOT/'fixtures', SQLiteHistoryStore(db))
    original = service.snapshot('pressure-increase', 780000).recap
    service.ingest('pressure-increase', corrections('pressure/replay_corrections.json'))
    restarted = SnapshotService(tmp_path/'absent', SQLiteHistoryStore(db))
    assert restarted.snapshot('pressure-increase', 780000).recap == original
    revised = restarted.snapshot('pressure-increase', 785000).recap
    assert len(revised.statements) == 1 and revised.statements[0].citation.revision == 2
    assert '2/6' in revised.statements[0].narrative.explanation
    withdrawn = restarted.snapshot('pressure-increase', 790000).recap
    assert withdrawn.state == 'no_eligible' and withdrawn.statements == ()
    restored = restarted.snapshot('pressure-increase', 795000).recap
    assert sorted(s.citation.revision for s in restored.statements) == [3, 4]
    assert restarted.snapshot('pressure-increase', 780000).recap == original


def test_player_correction_replaces_citation_even_without_number_change():
    service = SnapshotService(ROOT/'fixtures')
    prefs = ViewingPreferences(player_id='eb04')
    before = service.snapshot('contribution-increase',780000,preferences=prefs).recap
    service.ingest('contribution-increase',corrections('contributions/publication_corrections.json'))
    for cutoff, revision in [(780000,1),(782000,2),(795000,4)]:
        recap = service.snapshot('contribution-increase',cutoff,preferences=prefs).recap
        assert len(recap.statements) == 1 and recap.statements[0].citation.revision == revision
        assert '1/4' in recap.statements[0].narrative.explanation and '3/4' in recap.statements[0].narrative.explanation
    for cutoff in [785000,790000]:
        assert service.snapshot('contribution-increase',cutoff,preferences=prefs).recap.statements == ()
    other = service.snapshot('contribution-increase',795000,preferences=ViewingPreferences(player_id='eb09')).recap
    assert other.state == 'no_eligible'  # Winning duels is not recovery credit.
    assert service.snapshot('contribution-increase',780000,preferences=prefs).recap == before


@pytest.mark.parametrize('scenario', ['pressure-control','progression-control','contribution-control'])
def test_controls_and_budget(scenario):
    service = SnapshotService(ROOT/'fixtures')
    assert service.snapshot(scenario,780000).recap.state == 'no_eligible'
    hidden = service.snapshot('increase',780000,preferences=ViewingPreferences(card_budget=0)).recap
    assert hidden.state == 'budget_hidden' and hidden.statements == ()


@pytest.mark.parametrize('scenario', ['increase','pressure-increase','progression-increase','contribution-increase'])
def test_every_statement_resolves_to_exact_published_evidence(scenario):
    app = create_app()
    with TestClient(app) as client:
        response = client.get(f'/api/scenarios/{scenario}/snapshot?at_ms=780000')
        assert response.headers['cache-control'] == 'no-store'
        snapshot = response.json()
        assert snapshot['recap']['match_id'] == snapshot['state']['match_id']
        assert snapshot['state']['score'] == {'eastbridge':0,'northport':1}
        for item in snapshot['recap']['statements']:
            c = item['citation']
            prefix = '' if c['kind']=='recovery' else f"/{'pressure' if c['kind']=='pressure' else 'contributions'}/{c['insight_id']}"
            result = client.get(f"/api/scenarios/{scenario}{prefix}/evidence/{c['revision']}?at_ms=780000")
            assert result.status_code == 200
            payload = result.json()
            if c['kind']=='recovery':
                assert payload['packet']['evidence_id'] == c['evidence_id']
                assert [payload['packet'][w]['value'] for w in ['baseline','current']] == [1,4]
            else:
                assert payload['evidence_id'] == c['evidence_id'] and payload['revision'] == c['revision']
                assert payload['operation'] != 'withdraw'


def test_recap_contract_rejects_future_duplicate_mismatched_and_hidden_claims():
    original = SnapshotService(ROOT/'fixtures').snapshot('contribution-increase',780000).recap.model_dump(mode='json')
    import copy
    for mutation in ['future','duplicate','revision','language','budget','state','length']:
        raw = copy.deepcopy(original)
        if mutation=='future': raw['statements'][0]['citation']['available_at']['elapsed_ms'] += 1
        if mutation=='duplicate': raw['statements'] *= 2
        if mutation=='revision': raw['statements'][0]['citation']['revision'] += 1
        if mutation=='language': raw['statements'][0]['narrative']['language'] = 'zh-Hans'
        if mutation=='budget': raw['preferences']['card_budget'] = 0
        if mutation=='state': raw['state'] = 'no_eligible'
        if mutation=='length': raw['statements'] *= 5
        import json
        with pytest.raises(ValidationError): SegmentRecap.model_validate_json(json.dumps(raw))


def test_recovery_withdrawal_removes_only_its_statement():
    service = SnapshotService(ROOT/'fixtures')
    service.ingest('increase',corrections('faults/recovery_corrections.json'))
    for cutoff, revision, count in [(780000,1,4),(785000,2,3),(795000,4,2)]:
        recap = service.snapshot('increase',cutoff).recap
        recovery = next(s for s in recap.statements if s.citation.kind=='recovery')
        assert recovery.citation.revision == revision
        assert f'{count} high recoveries' in recovery.narrative.explanation
    withdrawn = service.snapshot('increase',790000).recap
    assert withdrawn.statements and all(s.citation.kind!='recovery' for s in withdrawn.statements)


def test_selection_is_bounded_and_deterministic_when_ledger_has_more_stories():
    from counterpress.recaps import build_recap
    service = SnapshotService(ROOT/'fixtures')
    snapshot = service.snapshot('pressure-increase',780000)
    history = service.history('pressure-increase')
    # Selection-only test: distinct publication IDs exercise overflow independently
    # of detector eligibility; production publications are generated by project().
    publication = history.pressure_changes[0]
    changes = tuple(publication.model_copy(update={'insight_id':f'pressure-test-{i}'}) for i in range(6))
    expanded = history.model_copy(update={'pressure_changes': changes})
    recap = build_recap(expanded,snapshot.state.at,snapshot.windows,ViewingPreferences(),snapshot.audience)
    assert [s.citation.insight_id for s in recap.statements] == [f'pressure-test-{i}' for i in range(4)]
    assert recap.omitted_count == 2
    reversed_history = expanded.model_copy(update={'pressure_changes':tuple(reversed(changes))})
    assert build_recap(reversed_history,snapshot.state.at,snapshot.windows,ViewingPreferences(),snapshot.audience) == recap
