import json
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest
from pydantic import TypeAdapter

from counterpress.api.main import create_app
from counterpress.api.snapshots import SnapshotService
from counterpress.domain.models import Event
from counterpress.history import SQLiteHistoryStore
from test_snapshot_api import request

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "fixtures"


def updates():
    return TypeAdapter(tuple[Event, ...]).validate_json((FIXTURES / "faults/recovery_corrections.json").read_text())


def revise(event, **changes):
    return Event.model_validate_json(json.dumps(event.model_dump(mode="json") | changes))


def service(db, fixtures=FIXTURES):
    return SnapshotService(fixtures, SQLiteHistoryStore(db))


def test_restart_restores_sources_evidence_lifecycle_and_historical_cutoffs(tmp_path):
    db = tmp_path / "history.sqlite3"
    first = service(db)
    original = first.snapshot("increase", 780000)
    history = first.ingest("increase", updates())
    assert len(history.records) == 93
    assert [item.operation for item in history.changes] == ["create", "update", "withdraw", "create"]
    assert [item.revision for item in history.changes] == [1, 2, 3, 4]
    assert len({item.insight_id for item in history.changes}) == 1
    assert [(item.evidence.packet.baseline.value, item.evidence.packet.current.value)
            for item in history.changes] == [(1, 4), (1, 3), (1, 1), (1, 2)]
    for index, change in enumerate(history.changes[1:], 1):
        assert change.invalidates[0].evidence_version == index
        assert change.invalidates[0].evidence_id == original.evidence.packet.evidence_id
    # A new service needs no fixture files or previous process memory.
    restarted = service(db, tmp_path / "missing-fixtures")
    for at, count, revision in [(780000, 4, 1), (784999, 4, 1), (785000, 3, 2),
                                (789999, 3, 2), (790000, None, 3), (794999, None, 3), (795000, 2, 4)]:
        snapshot = restarted.snapshot("increase", at)
        assert snapshot.lifecycle.revision == revision
        assert (snapshot.insight.facts.current_count if snapshot.insight else None) == count
        assert (snapshot.evidence is None) == (count is None)
    assert restarted.evidence("increase", 1, 795000) == original.evidence
    assert restarted.snapshot("increase", 540000).lifecycle is None
    # Retransmitting the complete batch after a restart creates no new versions.
    assert restarted.ingest("increase", updates()) == history


def test_changed_support_updates_evidence_even_when_counts_do_not_change(tmp_path):
    app = service(tmp_path / "history.sqlite3")
    change = revise(updates()[0], position={"x": 73, "y": 38})
    result = app.ingest("increase", (change,)).changes[-1]
    assert result.operation == "update"
    assert result.insight.facts.current_count == 4
    assert next(record for record in result.evidence.records if record.event_id == "p053") == change


def test_previously_excluded_event_is_reconsidered_not_just_old_support(tmp_path):
    app = service(tmp_path / "history.sqlite3")
    before = app.history("increase")
    event = next(event for event in before.records if event.event_id == "p030")
    correction = revise(event, revision=2, source_delivery_sequence=100,
                        available_at={"period": 2, "elapsed_ms": 785000}, position={"x": 75, "y": 30})
    result = app.ingest("increase", (correction,)).changes[-1]
    assert result.insight.facts.baseline_count == 2
    assert result.insight.facts.current_count == 4
    assert "p030" in [event.event_id for event in result.evidence.records]


def test_source_sequence_is_not_a_checkpoint_and_duplicate_is_idempotent(tmp_path):
    app = service(tmp_path / "history.sqlite3")
    first = revise(updates()[0], source_delivery_sequence=100)
    second = revise(updates()[1], source_delivery_sequence=95)
    app.ingest("increase", (first, first))
    result = app.ingest("increase", (second,))
    assert len(result.records) == 91
    assert app.snapshot("increase", 790000).state.source_delivery_cursor == 100
    assert app.snapshot("increase", 790000).insight.facts.current_count == 2


@pytest.mark.parametrize("fault", ["identity_conflict", "backdated", "bad_possession", "wrong_roster"])
def test_bad_batch_rolls_back_all_records_and_publications(tmp_path, fault):
    db = tmp_path / "history.sqlite3"
    app = service(db)
    before = app.history("increase")
    good, bad = updates()[:2]
    if fault == "identity_conflict":
        bad = revise(before.records[0], position={"x": 1, "y": 1})
    elif fault == "backdated":
        bad = revise(bad, available_at={"period": 2, "elapsed_ms": 770000})
    elif fault == "bad_possession":
        bad = revise(bad, actor={"team_id": "northport", "player_id": "np06"},
                     action={"kind": "recovery", "control": "established", "origin": "open_play", "from_team_id": "eastbridge"})
    else:
        bad = revise(bad, actor={"team_id": "eastbridge", "player_id": "missing"})
    with pytest.raises(ValueError):
        app.ingest("increase", (good, bad))
    assert service(db).history("increase") == before


def test_store_rejects_rewrites_even_outside_service(tmp_path):
    app = service(tmp_path / "history.sqlite3")
    before = app.history("increase")
    with pytest.raises(ValueError, match="cannot be rewritten"):
        app.store.transact("increase", lambda previous: previous.model_copy(update={"records": previous.records[:-1]}))
    assert app.history("increase") == before


def test_concurrent_duplicate_writers_commit_once(tmp_path):
    db = tmp_path / "history.sqlite3"
    service(db).history("increase")
    def deliver(_):
        return service(db).ingest("increase", updates())
    with ThreadPoolExecutor(max_workers=4) as pool:
        results = list(pool.map(deliver, range(4)))
    assert all(result == results[0] for result in results)
    assert len(service(db).history("increase").changes) == 4


def test_two_viewers_rewind_without_mutating_producer_and_evidence_has_cutoff(tmp_path):
    db = tmp_path / "history.sqlite3"
    producer = service(db)
    committed = producer.ingest("increase", updates())
    app = create_app(tmp_path / "missing", db)
    late = request(app, "/api/scenarios/increase/snapshot?at_ms=790000&scope_id=viewer-a").json()
    early = request(app, "/api/scenarios/increase/snapshot?at_ms=780000&scope_id=viewer-b").json()
    assert late["scope_id"] == "viewer-a" and late["lifecycle"]["operation"] == "withdraw"
    assert early["scope_id"] == "viewer-b" and early["insight"]["revision"] == 1
    assert request(app, "/api/scenarios/increase/evidence/2?at_ms=780000").status_code == 404
    assert request(app, "/api/scenarios/increase/evidence/1?at_ms=795000").json()["packet"]["current"]["value"] == 4
    assert request(app, "/api/scenarios/increase/snapshot?at_ms=795001").status_code == 422
    assert request(app, "/api/scenarios/increase/snapshot?scope_id=bad%20scope").status_code == 422
    assert request(app, "/api/scenarios").json()[0]["end"]["elapsed_ms"] == 795000
    assert producer.history("increase") == committed


def test_unreadable_database_fails_closed_without_affecting_health(tmp_path):
    db = tmp_path / "broken.sqlite3"
    db.write_text("not a database")
    app = create_app(FIXTURES, db)
    for path in ("/api/scenarios", "/api/scenarios/increase/snapshot", "/api/scenarios/increase/evidence/1?at_ms=780000"):
        response = request(app, path)
        assert response.status_code == 503
        assert str(db) not in response.text
    assert request(app, "/health").json()["status"] == "ok"


def test_correction_outside_window_does_not_resurrect_old_revision(tmp_path):
    db = tmp_path / "history.sqlite3"
    app = service(db)
    before = app.history("increase")
    # Move the complete final possession past 58:00, preserving its play order.
    corrections = tuple(revise(event, revision=2, source_delivery_sequence=90 + index,
                               occurred_at={"period": 2, "elapsed_ms": 781000 + index * 1000},
                               available_at={"period": 2, "elapsed_ms": 785000})
                        for index, event in enumerate(before.records[-4:]))
    app.ingest("increase", corrections)
    restored = service(db, tmp_path / "missing")
    assert restored.snapshot("increase", 780000).insight.facts.current_count == 4
    changed = restored.snapshot("increase", 785000)
    assert changed.insight.facts.current_count == 3
    assert "p086" not in [record.event_id for record in changed.evidence.records]
    assert next(ref.revision for ref in changed.state.applied_events if ref.event_id == "p086") == 2
