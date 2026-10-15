import asyncio
import json
from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient
from pydantic import ValidationError

from counterpress.api.main import app
from counterpress.domain.models import EvidencePacket, MatchTime, RecoveryDetails
from counterpress.fixture import PossessionFixture, load_fixture

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "fixtures/tiny_possession.json"
EXPECTED = ROOT / "tests/expected_tiny_possession.json"


def parse_fixture(data):
    return PossessionFixture.model_validate_json(json.dumps(data))


def parse_evidence(data):
    return EvidencePacket.model_validate_json(json.dumps(data))


def test_health_and_api_documentation():
    async def check():
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.get("/health")
            assert response.status_code == 200
            assert response.json() == {"status": "ok", "service": "counterpress"}
            assert "/health" in (await client.get("/openapi.json")).json()["paths"]
            assert (await client.get("/docs")).status_code == 200

    asyncio.run(check())


def test_fixture_against_independent_hand_written_expectations():
    fixture = load_fixture(FIXTURE)
    expected = json.loads(EXPECTED.read_text())
    assert len(fixture.events) == expected["event_count"]
    assert [event.event_id for event in fixture.events] == expected["event_ids"]
    control = fixture.initial_state.controlled_possession_team_id
    trace, recoveries = [], []
    for event in fixture.events:
        if isinstance(event.action, RecoveryDetails):
            assert event.action.from_team_id == control
            control = event.actor.team_id
            recoveries.append(event.event_id)
        trace.append(control)
    assert trace == expected["control_after_each_event"]
    assert recoveries == expected["recovery_event_ids"]

    packet = parse_evidence(expected["evidence"])
    assert packet.match_id == fixture.match_id
    # Independent, tiny-fixture check, not the future runtime metric/replay engine.
    for observation in (packet.baseline, packet.current):
        qualifying = [event for event in fixture.events
                      if isinstance(event.action, RecoveryDetails)
                      and event.action.origin == "open_play"
                      and event.actor.team_id == packet.subject_team_id
                      and event.position.x >= 70
                      and observation.window.contains(event.occurred_at)
                      and event.available_at.key() <= packet.cutoff.key()]
        assert len(qualifying) == observation.value
        assert [(event.event_id, event.revision) for event in qualifying] == [
            (ref.event_id, ref.revision) for ref in observation.source_events
        ]


def test_window_boundaries_and_period_order():
    packet = parse_evidence(json.loads(EXPECTED.read_text())["evidence"])
    first, second = packet.baseline.window, packet.current.window
    assert not first.contains(first.start)
    assert first.contains(first.end)
    assert not second.contains(first.end)
    assert second.contains(second.end)
    assert not second.contains(MatchTime(period=2, elapsed_ms=240001))
    assert MatchTime(period=1, elapsed_ms=3000000).key() < first.start.key()


@pytest.mark.parametrize("path,value,message", [
    (("events", 0, "actor", "player_id"), "unknown", "registered player"),
    (("events", 0, "actor", "team_id"), "eastbridge", "recipient must belong"),
    (("events", 0, "position", "x"), 105.1, "less than or equal"),
    (("events", 0, "position", "y"), -0.1, "greater than or equal"),
    (("events", 0, "position", "x"), float("nan"), "finite number"),
    (("events", 0, "action", "end_position", "y"), 69, "less than or equal"),
    (("events", 0, "revision"), 0, "greater than 0"),
    (("events", 0, "revision"), "1", "valid integer"),
    (("events", 0, "source_delivery_sequence"), 0, "greater than 0"),
    (("events", 1, "source_delivery_sequence"), 1, "sequences must increase"),
    (("events", 1, "event_id"), "e01", "must be unique"),
    (("events", 1, "occurrence_order"), 1, "must be unique"),
    (("events", 0, "occurred_at", "period"), 3, "Input should be 1 or 2"),
    (("events", 0, "available_at", "elapsed_ms"), 184999, "availability cannot precede"),
    (("events", 0, "occurred_at", "elapsed_ms"), 179999, "ordered after initial"),
    (("events", 0, "match_id"), "different-match", "fixture match"),
    (("events", 0, "event_id"), " ", "String should match pattern"),
    (("events", 0, "surprise"), True, "Extra inputs"),
    (("events", 0, "action", "recipient"), None, "requires a recipient"),
    (("events", 3, "action", "from_team_id"), "eastbridge", "change controlled possession"),
    (("events", 3, "action", "from_team_id"), "other-team", "previous controlling team"),
    (("events", 3, "action", "control"), "uncertain", "established"),
    (("events", 3, "action", "kind"), "goal", "does not match any"),
    (("initial_state", "controlled_possession_team_id"), "eastbridge", "requires controlled possession"),
    (("pitch", "length_m"), 100, "105"),
])
def test_invalid_fixture_is_rejected(path, value, message):
    data = json.loads(FIXTURE.read_text())
    target = data
    for key in path[:-1]:
        target = target[key]
    target[path[-1]] = value
    with pytest.raises(ValidationError, match=message):
        parse_fixture(data)


@pytest.mark.parametrize("failure", ["reversed", "overlap", "cutoff", "count", "duplicate", "both_windows"])
def test_invalid_evidence_is_rejected(failure):
    data = json.loads(EXPECTED.read_text())["evidence"]
    if failure == "reversed":
        data["baseline"]["window"]["end"] = data["baseline"]["window"]["start"]
    elif failure == "overlap":
        data["current"]["window"]["start"]["elapsed_ms"] = 200000
    elif failure == "cutoff":
        data["cutoff"]["elapsed_ms"] = 239999
    elif failure == "count":
        data["baseline"]["value"] = 2
    elif failure == "duplicate":
        data["baseline"]["source_events"] *= 2
        data["baseline"]["value"] = 2
    else:
        data["current"]["source_events"] = data["baseline"]["source_events"]
        data["current"]["value"] = 1
    with pytest.raises(ValidationError):
        parse_evidence(data)


def test_occurrence_tie_uses_stable_order():
    data = json.loads(FIXTURE.read_text())
    data["events"][1]["occurred_at"] = data["events"][0]["occurred_at"].copy()
    parse_fixture(data)
    data["events"][1]["occurrence_order"] = 0
    with pytest.raises(ValidationError, match="ordered after initial"):
        parse_fixture(data)
