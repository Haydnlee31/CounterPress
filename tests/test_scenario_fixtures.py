"""Offline fixture audits; no production detector or replay engine yet."""

import json
from pathlib import Path

import pytest
from pydantic import TypeAdapter, ValidationError

from counterpress.domain.models import CarryDetails, DuelDetails, Event, PassDetails, RecoveryDetails
from counterpress.fixture import PossessionFixture, load_fixture

ROOT = Path(__file__).resolve().parents[1]
EXPECTED = json.loads((ROOT / "tests/expected_recovery_scenarios.json").read_text())
FAULTS = json.loads((ROOT / "tests/expected_faults.json").read_text())


@pytest.mark.parametrize("scenario", ["recovery_increase", "recovery_control"])
def test_hand_checked_counts_and_supporting_events(scenario):
    fixture = load_fixture(ROOT / f"fixtures/{scenario}.json")
    expected = EXPECTED["scenarios"][scenario]
    assert fixture.match_id == expected["match_id"]
    assert len(fixture.events) == expected["event_count"]
    assert fixture.initial_state.at.period == EXPECTED["period"]
    assert fixture.initial_state.at.elapsed_ms == EXPECTED["baseline_window_ms"][0]
    assert fixture.initial_state.score == EXPECTED["unchanged_score"]
    assert fixture.events[0].occurred_at == fixture.initial_state.at
    assert fixture.events[-1].occurred_at.elapsed_ms == EXPECTED["cutoff_ms"]
    assert all(event.occurred_at.period == EXPECTED["period"] for event in fixture.events)
    assert all(event.available_at.elapsed_ms <= EXPECTED["cutoff_ms"] for event in fixture.events)

    recoveries = [event for event in fixture.events if isinstance(event.action, RecoveryDetails)]
    assert [[event.event_id, event.action.from_team_id, event.actor.team_id]
            for event in recoveries] == EXPECTED["possession_transitions"]
    assert recoveries[-1].actor.team_id == EXPECTED["final_controlled_possession_team_id"]
    eligible = [event for event in recoveries
                if event.actor.team_id == EXPECTED["subject_team_id"]
                and event.action.origin == "open_play" and event.position.x >= 70]
    for window in ("baseline", "current"):
        start, end = EXPECTED[f"{window}_window_ms"]
        ids = [event.event_id for event in eligible if start < event.occurred_at.elapsed_ms <= end]
        assert ids == expected[window]["event_ids"]
        assert len(ids) == expected[window]["count"]
    assert (expected["current"]["count"] > expected["baseline"]["count"]) is expected["increase_expected"]
    assert {event.event_id: [event.position.x, event.position.y] for event in eligible} == expected["qualifying_locations"]
    assert [event.event_id for event in recoveries
            if event.actor.team_id == "eastbridge" and event.position.x < 70] == expected["nonqualifying_eastbridge_recoveries"]

    by_id = {event.event_id: event for event in fixture.events}
    assert by_id["p043"].occurred_at.elapsed_ms == 480000
    assert by_id["p043"].position.x == 70
    assert isinstance(by_id["p041"].action, DuelDetails)
    assert isinstance(by_id["p042"].action, DuelDetails)
    if scenario == "recovery_control":
        assert by_id["p075"].position.x == 69.9


@pytest.mark.parametrize("scenario", ["recovery_increase", "recovery_control"])
def test_ball_location_and_player_possession_are_continuous(scenario):
    """Check all authored plays in a fixed Eastbridge-positive-x frame."""
    fixture = load_fixture(ROOT / f"fixtures/{scenario}.json")

    def fixed_frame(position, team_id):
        if team_id == "eastbridge":
            return position.x, position.y
        return 105 - position.x, 68 - position.y

    previous_end = None
    holder = fixture.events[0].actor
    for event in fixture.events:
        start = fixed_frame(event.position, event.actor.team_id)
        if previous_end is not None:
            assert start == pytest.approx(previous_end), event.event_id
        action = event.action
        if isinstance(action, RecoveryDetails):
            assert action.from_team_id == holder.team_id
            holder = event.actor
        elif isinstance(action, DuelDetails):
            assert holder in (event.actor, action.opponent)
        else:
            assert event.actor == holder, event.event_id
        if isinstance(action, PassDetails) and action.outcome == "completed":
            holder = action.recipient
        previous_end = fixed_frame(action.end_position, event.actor.team_id) if isinstance(
            action, (PassDetails, CarryDetails)
        ) else start


@pytest.mark.parametrize("name", ["invalid_player", "invalid_coordinate"])
def test_invalid_fault_fixtures_are_rejected(name):
    assert FAULTS[name]["fixture_valid"] is False
    with pytest.raises(ValidationError, match=FAULTS[name]["reason"]):
        load_fixture(ROOT / f"fixtures/faults/{name}.json")


@pytest.mark.parametrize("name", ["duplicate_delivery", "event_correction"])
def test_valid_fault_records_are_explicitly_outside_ordered_fixture_contract(name):
    raw = (ROOT / f"fixtures/faults/{name}.json").read_text()
    events = TypeAdapter(tuple[Event, ...]).validate_json(raw)
    expected = FAULTS[name]
    assert expected["individual_records_valid"] is True
    assert expected["ordered_fixture_valid"] is False
    if name == "duplicate_delivery":
        assert len(events) == expected["delivered_records"]
        assert events[0] == events[1]
        assert len({(event.match_id, event.event_id, event.revision) for event in events}) == expected["unique_record_identities"]
    else:
        assert {event.event_id for event in events} == {expected["event_id"]}
        assert {event.occurrence_order for event in events} == {expected["occurrence_order"]}
        assert events[0].occurred_at == events[1].occurred_at
        assert [event.revision for event in events] == expected["revisions"]
        assert [event.source_delivery_sequence for event in events] == expected["source_delivery_sequences"]
        assert [event.position.x for event in events] == expected["x_coordinates"]
        assert [event.available_at.elapsed_ms for event in events] == expected["available_elapsed_ms"]
    fixture = json.loads((ROOT / "fixtures/tiny_possession.json").read_text())
    fixture["events"] = json.loads(raw)
    with pytest.raises(ValidationError, match=expected["reason"]):
        PossessionFixture.model_validate_json(json.dumps(fixture))
