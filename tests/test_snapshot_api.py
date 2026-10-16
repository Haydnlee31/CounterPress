import asyncio
import json
import shutil
from pathlib import Path

from httpx import ASGITransport, AsyncClient
import pytest
from pydantic import ValidationError

from counterpress.api.main import create_app
from counterpress.api.snapshots import SnapshotService
from counterpress.domain.models import Event

ROOT = Path(__file__).resolve().parents[1]


def request(app, path):
    async def get():
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            return await client.get(path)
    return asyncio.run(get())


def test_snapshot_card_and_evidence_agree_with_oracle():
    response = request(create_app(), "/api/scenarios/increase/snapshot?at_ms=780000")
    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store"
    data = response.json()
    oracle = json.loads((ROOT / "tests/expected_recovery_scenarios.json").read_text())["scenarios"]["recovery_increase"]
    assert data["comparison_status"] == "ready"
    packet = data["evidence"]["packet"]
    records = data["evidence"]["records"]
    insight = data["insight"]
    for name in ("baseline", "current"):
        assert insight["facts"][f"{name}_count"] == packet[name]["value"] == oracle[name]["count"]
        assert [ref["event_id"] for ref in packet[name]["source_events"]] == oracle[name]["event_ids"]
    assert [event["event_id"] for event in records] == oracle["baseline"]["event_ids"] + oracle["current"]["event_ids"]
    assert insight["evidence_id"] == packet["evidence_id"]
    assert insight["claim_type"] == "fact"
    assert "4 attacking-third recoveries" in insight["explanation"]
    assert all(event["available_at"]["elapsed_ms"] <= 780000 for event in records)
    assert request(create_app(), "/api/scenarios/increase/snapshot?at_ms=780000").json() == data


def test_no_future_data_or_increase_card_for_control():
    app = create_app()
    early = request(app, "/api/scenarios/increase/snapshot?at_ms=540000").json()
    assert early["comparison_status"] == "collecting"
    assert early["insight"] is early["evidence"] is None
    assert [ref["event_id"] for ref in early["metrics"][0]["high_recoveries"]] == ["p043", "p053"]
    assert early["state"]["source_delivery_cursor"] == 53
    assert "p064" not in json.dumps(early)
    end = request(app, "/api/scenarios/control/snapshot?at_ms=780000").json()
    assert end["comparison_status"] == "no_increase"
    assert end["insight"] is end["evidence"] is None
    # Requesting a historical snapshot after the end must not return cached later facts.
    request(app, "/api/scenarios/increase/snapshot?at_ms=780000")
    start = request(app, "/api/scenarios/increase/snapshot?at_ms=180000").json()
    assert start["insight"] is start["evidence"] is None
    assert len(start["state"]["applied_events"]) == 1


@pytest.mark.parametrize("change", ["move_location", "restart"])
def test_source_revision_updates_card_and_frozen_evidence_together(tmp_path, change):
    service = SnapshotService(ROOT / "fixtures")
    original = service.snapshot("increase", 780000)
    source = json.loads((ROOT / "fixtures/recovery_increase.json").read_text())
    record = next(event for event in source["events"] if event["event_id"] == "p053")
    record.update(revision=2, source_delivery_sequence=90, available_at={"period": 2, "elapsed_ms": 785000})
    if change == "move_location":
        record["position"]["x"] = 69
    else:
        record["action"]["origin"] = "restart"
    service.ingest("increase", (Event.model_validate_json(json.dumps(record)),))
    changed = service.snapshot("increase", 785000)
    assert changed.insight.facts.current_count == changed.evidence.packet.current.value == 3
    assert "p053" not in [event.event_id for event in changed.evidence.records]
    assert original.insight.insight_id == changed.insight.insight_id
    assert original.evidence.packet.evidence_id == changed.evidence.packet.evidence_id
    assert changed.evidence.packet.evidence_version == 2
    assert original.evidence.packet.current.value == 4
    assert len(original.evidence.records) == 5
    with pytest.raises(ValidationError):
        original.evidence.packet.current.value = 99


def test_seeded_fixture_edits_cannot_rewrite_persisted_history(tmp_path):
    path = tmp_path / "recovery_increase.json"
    shutil.copy(ROOT / "fixtures/recovery_increase.json", path)
    service = SnapshotService(tmp_path)
    original = service.snapshot("increase", 780000)
    path.write_text("invalid source after seeding")
    assert service.snapshot("increase", 780000) == original


@pytest.mark.parametrize("path,status", [
    ("/api/scenarios/missing/snapshot", 404),
    ("/api/scenarios/increase/snapshot?at_ms=179999", 422),
    ("/api/scenarios/increase/snapshot?at_ms=780001", 422),
    ("/api/scenarios/increase/snapshot?at_ms=NaN", 422),
])
def test_invalid_requests(path, status):
    assert request(create_app(), path).status_code == status


def test_catalog_has_no_event_feed_and_missing_fixture_is_reported(tmp_path):
    app = create_app(tmp_path)
    catalog = request(app, "/api/scenarios").json()
    assert [item["scenario_id"] for item in catalog] == ["increase", "control", "pressure-increase", "pressure-control", "progression-increase", "progression-control", "contribution-increase", "contribution-control"]
    assert all("events" not in item for item in catalog)
    response = request(app, "/api/scenarios/increase/snapshot")
    assert response.status_code == 503
    assert str(tmp_path) not in response.text
