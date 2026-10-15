import json
import subprocess
import sys
from fractions import Fraction
from pathlib import Path

import pytest
from pydantic import TypeAdapter

from counterpress.clock import VirtualClock
from counterpress.domain.metrics import compare_recoveries, is_high_recovery
from counterpress.domain.models import Event, MatchTime, ObservationWindow
from counterpress.domain.replay import EventJournal
from counterpress.fixture import PossessionFixture, load_fixture
from counterpress.replay import ReplaySession

ROOT = Path(__file__).resolve().parents[1]
EXPECTED = json.loads((ROOT / "tests/expected_recovery_scenarios.json").read_text())
FAULTS = json.loads((ROOT / "tests/expected_faults.json").read_text())


def time(ms):
    return MatchTime(period=2, elapsed_ms=ms)


def revised(event, **changes):
    data = event.model_dump(mode="json")
    data.update(changes)
    return Event.model_validate_json(json.dumps(data))


def fault(name):
    return TypeAdapter(tuple[Event, ...]).validate_json((ROOT / f"fixtures/faults/{name}.json").read_text())


def tiny():
    return ReplaySession(load_fixture(ROOT / "fixtures/tiny_possession.json"), end=time(240000))


def finish(session):
    session.clock.play()
    session.clock.advance(Fraction(session.clock.end.elapsed_ms - session.clock.start.elapsed_ms, 1000) / session.clock.speed)
    return session.snapshot()


@pytest.mark.parametrize("scenario", ["recovery_increase", "recovery_control"])
@pytest.mark.parametrize("speed", [0.5, 1, 3, 60])
def test_replay_oracles_speed_and_repeatability(scenario, speed):
    session = ReplaySession(load_fixture(ROOT / f"fixtures/{scenario}.json"), speed=speed)
    snapshot = finish(session)
    expected = EXPECTED["scenarios"][scenario]
    result = session.comparison("eastbridge", ObservationWindow(start=time(180000), end=time(480000)),
                                ObservationWindow(start=time(480000), end=time(780000)))
    for label in ("baseline", "current"):
        observation = getattr(result, label)
        assert observation.value == expected[label]["count"]
        assert [ref.event_id for ref in observation.source_events] == expected[label]["event_ids"]
    assert result.increased is expected["increase_expected"]
    assert snapshot.state.score == EXPECTED["unchanged_score"]
    assert snapshot.state.controlled_possession_team_id == EXPECTED["final_controlled_possession_team_id"]
    assert len(snapshot.events) == expected["event_count"]
    assert snapshot.state.source_delivery_cursor == 89
    session.clock.reset()
    assert not session.clock.playing
    assert session.clock.now == session.fixture.initial_state.at
    assert finish(session) == snapshot
    other = ReplaySession(session.fixture, speed=7)
    assert finish(other) == snapshot


def test_tiny_metrics_match_hand_calculation_and_duel_is_not_recovery():
    session = tiny()
    result = finish(session)
    expected = json.loads((ROOT / "tests/expected_tiny_metrics.json").read_text())
    for metrics in result.metrics:
        oracle = expected[metrics.team_id]
        assert metrics.pass_attempts == oracle["pass_attempts"]
        assert metrics.pass_completions == oracle["pass_completions"]
        assert metrics.attempted_pass_distance_m == pytest.approx(oracle["attempted_pass_distance_m"])
        assert metrics.completed_pass_distance_m == pytest.approx(oracle["completed_pass_distance_m"])
        assert [ref.event_id for ref in metrics.high_recoveries] == oracle["high_recovery_ids"]
    assert session.snapshot(time(200200)).state.controlled_possession_team_id == "northport"
    assert session.snapshot(time(210199)).state.controlled_possession_team_id == "northport"
    assert session.snapshot(time(210200)).state.controlled_possession_team_id == "eastbridge"


def test_pause_reset_speed_changes_fractional_ticks_and_end_clamp():
    clock = VirtualClock(time(180000), time(240000))
    assert clock.advance(100) == time(180000)  # Starts paused.
    clock.play()
    for _ in range(10):
        clock.advance(0.0001)
    assert clock.now == time(180001)  # No truncation drift between ticks.
    clock.pause()
    assert clock.advance(10) == time(180001)
    clock.set_speed(2)
    clock.play()
    assert clock.advance(1) == time(182001)
    clock.set_speed(0.5)
    assert clock.advance(2) == time(183001)
    assert clock.advance(1000) == time(240000)
    assert not clock.playing
    clock.reset()
    assert clock.now == time(180000)
    assert clock.speed == Fraction(1, 2)
    assert not clock.playing


@pytest.mark.parametrize("speed", [0, -1, float("nan"), float("inf"), True])
def test_invalid_speed_is_rejected(speed):
    clock = VirtualClock(time(0), time(1000))
    with pytest.raises(ValueError):
        clock.set_speed(speed)
    assert clock.speed == 1


@pytest.mark.parametrize("elapsed", [-1, float("nan"), float("inf"), True])
def test_invalid_elapsed_time_is_rejected_even_when_paused(elapsed):
    with pytest.raises(ValueError):
        VirtualClock(time(0), time(1000)).advance(elapsed)


def test_no_future_events_and_no_premature_comparison():
    session = ReplaySession(load_fixture(ROOT / "fixtures/recovery_increase.json"))
    session.clock.play()
    session.clock.advance(360)  # 48:00 -> 54:00
    snapshot = session.snapshot()
    assert snapshot.state.at == time(540000)
    assert [ref.event_id for ref in snapshot.metrics[0].high_recoveries] == ["p043", "p053"]
    assert snapshot.state.source_delivery_cursor == 53
    assert all(event.available_at.key() <= time(540000).key() for event in snapshot.events)
    with pytest.raises(ValueError, match="not ready"):
        session.comparison("eastbridge", ObservationWindow(start=time(180000), end=time(480000)),
                           ObservationWindow(start=time(480000), end=time(780000)))
    assert session.snapshot(time(480000)).metrics[0].high_recoveries[0].event_id == "p043"
    assert session.clock.now == time(540000)  # Historical reads do not move producer time.


def test_duplicate_delivery_does_not_change_state_or_metrics():
    session = tiny()
    before = finish(session)
    session.deliver(fault("duplicate_delivery"))
    assert session.snapshot() == before
    assert len(session.journal.records) == 10
    assert len(session.snapshot().metrics[0].high_recoveries) == FAULTS["duplicate_delivery"]["future_canonical_high_recovery_count"]


def test_correction_only_applies_at_availability_and_rewind_restores_old_revision():
    session = tiny()
    session.deliver(fault("event_correction"))
    before = session.snapshot(time(239999))
    after = session.snapshot(time(240000))
    assert [len(snapshot.metrics[0].high_recoveries) for snapshot in (before, after)] == FAULTS["event_correction"]["future_counts_before_after"]
    assert before.state.source_delivery_cursor == 10
    assert after.state.source_delivery_cursor == 11
    assert next(event.revision for event in after.events if event.event_id == "e04") == 2
    session.deliver((fault("event_correction")[0],))  # Old retransmission after correction.
    assert session.snapshot(time(240000)) == after
    assert session.snapshot(time(239999)) == before


def test_revision_is_selected_before_window_filtering():
    first = fault("event_correction")[0]
    correction = revised(first, revision=2, source_delivery_sequence=11,
                         occurred_at={"period": 2, "elapsed_ms": 241000},
                         available_at={"period": 2, "elapsed_ms": 250000})
    journal = EventJournal(first.match_id, (correction, first))  # Arrival order irrelevant.
    baseline = ObservationWindow(start=time(180000), end=time(210000))
    current = ObservationWindow(start=time(210000), end=time(240000))
    before = compare_recoveries(journal.events_at(time(249999)), "eastbridge", baseline, current, time(249999))
    after = compare_recoveries(journal.events_at(time(250000)), "eastbridge", baseline, current, time(250000))
    assert before.baseline.value == 1
    assert after.baseline.value == after.current.value == 0
    assert journal.events_at(time(250000)) == (correction,)


def test_late_delivery_rebuilds_in_occurrence_order():
    original = load_fixture(ROOT / "fixtures/tiny_possession.json")
    data = original.model_dump(mode="json")
    data["events"] = data["events"][1:]
    session = ReplaySession(PossessionFixture.model_validate_json(json.dumps(data)), end=time(245000))
    delayed = revised(original.events[0], source_delivery_sequence=11,
                      available_at={"period": 2, "elapsed_ms": 241000})
    before = session.snapshot(time(240000))
    session.deliver((delayed,))
    assert session.snapshot(time(240000)) == before
    after = session.snapshot(time(241000))
    assert after.events[0].event_id == "e01"
    assert after.metrics[1].pass_attempts == 2
    assert before.metrics[1].pass_attempts == 1


@pytest.mark.parametrize("conflict", ["payload", "sequence", "order", "unstable_order", "revision_sequence", "availability", "match"])
def test_journal_rejects_conflicts_atomically(conflict):
    source = fault("event_correction")[0]
    journal = EventJournal(source.match_id, (source,))
    if conflict == "payload":
        incoming = revised(source, position={"x": 80, "y": 34})
    elif conflict == "sequence":
        incoming = revised(source, event_id="another", occurrence_order=5)
    elif conflict == "order":
        incoming = revised(source, event_id="another", source_delivery_sequence=12)
    elif conflict == "unstable_order":
        incoming = revised(source, revision=2, source_delivery_sequence=12, occurrence_order=5)
    elif conflict == "revision_sequence":
        incoming = revised(source, revision=2, source_delivery_sequence=3)
    elif conflict == "availability":
        incoming = revised(source, revision=2, source_delivery_sequence=12,
                           available_at={"period": 2, "elapsed_ms": 210100})
    else:
        incoming = revised(source, match_id="another")
    with pytest.raises(ValueError):
        journal.append((incoming,))
    assert journal.records == (source,)


def test_equal_time_uses_occurrence_order_and_newest_available_revision_wins():
    source = fault("event_correction")[0]
    next_event = revised(source, event_id="another", source_delivery_sequence=12, occurrence_order=5)
    updated = revised(source, revision=2, source_delivery_sequence=13)
    journal = EventJournal(source.match_id, (next_event, updated, source))
    assert journal.events_at(time(240000)) == (updated, next_event)


def test_restarts_and_below_threshold_are_excluded_for_either_team():
    source = fault("event_correction")[0]
    boundary = revised(source, position={"x": 70, "y": 34})
    assert is_high_recovery(boundary, "eastbridge")
    assert not is_high_recovery(revised(source, position={"x": 69.999, "y": 34}), "eastbridge")
    action = source.action.model_dump(mode="json")
    action["origin"] = "restart"
    assert not is_high_recovery(revised(source, action=action), "eastbridge")
    action.update(origin="open_play", from_team_id="eastbridge")
    opposite = revised(boundary, actor={"team_id": "northport", "player_id": "np06"}, action=action)
    assert is_high_recovery(opposite, "northport")
    assert not is_high_recovery(opposite, "eastbridge")


def test_bad_actor_and_inconsistent_possession_fail_without_fabricating_metrics():
    session = tiny()
    original = session.journal.records[0]
    unknown = revised(original, revision=2, source_delivery_sequence=11,
                      actor={"team_id": "northport", "player_id": "np99"})
    with pytest.raises(ValueError, match="unregistered"):
        session.deliver((unknown,))
    duplicate_recovery = revised(fault("event_correction")[0], event_id="extra-recovery",
                                source_delivery_sequence=11, occurrence_order=11)
    session.deliver((duplicate_recovery,))
    with pytest.raises(ValueError, match="contradicts controlled possession"):
        session.snapshot(time(240000))


def test_period_boundaries_and_snapshot_bounds():
    with pytest.raises(ValueError, match="one period"):
        VirtualClock(MatchTime(period=1, elapsed_ms=0), time(100))
    session = tiny()
    for cutoff in (time(179999), time(240001)):
        with pytest.raises(ValueError, match="outside"):
            session.snapshot(cutoff)


def test_cli_report_and_invalid_speed():
    command = [sys.executable, "-m", "counterpress.replay", "fixtures/recovery_increase.json"]
    result = subprocess.run(command + ["--speed", "3"], cwd=ROOT, text=True, capture_output=True, check=True)
    assert "Baseline (48:00, 53:00]: 1 | p043@r1" in result.stdout
    assert "Current (53:00, 58:00]: 4 | p053@r1, p064@r1, p075@r1, p086@r1" in result.stdout
    invalid = subprocess.run(command + ["--speed", "0"], cwd=ROOT, text=True, capture_output=True)
    assert invalid.returncode == 2
    assert "value must be positive" in invalid.stderr
