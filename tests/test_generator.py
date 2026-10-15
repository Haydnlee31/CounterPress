"""Independent geometric/state audits plus frozen, manually reviewed development controls."""

from hashlib import sha256
import json
from pathlib import Path
import random

import pytest
from pydantic import ValidationError

from counterpress.api.snapshots import BASELINE, CURRENT, END, SnapshotService, project
from counterpress.domain.metrics import compare_recoveries
from counterpress.domain.models import MatchTime
from counterpress.fixture import load_fixture
from counterpress.generator.__main__ import export
from counterpress.generator.engine import encoded_feed, generate
from counterpress.generator.models import GeneratorConfig, Phase, Tactics
from counterpress.generator.suite import profile, suite
from counterpress.history import History, SQLiteHistoryStore
from counterpress.replay import ReplaySession

ROOT = Path(__file__).resolve().parents[1]
EXPECTED = json.loads((ROOT / "tests/expected_generator_controls.json").read_text())
SPLITS = suite()
CONFIGS = (*SPLITS["development"], *SPLITS["holdout"])


def fixed(position, team):
    return (position.x, position.y) if team == "eastbridge" else (105 - position.x, 68 - position.y)


@pytest.mark.parametrize("config", CONFIGS, ids=lambda config: f"seed-{config.seed}")
def test_whole_generated_match_has_continuous_ball_holder_and_valid_replay(config):
    result = generate(config)
    feed = result.feed
    holder, ball = feed.events[0].actor, fixed(feed.events[0].position, feed.events[0].actor.team_id)
    previous = None
    for index, event in enumerate(feed.events, 1):
        assert event.source_delivery_sequence == event.occurrence_order == index
        assert event.revision == 1 and event.event_id == f"g{index:04}"
        assert event.match_id == feed.match_id
        assert event.occurred_at.period == event.available_at.period == 2
        assert 180000 <= event.occurred_at.elapsed_ms <= event.available_at.elapsed_ms <= 780000
        assert fixed(event.position, event.actor.team_id) == pytest.approx(ball, abs=0.001)
        action = event.action
        if action.kind == "recovery":
            assert action.from_team_id == holder.team_id and event.actor.team_id != holder.team_id
            assert previous.action.kind in ("pass", "duel")
            if previous.action.kind == "pass":
                assert previous.action.outcome == "incomplete"
            else:
                assert previous.action.outcome == "lost" and event.actor == previous.action.opponent
            if action.origin == "restart":
                assert previous.action.kind == "pass"
                assert previous.action.end_position.x in (0, 105) or previous.action.end_position.y in (0, 68)
                assert event.occurred_at.elapsed_ms - previous.occurred_at.elapsed_ms >= 8000
            holder = event.actor
        else:
            assert event.actor == holder
            if action.kind == "duel":
                assert action.opponent.team_id != holder.team_id
            elif action.kind == "pass" and action.outcome == "completed":
                assert action.recipient.team_id == holder.team_id and action.recipient != holder
                holder = action.recipient
        if action.kind in ("pass", "carry"):
            ball = fixed(action.end_position, event.actor.team_id)
        if previous:
            assert event.occurred_at.key() > previous.occurred_at.key()
            assert event.available_at.key() > previous.available_at.key()
        previous = event
    session = ReplaySession(feed, end=END)
    at_end = session.snapshot(END)
    assert len(at_end.events) == len(feed.events)
    assert at_end.state.controlled_possession_team_id == holder.team_id
    assert at_end.state.score == {"eastbridge": 0, "northport": 1}
    early = session.snapshot(MatchTime(period=2, elapsed_ms=480000))
    assert all(event.available_at.elapsed_ms <= 480000 for event in early.events)
    assert result.evaluation.feed_sha256 == sha256(encoded_feed(feed).encode()).hexdigest()


@pytest.mark.parametrize("expected", EXPECTED["controls"], ids=lambda item: item["name"])
def test_independently_reviewed_controls(expected):
    result = generate(profile(expected["seed"], expected["profile"]))
    feed = result.feed
    assert feed.match_id == expected["match_id"] and len(feed.events) == expected["event_count"]
    # Independent direct inspection, not the production detector or evaluator label.
    qualifying = [event for event in feed.events if event.action.kind == "recovery"
                  and event.actor.team_id == "eastbridge" and event.action.origin == "open_play" and event.position.x >= 70]
    assert [event.occurred_at.elapsed_ms for event in qualifying] == expected["qualifying_occurrences_ms"]
    assert [event.position.x for event in qualifying] == expected["qualifying_x"]
    assert [event.event_id for event in qualifying if 180000 < event.occurred_at.elapsed_ms <= 480000] == expected["baseline_ids"]
    assert [event.event_id for event in qualifying if 480000 < event.occurred_at.elapsed_ms <= 780000] == expected["current_ids"]
    comparison = compare_recoveries(ReplaySession(feed, end=END).snapshot(END).events, "eastbridge", BASELINE, CURRENT, END)
    assert comparison.baseline.value == len(expected["baseline_ids"])
    assert comparison.current.value == len(expected["current_ids"])
    trials = [trial for trial in result.evaluation.pressure_trials if trial.defending_team_id == "eastbridge" and trial.at.elapsed_ms > 480000]
    assert [trial.resolution.event_id for trial in trials if trial.outcome == "recovery"] == expected["current_pressure_recovery_ids"]
    assert [trial.start.event_id for trial in trials if trial.outcome == "retained"] == expected["current_failed_pressure_ids"]
    assert result.evaluation.end_state == expected["end_state"]


def test_reproducible_without_global_rng_and_no_forced_pressure_outcome():
    config = profile(2)
    before = random.getstate()
    first = generate(config)
    assert random.getstate() == before
    assert generate(config) == first
    other = generate(profile(7))
    assert first.feed != other.feed and first.feed.match_id != other.feed.match_id
    assert config.phases == other.evaluation.config.phases
    assert any(trial.outcome == "recovery" for trial in first.evaluation.pressure_trials if trial.at.elapsed_ms > 480000 and trial.defending_team_id == "eastbridge")
    assert not any(trial.outcome == "recovery" for trial in other.evaluation.pressure_trials if trial.at.elapsed_ms > 480000 and trial.defending_team_id == "eastbridge")


@pytest.mark.parametrize("name", ["pressure-shift", "directness-shift"])
def test_changed_settings_preserve_prefix_and_change_later_actions(name):
    steady = generate(profile(2, "steady")).feed
    changed = generate(profile(2, name)).feed
    def records(feed, before):
        return [event.model_dump(exclude={"match_id"}) for event in feed.events if (event.occurred_at.elapsed_ms < 480000) == before]
    assert records(steady, True) == records(changed, True)
    assert records(steady, False) != records(changed, False)


def test_holdout_has_disjoint_whole_match_ids_seeds_and_setting_combinations():
    development, holdout = SPLITS["development"], SPLITS["holdout"]
    assert len(development) == 36 and len(holdout) == 6
    assert not {item.seed for item in development} & {item.seed for item in holdout}
    dev_ids = {generate(item).feed.match_id for item in development}
    held_ids = {generate(item).feed.match_id for item in holdout}
    assert len(dev_ids) == 36 and len(held_ids) == 6 and not dev_ids & held_ids
    def combinations(configs):
        return {(phase.eastbridge.model_dump_json(), phase.northport.model_dump_json()) for config in configs for phase in config.phases}
    assert not combinations(development) & combinations(holdout)


def test_evaluator_labels_reference_real_resolutions_and_keep_unfinished_trials_pending():
    pending = 0
    # Seed 59 is a separate development regression for a challenge exactly at 58:00.
    # It is not selected into the fixed benchmark suite or the holdout set.
    for config in (*CONFIGS, profile(59)):
        result = generate(config)
        by_id = {event.event_id: event for event in result.feed.events}
        for trial in result.evaluation.pressure_trials:
            start = by_id[trial.start.event_id]
            assert start.action.kind == "duel" and trial.at == start.occurred_at
            assert start.action.opponent.team_id == trial.defending_team_id
            assert start.position.x <= 35
            if trial.outcome == "pending":
                pending += 1
                assert trial.resolution is None and start == result.feed.events[-1]
                assert result.evaluation.end_state == "loose"
            else:
                resolved = by_id[trial.resolution.event_id]
                if trial.outcome == "recovery":
                    assert resolved.action.kind == "recovery" and resolved.action.origin == "open_play"
                    assert resolved.actor == start.action.opponent and resolved.position.x >= 70
                else:
                    assert resolved == start and start.action.outcome == "won"
    assert pending > 0


def test_exports_keep_all_hidden_data_outside_feed_and_refuse_overwrite(tmp_path):
    folder = tmp_path / "export"
    export(folder, {"single": (profile(2),)})
    paths = list((folder / "feeds").glob("*.json"))
    assert len(paths) == 1
    raw = paths[0].read_text()
    assert all(word not in raw for word in ('"seed"', '"pressure"', '"directness"', '"flank"', '"phases"', '"pressure_trials"', '"outcome_label"', '"holdout"'))
    feed = load_fixture(paths[0])
    private = json.loads((folder / "evaluation" / paths[0].name).read_text())
    assert private["config"]["seed"] == 2 and private["feed_sha256"] == sha256(raw.encode()).hexdigest()
    assert private["match_id"] == feed.match_id
    with pytest.raises(FileExistsError):
        export(folder, {"single": (profile(7),)})
    assert paths[0].read_text() == raw
    with pytest.raises(FileExistsError):
        export(tmp_path / "duplicates", {"development": (profile(2),), "holdout": (profile(2),)})
    assert not (tmp_path / "duplicates").exists()


def test_generated_feed_uses_existing_evidence_and_persistence_without_evaluator(tmp_path):
    feed = generate(profile(2)).feed
    store = SQLiteHistoryStore(tmp_path / "history.sqlite3")
    store.transact("increase", lambda _: project(History(fixture=feed, records=feed.events), END))
    # Stored public feed is enough; no generator configuration is passed into the snapshot service.
    service = SnapshotService(tmp_path / "no-seed-files", SQLiteHistoryStore(tmp_path / "history.sqlite3"))
    snapshot = service.snapshot("increase", 780000)
    assert snapshot.insight.facts.baseline_count == 1 and snapshot.insight.facts.current_count == 3
    assert [event.event_id for event in snapshot.evidence.records] == ["g0031", "g0087", "g0097", "g0107"]
    assert snapshot.audience.variant is not None
    assert service.snapshot("increase", 540000).insight is None


@pytest.mark.parametrize("change", [{"pressure": -0.1}, {"pressure": 1.1}, {"directness": float("nan")},
    {"flank": "diagonal"}, {"escape_skill": True}])
def test_invalid_hidden_settings_fail_before_generation(change):
    with pytest.raises(ValidationError):
        Tactics.model_validate(profile(2).phases[0].eastbridge.model_dump() | change)


def test_seed_and_phase_validation():
    phase = profile(2).phases[0]
    for seed in (-1, 2**32, True):
        with pytest.raises(ValidationError):
            GeneratorConfig(seed=seed, phases=(phase,))
    for phases in ((), (phase, phase), (profile(2).phases[1], phase)):
        with pytest.raises(ValidationError):
            GeneratorConfig(seed=2, phases=phases)
    with pytest.raises(ValidationError):
        Phase.model_validate(phase.model_dump() | {"start_ms": 780000})
