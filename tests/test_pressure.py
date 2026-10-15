"""Observable episode controls, boundary accounting, source revisions and eligibility."""

import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from counterpress.domain.models import Event, MatchTime, ObservationWindow
from counterpress.domain.pressure import PressureEvidence, PressurePolicy, Publication, analyze_pressure
from counterpress.fixture import PossessionFixture, load_fixture
from counterpress.generator.engine import generate
from counterpress.generator.suite import profile
from counterpress.replay import ReplaySession

ROOT = Path(__file__).resolve().parents[1]
EXPECTED = json.loads((ROOT / "tests/expected_pressure.json").read_text())


def at(seconds):
    return MatchTime(period=2, elapsed_ms=180000 + seconds * 1000)


def window(start, end):
    return ObservationWindow(start=at(start), end=at(end))


BASELINE, CURRENT = window(0, 60), window(60, 120)


def fixture(name="increase"):
    return load_fixture(ROOT / f"fixtures/pressure/{name}.json")


def analyze(feed=None, *, cutoff=120, baseline=BASELINE, current=CURRENT, **kwargs):
    session = feed if isinstance(feed, ReplaySession) else ReplaySession(feed or fixture(), end=at(max(cutoff, 120)))
    return analyze_pressure(session, "eastbridge", baseline, current, at(cutoff), **kwargs)


def changed_event(event, **changes):
    return Event.model_validate(event.model_dump() | changes)


@pytest.mark.parametrize("name", ["increase", "control"])
def test_manual_controls_and_independent_geometry(name):
    feed, expected = fixture(name), EXPECTED[name]
    # Independently audit control geometry and actor continuity, without detector helpers.
    ball, holder = (20.0, 34.0), "northport"
    for event in feed.events:
        own = event.actor.team_id == "eastbridge"
        point = (event.position.x, event.position.y) if own else (105-event.position.x, 68-event.position.y)
        assert point == ball
        if event.action.kind == "recovery":
            assert event.action.from_team_id == holder
            holder = event.actor.team_id
        else:
            assert event.actor.team_id == holder
        if event.action.kind in ("carry", "pass"):
            end = event.action.end_position
            ball = (end.x, end.y) if own else (105-end.x, 68-end.y)
    result = analyze(feed)
    for prefix, summary in (("baseline", result.baseline), ("current", result.current)):
        assert list(summary.included) == expected[f"{prefix}_included"]
        episodes = [episode for episode in result.episodes if episode.episode_id in summary.included]
        assert [episode.episode_id for episode in episodes if episode.pressure_events] == expected[f"{prefix}_pressured"]
        assert [episode.episode_id for episode in episodes if episode.pressure_events and episode.outcome == "escape"] == expected[f"{prefix}_pressured_escapes"]
        assert not summary.boundary_excluded and not summary.pending and not summary.left_censored
    for decision, key in zip(result.decisions, ("exposure_fraction", "escape_fraction")):
        assert [decision.baseline_numerator, decision.baseline_denominator, decision.current_numerator, decision.current_denominator] == expected[key]
    assert [decision.status for decision in result.decisions] == expected["statuses"]
    assert PressureEvidence.model_validate_json(result.model_dump_json()) == result


def small_feed(rows, *, initial="eastbridge"):
    """Explicit test records: (id, second, kind, x, end_x/outcome/origin)."""
    events = []
    for index, (eid, second, kind, x, value) in enumerate(rows, 1):
        team = "northport" if kind == "opponent_recovery" else "eastbridge"
        if kind in ("recovery", "opponent_recovery"):
            action = dict(kind="recovery", from_team_id="eastbridge" if team == "northport" else "northport", control="established", origin=value)
        elif kind == "duel":
            action = dict(kind="duel", opponent=dict(team_id="northport", player_id="np04"), outcome=value)
        else:
            action = dict(kind=kind, end_position=dict(x=float(value), y=34.0))
            if kind == "pass":
                action |= dict(outcome="completed", recipient=dict(team_id="eastbridge", player_id="eb08"))
        events.append(Event.model_validate(dict(match_id="boundary-test", event_id=eid, revision=1,
            source_delivery_sequence=index, occurrence_order=index, occurred_at=at(second).model_dump(), available_at=at(second).model_dump(),
            actor=dict(team_id=team,player_id="np04" if team == "northport" else "eb04"),
            position=dict(x=float(x),y=34.0),action=action)))
    base = fixture().model_dump()
    base.update(match_id="boundary-test", events=tuple(event.model_dump() for event in events))
    base["initial_state"]["controlled_possession_team_id"] = initial
    return PossessionFixture.model_validate(base)


def test_boundary_exclusions_pending_and_initial_left_censoring():
    feed = small_feed([
        ("initial", 0, "carry", 20, 20), ("first-end", 5, "carry", 20, 50),
        ("entry", 50, "carry", 50, 30), ("challenge", 55, "duel", 30, "won"),
        ("cross-end", 65, "carry", 30, 50), ("last-entry", 110, "carry", 50, 30),
        ("unresolved", 119, "duel", 30, "lost"),
    ])
    result = analyze(feed)
    assert result.baseline.left_censored == ("initial",)
    assert result.baseline.pending == ("entry",)
    assert result.current.boundary_excluded == ("entry",)
    assert result.current.pending == ("last-entry",)
    assert result.baseline.completed == result.current.completed == 0
    assert all(decision.status == "insufficient_sample" and decision.change is None for decision in result.decisions)
    assert result.episodes[-1].outcome == "pending" and result.episodes[-1].end is None


@pytest.mark.parametrize("start,end,expected", [(0, 5, "boundary"), (1, 60, "baseline"), (60, 65, "boundary"), (61, 120, "current")])
def test_start_exclusive_end_inclusive(start, end, expected):
    feed = small_feed([("start", start, "recovery", 20, "open_play"), ("end", end, "carry", 20, 50)], initial="northport")
    result = analyze(feed)
    if expected == "boundary":
        assert sum(len(item.boundary_excluded) for item in (result.baseline, result.current)) == 1
        assert result.baseline.completed == result.current.completed == 0
    else:
        assert getattr(result, expected).included == ("start",)


def test_x35_is_inside_won_duel_is_not_escape_and_repeated_duels_count_once():
    feed = small_feed([("start", 1, "recovery", 35, "restart"), ("d1", 2, "duel", 35, "won"),
                       ("d2", 3, "duel", 35, "won"), ("inside", 4, "carry", 35, 35),
                       ("escape", 5, "pass", 35, 35.001)], initial="northport")
    result = analyze(feed)
    assert result.baseline.completed == result.baseline.exposed == result.baseline.escaped_under_pressure == 1
    assert result.episodes[0].end == at(5)
    assert [ref.event_id for ref in result.episodes[0].pressure_events] == ["d1", "d2"]


def test_restart_resolution_is_not_an_escape():
    feed = small_feed([("start", 1, "recovery", 20, "open_play"), ("duel", 2, "duel", 20, "lost"),
                       ("restart", 12, "opponent_recovery", 85, "restart")], initial="northport")
    result = analyze(feed)
    assert result.episodes[0].outcome == "restart"
    assert result.baseline.exposed == 1 and result.baseline.escaped_under_pressure == 0


def test_challenging_for_possession_does_not_start_a_build_up_episode():
    feed = small_feed([("challenge", 1, "duel", 20, "won"),
                       ("start", 2, "recovery", 20, "open_play"),
                       ("escape", 3, "carry", 20, 50)], initial="northport")
    result = analyze(feed)
    assert result.baseline.included == ("start",)
    assert result.baseline.exposed == 0 and not result.baseline.left_censored


def test_opponent_perspective_duel_rotates_into_subject_defensive_third():
    feed = fixture()
    rows = []
    for event in feed.events:
        if event.event_id == "b1-duel":
            event = changed_event(event, actor={"team_id":"northport", "player_id":"np04"},
                position={"x":85.0,"y":34.0}, action={"kind":"duel", "opponent":{"team_id":"eastbridge","player_id":"eb04"}, "outcome":"lost"})
        rows.append(event)
    result = analyze(PossessionFixture.model_validate(feed.model_dump() | {"events":tuple(row.model_dump() for row in rows)}))
    assert result.baseline.exposed == 3 and result.episodes[0].pressure_events[0].event_id == "b1-duel"


@pytest.mark.parametrize("minimum,expected", [(3,["eligible","eligible"]), (4,["eligible","insufficient_sample"]), (7,["insufficient_sample","insufficient_sample"])])
def test_each_window_and_each_metric_has_its_own_minimum(minimum, expected):
    result = analyze(policy=PressurePolicy(minimum_episodes=minimum))
    assert [decision.status for decision in result.decisions] == expected


def test_minimum_is_also_required_in_current_window():
    result = analyze(current=window(60, 79))
    assert result.current.completed == 2 and result.baseline.completed == 6
    assert all(decision.status == "insufficient_sample" for decision in result.decisions)


def test_threshold_and_zero_denominators_are_not_success():
    result = analyze(policy=PressurePolicy(minimum_rate_change=0.6))
    assert [decision.status for decision in result.decisions] == ["below_threshold", "eligible"]
    feed = small_feed([("start",1,"recovery",20,"open_play"),("end",2,"carry",20,50)], initial="northport")
    result = analyze(feed, policy=PressurePolicy(minimum_episodes=1))
    assert result.baseline.exposure_rate == 0 and result.baseline.pressured_escape_rate is None
    assert result.decisions[1].change is None


def receipt(**changes):
    return Publication.model_validate(dict(match_id="build-up-increase",team_id="eastbridge",metric="pressure_exposure",
        baseline=window(0,30).model_dump(),current=window(30,60).model_dump(),published_at=at(100).model_dump()) | changes)


def test_cooldown_is_metric_scoped_and_exact_expiry_is_eligible():
    prior = receipt()
    result = analyze(publications=(prior,))
    assert [decision.status for decision in result.decisions] == ["cooldown", "eligible"]
    assert analyze(cutoff=160, publications=(prior,)).decisions[0].status == "eligible"


@pytest.mark.parametrize("changes", [{"match_id":"another"},{"team_id":"northport"},{"published_at":at(121).model_dump()},
    {"baseline":BASELINE.model_dump(),"current":CURRENT.model_dump(),"published_at":at(120).model_dump()}])
def test_unrelated_future_and_same_window_receipts_do_not_suppress(changes):
    assert analyze(publications=(receipt(**changes),)).decisions[0].status == "eligible"


def test_source_correction_rebuilds_pressure_and_historical_cutoff_preserves_old_evidence():
    session = ReplaySession(fixture(),end=at(140))
    old = analyze(session)
    event = next(event for event in fixture().events if event.event_id == "b1-duel")
    # Correct the observed duel to a stationary carry: pressure evidence disappears.
    update = changed_event(event, revision=2, source_delivery_sequence=1000, available_at=at(130).model_dump(),
                           action={"kind":"carry","end_position":{"x":20.0,"y":34.0}})
    session.deliver((update, update))
    assert analyze(session) == old
    current = analyze(session, cutoff=130)
    assert current.baseline.exposed == 2
    assert current.decisions[1].status == "insufficient_sample"
    assert current.fingerprint != old.fingerprint
    assert next(record for record in current.records if record.event_id == event.event_id).revision == 2
    assert all(source.revision == 2 for episode in current.episodes for source in episode.source_events if source.event_id == event.event_id)


def test_late_resolution_keeps_episode_pending_until_available():
    feed = small_feed([("start",61,"recovery",20,"open_play"),("duel",62,"duel",20,"won"),
                       ("end",119,"carry",20,50)], initial="northport")
    rows = list(feed.events)
    rows[-1] = changed_event(rows[-1],available_at=at(130).model_dump())
    feed = PossessionFixture.model_validate(feed.model_dump() | {"events":tuple(row.model_dump() for row in rows)})
    before = analyze(feed)
    assert before.current.pending == ("start",) and before.current.completed == 0
    assert all(record.event_id != "end" for record in before.records)
    after = analyze(feed,cutoff=130)
    assert after.current.included == ("start",) and after.current.pending == ()


def test_pressure_outside_defensive_third_does_not_expose_an_episode():
    feed = small_feed([("outside",1,"duel",40,"won"),("entry",2,"carry",40,30),("escape",3,"carry",30,40)])
    result = analyze(feed)
    assert result.baseline.completed == 1 and result.baseline.exposed == 0


@pytest.mark.parametrize("seed", [2,7,15,59])
def test_generated_development_feed_works_without_evaluator_labels(seed):
    feed = generate(profile(seed)).feed
    result = analyze(feed,cutoff=600,baseline=window(0,300),current=window(300,600))
    assert result.records == feed.events
    assert '"seed"' not in result.model_dump_json() and '"pressure_trials"' not in result.model_dump_json()
    assert all(source in { (record.event_id,record.revision) for record in result.records}
               for episode in result.episodes for source in [(ref.event_id,ref.revision) for ref in episode.source_events])


@pytest.mark.parametrize("kwargs", [{"cutoff":119},{"baseline":window(-1,60)},{"current":window(61,120)}])
def test_invalid_or_unfinished_comparisons_rejected(kwargs):
    with pytest.raises(ValueError):
        analyze(**kwargs)


@pytest.mark.parametrize("kwargs", [{"minimum_episodes":0},{"minimum_rate_change":float("nan")},{"minimum_rate_change":0},{"cooldown_ms":-1}])
def test_invalid_policy_rejected(kwargs):
    with pytest.raises(ValidationError):
        PressurePolicy(**kwargs)


def test_evidence_rejects_missing_and_future_records():
    result = analyze()
    raw = result.model_dump()
    raw["records"] = raw["records"][2:]
    with pytest.raises(ValidationError,match="missing"):
        PressureEvidence.model_validate(raw)
    raw = result.model_dump()
    raw["records"][0]["available_at"] = at(130).model_dump()
    with pytest.raises(ValidationError,match="future"):
        PressureEvidence.model_validate(raw)


def test_evidence_rejects_invented_rates_and_episode_membership():
    raw = analyze().model_dump()
    raw["baseline"]["exposure_rate"] = 0.99
    with pytest.raises(ValidationError,match="fractions"):
        PressureEvidence.model_validate(raw)
    raw = analyze().model_dump()
    raw["baseline"]["included"] = ("not-an-episode", *raw["baseline"]["included"][1:])
    with pytest.raises(ValidationError,match="episode evidence"):
        PressureEvidence.model_validate(raw)
